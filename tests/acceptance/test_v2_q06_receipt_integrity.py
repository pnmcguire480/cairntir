import hashlib
import json

import pytest

from cairntir.durability import request_hash
from cairntir.errors import WorkflowError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

WING = "q06_receipt_integrity"
ROOM = "database"
KEY = "paladin.human.map:integrity-run"
OPERATION = "paladin.human.map.v1"
CAPABILITY_MAP = {"schema": "cairntir.paladin-human-capabilities.v1", "checks": []}
REQUEST = {
    "run_id": "integrity-run",
    "plan_sha256": "a" * 64,
    "map_sha256": request_hash(CAPABILITY_MAP),
    "capability_map": CAPABILITY_MAP,
}


def _state(store):
    drawers = store._conn.execute(
        "SELECT id, wing, room, content, metadata FROM drawers ORDER BY id"
    ).fetchall()
    workflows = store._conn.execute("SELECT * FROM workflow_runs ORDER BY idempotency_key")
    return tuple(map(tuple, drawers)), tuple(map(tuple, workflows))


def _committed_map(store):
    result = {"map_sha256": REQUEST["map_sha256"]}
    body = json.dumps(
        {"operation": OPERATION, "request_sha256": request_hash(REQUEST), "result": result},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    def append():
        drawer = store.add(
            Drawer(
                wing=WING,
                room=ROOM,
                content=body,
                metadata={
                    "kind": "paladin.human",
                    "operation": OPERATION,
                    "key": KEY,
                    "run_id": REQUEST["run_id"],
                    "attempt_id": None,
                    "plan_sha256": REQUEST["plan_sha256"],
                    "map_sha256": REQUEST["map_sha256"],
                    "item_id": None,
                },
            )
        )
        return {
            "request": REQUEST,
            "result": result,
            "evidence": {
                "drawer_id": drawer.id,
                "source_identity": store.portable_identity(drawer.id),
                "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
            },
        }

    execution = store.paladin_human_execute_once(
        wing=WING,
        room=ROOM,
        idempotency_key=KEY,
        operation=OPERATION,
        request=REQUEST,
        action=append,
    )
    assert execution.receipt.result["evidence"]["drawer_id"] > 0
    return execution.receipt.result["evidence"]["drawer_id"]


@pytest.mark.parametrize(
    "corruption",
    [
        "owner_slot",
        "request_identity",
        "request_hash",
        "foreign_evidence",
        "source_identity",
        "evidence_content",
        "missing_reference_field",
    ],
)
def test_replay_rejects_corrupted_receipt_without_rewriting_evidence(tmp_path, corruption):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        drawer_id = _committed_map(store)
        assert store.paladin_human_receipt(KEY, wing=WING) is not None
        with store.transaction():
            if corruption == "owner_slot":
                marker = store._conn.execute(
                    "SELECT idempotency_key, result FROM workflow_runs "
                    "WHERE idempotency_key LIKE 'paladin.human.owner:%'"
                ).fetchone()
                record = json.loads(marker["result"])
                record["storage_key"] = "paladin.human.map:unbound"
                store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                    (json.dumps(record), marker["idempotency_key"]),
                )
            elif corruption == "request_hash":
                store._conn.execute(
                    "UPDATE workflow_runs SET request_hash=? WHERE idempotency_key=?",
                    ("0" * 64, KEY),
                )
            elif corruption == "foreign_evidence":
                foreign = store.add(Drawer(wing="another_wing", room=ROOM, content="private"))
                row = store._conn.execute(
                    "SELECT result FROM workflow_runs WHERE idempotency_key=?", (KEY,)
                ).fetchone()
                record = json.loads(row["result"])
                record["evidence"]["drawer_id"] = foreign.id
                store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                    (json.dumps(record), KEY),
                )
            elif corruption == "evidence_content":
                store._conn.execute(
                    "UPDATE drawers SET content=? WHERE id=?", ("silently changed", drawer_id)
                )
            else:
                row = store._conn.execute(
                    "SELECT result FROM workflow_runs WHERE idempotency_key=?", (KEY,)
                ).fetchone()
                record = json.loads(row["result"])
                if corruption == "request_identity":
                    record["request"]["run_id"] = "another-run"
                elif corruption == "source_identity":
                    record["evidence"]["source_identity"] = "wrong source"
                else:
                    del record["evidence"]["content_sha256"]
                store._conn.execute(
                    "UPDATE workflow_runs SET result=? WHERE idempotency_key=?",
                    (json.dumps(record), KEY),
                )
        before = _state(store)
        with pytest.raises(WorkflowError):
            store.paladin_human_receipt(KEY, wing=WING)
        assert _state(store) == before


def test_invalid_map_binding_cannot_claim_key_or_run_action(tmp_path):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        before = _state(store)
        bad = {**REQUEST, "map_sha256": "0" * 64}
        with pytest.raises(WorkflowError, match="capability map"):
            store.paladin_human_execute_once(
                wing=WING,
                room=ROOM,
                idempotency_key=KEY,
                operation=OPERATION,
                request=bad,
                action=lambda: pytest.fail("invalid request executed"),
            )
        assert _state(store) == before


def test_q06_workflow_refuses_caller_transaction_before_action(tmp_path):
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32)) as store:
        before = _state(store)
        with store.transaction(), pytest.raises(WorkflowError, match="caller transaction"):
            store.paladin_human_execute_once(
                wing=WING,
                room=ROOM,
                idempotency_key=KEY,
                operation=OPERATION,
                request=REQUEST,
                action=lambda: pytest.fail("nested Q06 action executed"),
            )
        assert _state(store) == before
