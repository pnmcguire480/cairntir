"""Integration tests for the capture daemon and spool format."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.daemon import (
    CaptureDaemon,
    parse_capture,
    pending_files,
    spool_dir,
    write_capture,
)
from cairntir.errors import MCPError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "daemon.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


@pytest.fixture()
def spool(tmp_path: Path) -> Path:
    return spool_dir(tmp_path)


def test_spool_dir_creates_directory_and_failed_subdir(tmp_path: Path) -> None:
    path = spool_dir(tmp_path)
    assert path.exists()
    assert (path / "failed").exists()


def test_write_capture_produces_readable_json(spool: Path) -> None:
    path = write_capture(spool, wing="cairntir", room="decisions", content="ship phase 4")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["wing"] == "cairntir"
    assert payload["content"] == "ship phase 4"
    assert payload["layer"] == "on_demand"


def test_pending_files_returns_in_arrival_order(spool: Path) -> None:
    first = write_capture(spool, wing="cairntir", room="r1", content="a")
    second = write_capture(spool, wing="cairntir", room="r1", content="b")
    third = write_capture(spool, wing="cairntir", room="r1", content="c")
    assert [p.name for p in pending_files(spool)] == [
        first.name,
        second.name,
        third.name,
    ]


def test_parse_capture_rejects_bad_json(spool: Path) -> None:
    bad = spool / "00000000000000000001-abcd1234.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(MCPError):
        parse_capture(bad)


def test_parse_capture_rejects_missing_keys(spool: Path) -> None:
    bad = spool / "00000000000000000002-abcd1234.json"
    bad.write_text(json.dumps({"wing": "cairntir"}), encoding="utf-8")
    with pytest.raises(MCPError):
        parse_capture(bad)


def test_tick_persists_spooled_drawers_and_deletes_files(store: DrawerStore, spool: Path) -> None:
    write_capture(
        spool,
        wing="cairntir",
        room="decisions",
        content="chose sqlite-vec",
        layer="essential",
        metadata={"source": "daemon-test"},
    )
    write_capture(spool, wing="cairntir", room="notes", content="amnesia killer shipping")

    daemon = CaptureDaemon(store, spool)
    processed = daemon.tick()

    assert processed == 2
    assert daemon.stats.processed == 2
    assert daemon.stats.failed == 0
    assert pending_files(spool) == []

    results = store.list_by(wing="cairntir", limit=10)
    contents = {d.content for d in results}
    assert contents == {"chose sqlite-vec", "amnesia killer shipping"}

    essentials = store.list_by(wing="cairntir", layer=Layer.ESSENTIAL)
    assert len(essentials) == 1
    assert essentials[0].metadata == {"source": "daemon-test"}


def test_tick_quarantines_malformed_files(store: DrawerStore, spool: Path) -> None:
    bad = spool / "00000000000000000099-deadbeef.json"
    bad.write_text("not json", encoding="utf-8")

    daemon = CaptureDaemon(store, spool)
    processed = daemon.tick()

    assert processed == 0
    assert daemon.stats.failed == 1
    assert not bad.exists()
    quarantined = list((spool / "failed").iterdir())
    assert any(p.name == bad.name for p in quarantined)
    assert any(p.suffix == ".error" for p in quarantined)


def test_tick_is_idempotent_when_spool_empty(store: DrawerStore, spool: Path) -> None:
    daemon = CaptureDaemon(store, spool)
    assert daemon.tick() == 0
    assert daemon.tick() == 0
    assert daemon.stats.processed == 0


def test_run_loop_exits_on_request_stop(store: DrawerStore, spool: Path) -> None:
    write_capture(spool, wing="cairntir", room="notes", content="stop me")
    daemon = CaptureDaemon(store, spool, poll_interval=0.01)

    async def drive() -> None:
        task = asyncio.create_task(daemon.run())
        await asyncio.sleep(0.05)
        daemon.request_stop()
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(drive())
    assert daemon.stats.processed >= 1
    assert pending_files(spool) == []
