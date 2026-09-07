from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from test_recovery_outcomes import (
    TEXT,
    add,
    contents,
)

from cairntir.errors import CairntirError, EmbeddingSpaceError, MemoryStoreError, WorkflowError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore, inspect_embedding_space
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, WriteProvenance
from cairntir.tasks import TaskBook


@pytest.mark.parametrize(
    "operation",
    [
        lambda store: store.get(1),
        lambda store: store.get_provenance(1),
        lambda store: store.list_by(),
        lambda store: store.wing_counts(),
        lambda store: store.wing_exists("recovery"),
        lambda store: store.content_lengths(),
        lambda store: store.has_content_since(
            wing="recovery", content=TEXT, created_at=datetime.now(UTC)
        ),
        lambda store: store.stale_ids(older_than=datetime.now(UTC), layer=Layer.ON_DEMAND),
        lambda store: store.context_candidates(wing="recovery"),
        lambda store: store.context_relatives(wing="recovery", drawer_ids=[1]),
        lambda store: store.portable_identity(1),
        lambda store: store.portable_source(1),
        lambda store: store.portable_relations(1),
        lambda store: store.workflow_receipt("missing"),
        lambda store: store.legacy_migration_drawer_ids(),
        lambda store: store.embedding_status(),
        lambda store: store.is_registered_procedure(1),
    ],
    ids=[
        "get",
        "provenance",
        "list",
        "counts",
        "wing",
        "lengths",
        "dedup",
        "stale",
        "candidates",
        "relationships",
        "portable-id",
        "portable-source",
        "portable-relations",
        "workflow",
        "legacy-trust",
        "embedding-status",
        "procedure",
    ],
)
def test_revoked_sql_read_access_reports_error_instead_of_empty_success(seeded, operation):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.set_authorizer(
            lambda action, *_: (
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ else sqlite3.SQLITE_OK
            )
        )
        try:
            with pytest.raises(CairntirError, match=r"prohibited|authorized"):
                operation(store)
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        assert store.list_by(wing="recovery")


@pytest.mark.parametrize(
    ("operation", "column"),
    [
        (lambda store: store.reinforce(1, amount=2), "belief_mass"),
        (lambda store: store.weaken(1, amount=2), "belief_mass"),
        (lambda store: store.update_layer(1, Layer.DEEP), "layer"),
        (lambda store: store.add_anchors(1, [{"path": "src/example.py"}]), "metadata"),
    ],
)
def test_revoked_sql_write_access_preserves_drawer_and_vector_state(seeded, operation, column):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.set_authorizer(
            lambda action, table, field, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_UPDATE and table == "drawers" and field == column
                else sqlite3.SQLITE_OK
            )
        )
        try:
            with pytest.raises(MemoryStoreError, match=r"authorized|prohibited"):
                operation(store)
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        saved = add(store, "Write access restored without losing prior evidence.")
        assert saved.id is not None


@pytest.mark.parametrize("result", [{"bad": {1, 2}}, {"bad": object()}])
def test_non_json_workflow_result_rolls_back_and_can_retry(seeded, result):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        original = [item.content for item in store.list_by()]

        def invalid_result():
            add(store, "Must not survive a failed workflow result.")
            return result

        with pytest.raises(WorkflowError, match="non-JSON result"):
            store.execute_once(
                idempotency_key="non-json", operation="verify", request={}, action=invalid_result
            )
        assert [item.content for item in store.list_by()] == original
        failure = store.workflow_receipt("non-json")
        assert failure.state.value == "failed" and "non-JSON result" in failure.error
        success = store.execute_once(
            idempotency_key="non-json",
            operation="verify",
            request={},
            action=lambda: {"id": add(store, "Retry succeeds.").id},
        )
        assert success.receipt.attempt_count == 2
        assert success.receipt.state.value == "committed"
        assert "Must not survive" not in contents(database)


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("result", "not json"),
        ("result", "[]"),
        ("state", "invented"),
        ("started_at", "yesterday"),
        ("updated_at", "tomorrow"),
    ],
)
def test_damaged_workflow_receipt_is_reported_without_rerunning_action(seeded, column, bad_value):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store.execute_once(
            idempotency_key="durable-result",
            operation="verify",
            request={},
            action=lambda: {"ok": True},
        )
        store._conn.execute(
            f'UPDATE workflow_runs SET "{column}"=? WHERE idempotency_key=?',  # noqa: S608
            (bad_value, "durable-result"),
        )
        store._conn.commit()
        before = contents(database)
        ran = []
        with pytest.raises(WorkflowError, match=r"invalid|not an object"):
            store.execute_once(
                idempotency_key="durable-result",
                operation="verify",
                request={},
                action=lambda: ran.append(True) or {},
            )
        assert ran == []
        assert contents(database) == before


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [[0.5] * 31] * 3,
        [[float("nan")] * 32] * 3,
        [[0.0] * 32] * 3,
        [[1e100] * 32] * 3,
        [[1e-100] * 32] * 3,
    ],
)
def test_invalid_reindex_output_keeps_previous_working_index(seeded, monkeypatch, vectors):
    database, _, _ = seeded
    before = contents(database)
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(database, provider) as store:
        with monkeypatch.context() as patch:
            patch.setattr(provider, "embed", lambda texts: vectors)
            with pytest.raises(EmbeddingSpaceError):
                store.reindex_embeddings()
        assert contents(database) == before
        assert store.embedding_status().verified
        assert store.search(TEXT, wing="recovery", room="evidence", limit=1)[0][0].content == TEXT


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("embedding_dimension", "nonnumeric"),
        ("embedding_dimension", "17"),
        ("embedding_generation", None),
        ("embedding_space_id", None),
    ],
)
def test_damaged_embedding_identity_disables_semantic_use_without_repairing_evidence(
    seeded, key, value
):
    database, _, _ = seeded
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(database, provider) as store:
        keys = dict(store._conn.execute("SELECT key,value FROM store_metadata"))
        assert key in keys
        if value is None:
            store._conn.execute("DELETE FROM store_metadata WHERE key=?", (key,))
        else:
            store._conn.execute("UPDATE store_metadata SET value=? WHERE key=?", (value, key))
        store._conn.commit()
        before = contents(database)
        status = inspect_embedding_space(database, provider)
        assert not status.verified and status.state in {"corrupt", "unverified"}
        with pytest.raises(EmbeddingSpaceError):
            store.search(TEXT)
        assert contents(database) == before


@pytest.mark.parametrize("payload", [{"value": object()}, {"value": {1}}])
def test_unserializable_request_cannot_create_a_started_workflow(seeded, payload):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(WorkflowError),
    ):
        store.execute_once(
            idempotency_key="invalid-request",
            operation="verify",
            request=payload,
            action=lambda: {"id": add(store, "never execute").id},
        )
    assert contents(database) == before


@pytest.mark.parametrize("operation", ["add", "search"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0, None, 1e100, 1e-100, "invalid"])
def test_invalid_embedding_cannot_write_or_return_misleading_matches(
    seeded, monkeypatch, operation, value
):
    database, _, _ = seeded
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(database, provider) as store:
        before = contents(database)
        with monkeypatch.context() as patch:
            patch.setattr(
                provider,
                "embed",
                lambda texts: [] if value is None else [[value] * 32 for _ in texts],
            )
            with pytest.raises(EmbeddingSpaceError):
                add(
                    store, "An invalid embedding must not be written."
                ) if operation == "add" else store.search(TEXT)
        assert contents(database) == before
        assert store.search(TEXT, wing="recovery", room="evidence", limit=1)[0][0].content == TEXT


def test_rejected_anchor_repair_does_not_record_access_or_metadata_writes(seeded):
    database, _, _ = seeded
    before = contents(database)
    with (
        DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store,
        pytest.raises(MemoryStoreError, match="no anchors to repair"),
    ):
        store.repair_anchors(1)
    assert contents(database) == before


@pytest.mark.parametrize("result", [[], "done", 1, None, True])
def test_nonobject_workflow_result_rolls_back_before_reporting_failure(seeded, result):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        before = [(item.id, item.content) for item in store.list_by()]

        def invalid_result():
            add(store, "discard this failed workflow write")
            return result

        with pytest.raises(WorkflowError):
            store.execute_once(
                idempotency_key="nonobject", operation="verify", request={}, action=invalid_result
            )
        assert [(item.id, item.content) for item in store.list_by()] == before, (
            "RECOVERY: invalid workflow result committed its writes"
        )
        failed = store.workflow_receipt("nonobject")
        assert failed.state.value == "failed"
        corrected = store.execute_once(
            idempotency_key="nonobject",
            operation="verify",
            request={},
            action=lambda: {"id": add(store, "corrected workflow").id},
        )
        assert corrected.receipt.state.value == "committed" and corrected.receipt.attempt_count == 2
        assert "discard this failed workflow write" not in contents(database)


@pytest.mark.parametrize("boundary", ["prepare", "commit", "failure-record"])
def test_failed_workflow_receipt_write_preserves_data_and_allows_retry(seeded, boundary):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        if boundary == "prepare":
            store._conn.execute(
                "CREATE TRIGGER deny_receipt BEFORE INSERT ON workflow_runs "
                "BEGIN SELECT RAISE(ABORT, 'receipt write denied'); END"
            )
        else:
            state = "committed" if boundary == "commit" else "failed"
            store._conn.execute(
                "CREATE TRIGGER deny_receipt BEFORE UPDATE ON workflow_runs "
                f"WHEN NEW.state='{state}' "
                "BEGIN SELECT RAISE(ABORT, 'receipt write denied'); END"
            )
        before = [(item.id, item.content) for item in store.list_by()]

        def action():
            add(store, "discard this failed receipt write")
            if boundary == "failure-record":
                raise RuntimeError("work failed")
            return {"done": True}

        with pytest.raises(WorkflowError):
            store.execute_once(
                idempotency_key="receipt-write", operation="verify", request={}, action=action
            )
        assert [(item.id, item.content) for item in store.list_by()] == before
        receipt = store.workflow_receipt("receipt-write")
        if boundary == "prepare":
            assert receipt is None
        else:
            assert receipt.state.value == ("failed" if boundary == "commit" else "started")
        store._conn.execute("DROP TRIGGER deny_receipt")
        corrected = store.execute_once(
            idempotency_key="receipt-write",
            operation="verify",
            request={},
            action=lambda: {"id": add(store, "receipt write recovered").id},
        )
        assert corrected.receipt.state.value == "committed"
        assert "discard this failed receipt write" not in contents(database)


@pytest.mark.parametrize("boundary", ["registry", "drawer", "access", "checkpoint"])
def test_late_sqlite_read_or_access_failure_cannot_claim_a_successful_result(seeded, boundary):
    database, task, expected = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:

        def authorize(action, table, field, *_):
            denied = (
                (
                    boundary == "registry"
                    and action == sqlite3.SQLITE_READ
                    and table == "workflow_runs"
                )
                or (
                    boundary == "drawer"
                    and action == sqlite3.SQLITE_READ
                    and table == "drawers"
                    and field == "content"
                )
                or (
                    boundary == "access"
                    and action == sqlite3.SQLITE_UPDATE
                    and table == "drawers"
                    and field == "access_count"
                )
                or (
                    boundary == "checkpoint"
                    and action == sqlite3.SQLITE_PRAGMA
                    and table == "wal_checkpoint"
                )
            )
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK

        store._conn.set_authorizer(authorize)
        try:
            with pytest.raises(MemoryStoreError, match=r"authorized|prohibited"):
                if boundary in {"registry", "drawer"}:
                    TaskBook(store).resume("recovery", task_id=task)
                elif boundary == "access":
                    store.get(1)
                else:
                    store.checkpoint()
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        assert TaskBook(store).resume("recovery", task_id=task) == expected


@pytest.mark.parametrize("damage", ["invalid-provenance", "mismatched-trust"])
def test_reindex_rejects_damaged_provenance_before_replacing_any_vector(seeded, damage):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        if damage == "invalid-provenance":
            store._conn.execute("UPDATE drawers SET provenance='{}' WHERE id=1")
        else:
            store._conn.execute("UPDATE drawers SET trust='system' WHERE id=1")
        store._conn.commit()
        before = contents(database)
        with pytest.raises(CairntirError, match="provenance"):
            store.reindex_embeddings()
        assert contents(database) == before


@pytest.mark.parametrize("boundary", ["rollback", "nested-rollback", "nested-release"])
def test_sqlite_rollback_or_savepoint_failure_is_explicit_and_surviving_data_remains_recoverable(
    seeded, boundary
):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:

        def authorize(action, operation, *_):
            denied = (
                (
                    boundary == "rollback"
                    and action == sqlite3.SQLITE_TRANSACTION
                    and operation == "ROLLBACK"
                )
                or (
                    boundary == "nested-rollback"
                    and action == sqlite3.SQLITE_SAVEPOINT
                    and operation == "ROLLBACK"
                )
                or (
                    boundary == "nested-release"
                    and action == sqlite3.SQLITE_SAVEPOINT
                    and operation == "RELEASE"
                )
            )
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK

        store._conn.set_authorizer(authorize)
        try:
            with (
                pytest.raises(MemoryStoreError, match=r"roll back|commit"),
                store.transaction(),
            ):
                add(store, "uncommitted outer write")
                if boundary == "rollback":
                    raise ValueError("operation failed")
                with store.transaction():
                    add(store, "uncommitted nested write")
                    if boundary == "nested-rollback":
                        raise ValueError("nested operation failed")
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        store._conn.rollback()
        assert contents(database) == before
        add(store, "subsequent committed write")
        assert "subsequent committed write" in contents(database)
        assert "uncommitted outer write" not in contents(database)


@pytest.mark.parametrize("boundary", ["read", "create-stage"])
def test_failed_reindex_preparation_preserves_the_working_index(seeded, boundary):
    database, _, _ = seeded
    before = contents(database)
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:

        def authorize(action, table, column, *_):
            denied = (
                boundary == "read"
                and action == sqlite3.SQLITE_READ
                and table == "drawers"
                and column == "content"
            ) or (boundary == "create-stage" and action == sqlite3.SQLITE_CREATE_TEMP_TABLE)
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK

        store._conn.set_authorizer(authorize)
        try:
            with pytest.raises(MemoryStoreError, match=r"authorized|prohibited"):
                store.reindex_embeddings()
        finally:
            store._conn.set_authorizer(None)
        assert contents(database) == before
        assert store.search(TEXT, wing="recovery", room="evidence", limit=1)[0][0].content == TEXT


def test_semantic_trust_and_expiry_filters_cannot_return_untrusted_or_expired_evidence(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        trusted = store.add(
            Drawer(wing="recovery", room="evidence", content=TEXT),
            provenance=WriteProvenance.create(
                host="test", capture_path="test", trust=TrustLevel.SYSTEM
            ),
        )
        expired = store.add(
            Drawer(wing="recovery", room="evidence", content=TEXT),
            provenance=WriteProvenance.create(
                host="test",
                capture_path="test",
                trust=TrustLevel.SYSTEM,
                valid_until=datetime.now(UTC) - timedelta(days=1),
            ),
        )
        normal = store.search(TEXT, wing="recovery", trust=TrustLevel.SYSTEM)
        assert [drawer.id for drawer, _ in normal] == [trusted.id]
        historical = store.search(
            TEXT, wing="recovery", trust=TrustLevel.SYSTEM, include_expired=True
        )
        assert {drawer.id for drawer, _ in historical} == {trusted.id, expired.id}
        assert all(drawer.content == TEXT for drawer, _ in historical)
        assert store.get(1).content == TEXT
