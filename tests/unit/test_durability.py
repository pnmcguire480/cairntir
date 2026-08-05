"""Crash-safety, idempotency, provenance, and validity tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cairntir.durability import WorkflowState
from cairntir.errors import IdempotencyConflictError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore, inspect_database_integrity
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import TrustLevel, WriteProvenance


def _store(tmp_path: Path) -> DrawerStore:
    return DrawerStore(tmp_path / "durability.db", HashEmbeddingProvider(dimension=32))


def _drawer(content: str) -> Drawer:
    return Drawer(wing="cairntir", room="durability", content=content)


def test_transaction_rolls_back_drawers_and_vectors(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        with pytest.raises(RuntimeError, match="crash"), store.transaction():
            store.add(_drawer("first half"))
            store.add(_drawer("second half"))
            raise RuntimeError("simulated crash")

        assert store.list_by(include_expired=True) == []
        assert store._conn.execute("SELECT COUNT(*) FROM vec_drawers").fetchone()[0] == 0


def test_nested_savepoint_rolls_back_only_inner_unit(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        with store.transaction():
            store.add(_drawer("outer before"))
            with pytest.raises(RuntimeError, match="inner"), store.transaction():
                store.add(_drawer("inner discarded"))
                raise RuntimeError("inner")
            store.add(_drawer("outer after"))

        assert {d.content for d in store.list_by()} == {"outer before", "outer after"}


def test_execute_once_replays_committed_result_without_duplicate_writes(
    tmp_path: Path,
) -> None:
    with _store(tmp_path) as store:

        def action() -> dict[str, object]:
            first = store.add(_drawer("prediction"))
            second = store.add(_drawer("observation"))
            return {"ids": [first.id, second.id]}

        first = store.execute_once(
            idempotency_key="reason:42",
            operation="reason.step",
            request={"question": "will it work?"},
            action=action,
        )
        replay = store.execute_once(
            idempotency_key="reason:42",
            operation="reason.step",
            request={"question": "will it work?"},
            action=action,
        )

        assert first.replayed is False
        assert replay.replayed is True
        assert replay.result == first.result
        assert len(store.list_by()) == 2
        assert replay.receipt.state is WorkflowState.COMMITTED
        assert replay.receipt.attempt_count == 1


def test_failed_workflow_rolls_back_then_retries_same_key(tmp_path: Path) -> None:
    with _store(tmp_path) as store:

        def fails() -> dict[str, object]:
            store.add(_drawer("must roll back"))
            raise RuntimeError("runner died")

        with pytest.raises(RuntimeError, match="runner died"):
            store.execute_once(
                idempotency_key="retry-me",
                operation="recipe.run",
                request={"recipe": "test"},
                action=fails,
            )

        failed = store.workflow_receipt("retry-me")
        assert failed is not None
        assert failed.state is WorkflowState.FAILED
        assert store.list_by() == []

        committed = store.execute_once(
            idempotency_key="retry-me",
            operation="recipe.run",
            request={"recipe": "test"},
            action=lambda: {"id": store.add(_drawer("complete")).id},
        )
        assert committed.receipt.state is WorkflowState.COMMITTED
        assert committed.receipt.attempt_count == 2
        assert [d.content for d in store.list_by()] == ["complete"]


def test_idempotency_key_cannot_be_rebound(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        store.execute_once(
            idempotency_key="fixed",
            operation="reason.step",
            request={"question": "A"},
            action=lambda: {"ok": True},
        )
        with pytest.raises(IdempotencyConflictError, match="different request"):
            store.execute_once(
                idempotency_key="fixed",
                operation="reason.step",
                request={"question": "B"},
                action=lambda: {"ok": True},
            )


def test_provenance_round_trips_and_expired_memory_is_hidden(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    user = WriteProvenance.create(
        host="codex",
        capture_path="mcp",
        trust=TrustLevel.USER_ASSERTED,
        session_id="session-123",
        model="gpt-test",
    )
    expired = user.for_write(valid_until=now - timedelta(seconds=1))

    with _store(tmp_path) as store:
        expired_drawer = store.add(_drawer("same semantic content"), provenance=expired)
        current_drawer = store.add(_drawer("same semantic content"), provenance=user)

        receipt = store.get_provenance(current_drawer.id or 0)
        assert receipt is not None
        assert receipt.host == "codex"
        assert receipt.model == "gpt-test"
        assert receipt.session_id == "session-123"

        assert [d.id for d in store.list_by()] == [current_drawer.id]
        assert {d.id for d in store.list_by(include_expired=True)} == {
            expired_drawer.id,
            current_drawer.id,
        }
        hits = store.search("same semantic content", rerank_by_belief=False)
        assert [drawer.id for drawer, _ in hits] == [current_drawer.id]


def test_all_four_hosts_share_memory_without_losing_origin(tmp_path: Path) -> None:
    path = tmp_path / "shared.db"
    ids: dict[str, int] = {}
    for host in ("codex", "cursor", "claude", "qwen"):
        provenance = WriteProvenance.create(
            host=host,
            capture_path="mcp",
            session_id=f"{host}-session",
            model=f"{host}-model",
        )
        with DrawerStore(
            path,
            HashEmbeddingProvider(dimension=32),
            provenance=provenance,
        ) as store:
            saved = store.add(_drawer(f"continuity from {host}"))
            assert saved.id is not None
            ids[host] = saved.id

    with DrawerStore(path, HashEmbeddingProvider(dimension=32)) as store:
        hits = store.search("continuity", limit=10, rerank_by_belief=False)
        assert {drawer.id for drawer, _ in hits} == set(ids.values())
        for host, drawer_id in ids.items():
            receipt = store.get_provenance(drawer_id)
            assert receipt is not None
            assert receipt.host == host
            assert receipt.session_id == f"{host}-session"
            assert receipt.model == f"{host}-model"


def test_read_only_integrity_report_surfaces_failed_workflows(tmp_path: Path) -> None:
    path = tmp_path / "integrity.db"

    def fail() -> dict[str, object]:
        raise RuntimeError("boom")

    with (
        DrawerStore(path, HashEmbeddingProvider(dimension=16)) as store,
        pytest.raises(RuntimeError),
    ):
        store.execute_once(
            idempotency_key="failed",
            operation="test",
            request={"value": 1},
            action=fail,
        )

    report = inspect_database_integrity(path)
    assert report.ok is True
    assert report.quick_check == ("ok",)
    assert report.foreign_key_violations == 0
    assert report.started_workflows == 0
    assert report.failed_workflows == 1
