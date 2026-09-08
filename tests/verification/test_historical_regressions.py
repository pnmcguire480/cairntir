from __future__ import annotations

import json
from pathlib import Path

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def test_handshake_identifies_cairntir(tmp_cairntir_home: Path) -> None:
    from cairntir import __version__
    from cairntir.mcp.backend import CairntirBackend
    from cairntir.mcp.server import build_server

    with DrawerStore(tmp_cairntir_home / "memory.db", HashEmbeddingProvider(dimension=32)) as store:
        options = build_server(CairntirBackend(store)).create_initialization_options()
        assert options.server_version == __version__, "REGRESSION: handshake reports SDK version"


def test_interrupted_export_preserves_previous_file(tmp_path: Path) -> None:
    from cairntir.errors import PortableFormatError
    from cairntir.portable import write_jsonl

    target = tmp_path / "export.jsonl"
    original = b'{"previous":"complete evidence"}\n'
    target.write_bytes(original)

    def records():
        yield {"new": "first record"}
        raise OSError("reproducer: source stopped after one record")

    reported = False
    try:
        write_jsonl(records(), target)
    except (OSError, PortableFormatError):
        reported = True
    assert reported, "REGRESSION: interrupted export reported success"
    assert target.read_bytes() == original, "REGRESSION: interrupted export destroyed prior file"
    assert list(tmp_path.iterdir()) == [target]


def test_invalid_checkpoint_preserves_resumable_task(tmp_cairntir_home: Path) -> None:
    from cairntir.errors import CairntirError
    from cairntir.tasks import TaskBook

    state = {
        "expected_revision": 0,
        "idempotency_key": "valid-request",
        "status": "active",
        "completed": [],
        "outstanding": ["finish the request"],
        "next_action": "continue",
        "evidence_ids": [],
    }
    with DrawerStore(tmp_cairntir_home / "memory.db", HashEmbeddingProvider(dimension=32)) as store:
        book = TaskBook(store)
        receipt = json.loads(
            book.checkpoint(
                wing="verification",
                room="tasks",
                content="café",
                model="verification",
                checkpoint=state,
            )
        )
        before = book.resume("verification", task_id=receipt["task_id"])
        bad = state | {
            "task_id": receipt["task_id"],
            "expected_revision": 1,
            "idempotency_key": "invalid-\ud800",
        }
        reported = None
        try:
            book.checkpoint(
                wing="verification",
                room="tasks",
                content="progress",
                model="verification",
                checkpoint=bad,
            )
        except (CairntirError, UnicodeError, OverflowError) as exc:
            reported = exc
        assert book.resume("verification", task_id=receipt["task_id"]) == before
        assert isinstance(reported, CairntirError), "REGRESSION: checkpoint leaked an untyped error"


def test_reopening_current_store_preserves_database_bytes(tmp_cairntir_home: Path) -> None:
    database = tmp_cairntir_home / "memory.db"
    provider = HashEmbeddingProvider(dimension=32)
    with DrawerStore(database, provider) as store:
        saved = store.add(Drawer(wing="verification", room="evidence", content="café 日本語"))
    before = database.read_bytes()
    with DrawerStore(database, provider) as reopened:
        assert [item.content for item in reopened.list_by()] == [saved.content]
    assert database.read_bytes() == before, "REGRESSION: unchanged store reopen rewrote database"
