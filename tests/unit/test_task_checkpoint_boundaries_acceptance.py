"""Independent checkpoint input boundaries; see the matching frozen contract."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_task_resume_acceptance import _cli, _McpPeer, _state

from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook

WING = "checkpoint-boundaries"
ROOM = "tasks"
STRING_FIELDS = (
    "content",
    "idempotency_key",
    "task_id",
    "completed",
    "outstanding",
    "next_action",
    "model",
)
TRANSPORT_CASES = (*STRING_FIELDS, "evidence-overflow", "evidence-huge")


@pytest.fixture()
def owner(tmp_cairntir_home: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DrawerStore]:
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    with DrawerStore(
        tmp_cairntir_home / "cairntir.db", HashEmbeddingProvider(dimension=32)
    ) as store:
        yield store


def _payload(**changes: Any) -> dict[str, Any]:
    return {
        "content": "Preserve the exact request and resume the boundary repair.",
        "model": "independent-boundary-tester",
        "checkpoint": {
            "expected_revision": 0,
            "idempotency_key": "boundary-create",
            "status": "active",
            "completed": [],
            "outstanding": ["repair the input boundary"],
            "next_action": "Validate the checkpoint.",
            "evidence_ids": [],
        },
        **changes,
    }


def _save(owner: DrawerStore, payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(TaskBook(owner).checkpoint(wing=WING, room=ROOM, **payload))


def _update(owner: DrawerStore) -> dict[str, Any]:
    created = _save(owner, _payload())
    payload = _payload()
    payload["checkpoint"].update(
        task_id=created["task_id"],
        expected_revision=created["revision"],
        idempotency_key="boundary-update",
    )
    return payload


def _invalid(payload: dict[str, Any], field: str, surrogate: str = "\ud800") -> None:
    if field in {"content", "model"}:
        payload[field] = "before" + surrogate + "after"
    elif field in {"completed", "outstanding"}:
        payload["checkpoint"][field] = ["before" + surrogate + "after"]
    elif field in {"evidence-overflow", "evidence-huge"}:
        payload["checkpoint"]["evidence_ids"] = [2**63 if field == "evidence-overflow" else 10**100]
    else:
        payload["checkpoint"][field] = "before" + surrogate + "after"


def _clean_error(text: str, prefix: str) -> None:
    assert prefix in text and text.strip() != prefix
    assert not any(
        marker in text
        for marker in ("Traceback", "OverflowError", "UnicodeEncodeError", "codec can't encode")
    ), text


class _EscapedPeer(_McpPeer):
    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self.process.stdin.flush()


def _cli_payload(path: Path, payload: dict[str, Any]) -> Any:
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8", newline="\n")
    return _cli("checkpoint", WING, "--room", ROOM, "--input", str(path))


@pytest.mark.parametrize("field", STRING_FIELDS)
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"], ids=["high", "low"])
def test_direct_surrogate_rejection_is_typed_and_atomic(
    owner: DrawerStore, field: str, surrogate: str
) -> None:
    payload = _update(owner)
    _invalid(payload, field, surrogate)
    before = _state()
    try:
        with pytest.raises(CairntirError):
            _save(owner, payload)
    finally:
        assert _state() == before


@pytest.mark.parametrize("evidence_id", [2**63, 10**100], ids=["int64-overflow", "huge"])
def test_direct_oversized_evidence_ids_are_typed_and_atomic(
    owner: DrawerStore, evidence_id: int
) -> None:
    payload = _update(owner)
    payload["checkpoint"]["evidence_ids"] = [evidence_id]
    before = _state()
    try:
        with pytest.raises(CairntirError):
            _save(owner, payload)
    finally:
        assert _state() == before


def test_representable_missing_evidence_id_fails_cleanly(owner: DrawerStore) -> None:
    payload = _update(owner)
    payload["checkpoint"]["evidence_ids"] = [2**63 - 1]
    before = _state()
    with pytest.raises(CairntirError):
        _save(owner, payload)
    assert _state() == before


@pytest.mark.parametrize("field", ["idempotency_key", "evidence-overflow"])
def test_invalid_creation_leaves_no_task_or_failure_receipt(owner: DrawerStore, field: str) -> None:
    payload = _payload()
    _invalid(payload, field)
    before = _state()
    try:
        with pytest.raises(CairntirError):
            _save(owner, payload)
    finally:
        assert _state() == before


@pytest.mark.parametrize("field", TRANSPORT_CASES)
def test_cli_surfaces_clean_boundary_errors_without_writes(
    owner: DrawerStore, tmp_path: Path, field: str
) -> None:
    payload = _update(owner)
    task_id = payload["checkpoint"]["task_id"]
    _invalid(payload, field)
    before = _state()
    rejected = _cli_payload(tmp_path / "invalid.json", payload)
    assert _state() == before
    assert rejected.returncode != 0
    _clean_error(rejected.stdout + rejected.stderr, "cairntir:")
    resumed = json.loads(TaskBook(owner).resume(WING, task_id=task_id))
    assert resumed["status"] == "ready" and resumed["revision"] == 1


@pytest.mark.parametrize("field", ["evidence-overflow", "evidence-huge"])
def test_stdio_surfaces_typed_boundary_errors_and_remains_usable(
    owner: DrawerStore, field: str
) -> None:
    payload = _update(owner)
    task_id = payload["checkpoint"]["task_id"]
    _invalid(payload, field, "\udfff")
    peer = _EscapedPeer("codex")
    try:
        peer.initialize()
        before = _state()
        rejected = peer.call("cairntir_remember", wing=WING, room=ROOM, **payload)
        assert _state() == before
        assert rejected["isError"] is True
        _clean_error("\n".join(item["text"] for item in rejected["content"]), "[cairntir error]")
        resumed = peer.json("cairntir_handoff", wing=WING, resume=True, task_id=task_id)
        assert resumed["status"] == "ready" and resumed["revision"] == 1
        assert _state() == before
    finally:
        peer.close()


@pytest.mark.parametrize("transport", ["direct", "cli", "stdio"])
def test_valid_unicode_round_trips_with_idempotent_replay(
    owner: DrawerStore, tmp_path: Path, transport: str
) -> None:
    request = "  Caf\u00e9 e\u0301 \u6771\u4eac \U0001f9ea\nPreserve exact Unicode.\t"
    payload = _payload(content=request, model="mod\u00e8le-\U0001f9e0")
    payload["checkpoint"].update(
        idempotency_key="cl\u00e9-\U0001f511",
        completed=["\u5b8c\u4e86 \U0001f680"],
        outstanding=["r\u00e9parer \U0001f6e0"],
        next_action="\u6b21\u3078 \U0001f9ea",
    )
    peer = _EscapedPeer("codex") if transport == "stdio" else None
    try:
        if peer is not None:
            peer.initialize()

        def save() -> dict[str, Any]:
            if peer is not None:
                return peer.json("cairntir_remember", wing=WING, room=ROOM, **payload)
            if transport == "cli":
                result = _cli_payload(tmp_path / "unicode.json", payload)
                assert result.returncode == 0, result.stdout + result.stderr
                return json.loads(result.stdout)
            return _save(owner, payload)

        created = save()
        before_retry = _state()
        retry = save()
        assert retry == {**created, "replayed": True}
        assert _state() == before_retry
        resumed = json.loads(TaskBook(owner).resume(WING, task_id=created["task_id"]))
        assert resumed["status"] == "ready"
        checkpoint = resumed["checkpoint"]
        assert checkpoint["original_request"] == checkpoint["summary"] == request
        for field in ("completed", "outstanding", "next_action"):
            assert checkpoint[field] == payload["checkpoint"][field]
        assert checkpoint["provenance"]["original"]["model"] == payload["model"]
        assert _state() == before_retry
    finally:
        if peer is not None:
            peer.close()
