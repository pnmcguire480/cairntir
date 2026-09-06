"""Reproduce independent source-purity and committed-WAL verification."""

# ruff: noqa: S101

from __future__ import annotations

import hashlib
import json
import mmap
import runpy
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from cairntir.errors import CairntirError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ROOT = Path(__file__).resolve().parents[1]
tree = runpy.run_path(str(ROOT / "tests/unit/test_context_boundaries.py"))["_tree"]


def embedder() -> HashEmbeddingProvider:
    """Use a deterministic local provider for filesystem proofs."""
    return HashEmbeddingProvider(dimension=32)


def mapped_tree(root: Path) -> dict[str, tuple[int, str]]:
    """Observe locked SHM bytes through a read-only mapping."""
    result = {}
    for path in (root, *root.rglob("*")):
        stamp = path.stat().st_mtime_ns
        digest = "<directory>"
        if path.is_file():
            with path.open("rb") as handle:
                if path.stat().st_size:
                    with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as contents:
                        digest = hashlib.sha256(contents).hexdigest()
                else:
                    digest = hashlib.sha256(b"").hexdigest()
        result[str(path.relative_to(root))] = stamp, digest
    return result


def reject_busy(database: Path, scratch: Path) -> dict[str, object]:
    """Require a typed busy response and complete private cleanup."""
    try:
        with DrawerStore(database, embedder(), read_only=True):
            raise AssertionError("A live WAL connection must produce a typed retry response")
    except CairntirError as error:
        assert "busy" in str(error).lower() or "lock" in str(error).lower()
        receipt = {"error_type": type(error).__name__, "detail": str(error)}
    assert not list(scratch.iterdir()), "busy-source rejection leaked its private snapshot"
    return {**receipt, "private_snapshot_removed": True}


def verify_busy(database: Path, source: Path, scratch: Path) -> dict[str, object]:
    """Check source identity around a rejected read."""
    before = tree(source)
    receipt = reject_busy(database, scratch)
    assert tree(source) == before, "busy-source rejection changed source files"
    return {**receipt, "source_unchanged": True}


def main() -> None:
    """Run isolated cold, busy and orphan-WAL proofs."""
    record: dict[str, object] = {
        "probe_kind": "independent isolated source-purity and WAL visibility verification",
        "runtime_store_sha256": hashlib.sha256(
            (ROOT / "src/cairntir/memory/store.py").read_bytes()
        ).hexdigest(),
        "frozen_snapshot_helper_sha256": hashlib.sha256(
            (ROOT / "tests/unit/test_context_boundaries.py").read_bytes()
        ).hexdigest(),
    }
    with tempfile.TemporaryDirectory(
        prefix="foundation-repair1-probe-", dir=ROOT / ".cairntir"
    ) as name:
        workspace = Path(name)
        source, scratch = workspace / "source", workspace / "private-snapshots"
        source.mkdir()
        scratch.mkdir()
        database = source / "memory.db"
        previous_tempdir = tempfile.tempdir
        tempfile.tempdir = str(scratch)
        try:
            with DrawerStore(database, embedder()) as writer:
                baseline = writer.add(
                    Drawer(
                        wing="wal-proof", room="evidence", content="Baseline committed evidence."
                    )
                )
            before = tree(source)
            with DrawerStore(database, embedder(), read_only=True) as reader:
                assert [
                    drawer.id for drawer, _ in reader.context_candidates(wing="wal-proof")[0]
                ] == [baseline.id]
                assert tree(source) == before
            assert tree(source) == before
            assert not list(scratch.iterdir())
            record["cold_quiescent"] = {
                "evidence_visible": True,
                "source_unchanged_during_and_after_read": True,
                "private_snapshot_removed": True,
            }

            with DrawerStore(database, embedder()) as writer:
                writer.add(
                    Drawer(
                        wing="wal-proof", room="evidence", content="Committed live-WAL evidence."
                    )
                )
                record["idle_live_wal_connection"] = verify_busy(database, source, scratch)
                with closing(sqlite3.connect(database)) as transaction:
                    transaction.execute("BEGIN IMMEDIATE")
                    before = mapped_tree(source)
                    receipt = reject_busy(database, scratch)
                    assert mapped_tree(source) == before
                    transaction.rollback()
                    record["active_write_transaction"] = {
                        **receipt,
                        "source_unchanged_during_rejected_read": True,
                        "observer": (
                            "read-only mmap preserves full hashes/mtimes while Windows "
                            "byte locks prevent ordinary SHM reads"
                        ),
                    }

            marker = "This exact newly committed evidence exists only in the orphan WAL."
            child = "\n".join(
                [
                    "import os, sys",
                    "from pathlib import Path",
                    "from cairntir.memory.store import DrawerStore",
                    "from cairntir.memory.embeddings import HashEmbeddingProvider",
                    "from cairntir.memory.taxonomy import Drawer",
                    "store = DrawerStore(Path(sys.argv[1]), HashEmbeddingProvider(dimension=32))",
                    "saved = store.add(Drawer(wing='wal-proof', room='evidence', "
                    "content=sys.argv[2]))",
                    "print(saved.id, flush=True)",
                    "os._exit(0)",
                ]
            )
            child_result = subprocess.run(  # noqa: S603 - fixed synthetic child and isolated paths
                [sys.executable, "-c", child, str(database), marker],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            committed_id = int(child_result.stdout.strip())
            assert marker.encode() not in database.read_bytes()
            assert marker.encode() in database.with_name(database.name + "-wal").read_bytes()
            before = tree(source)
            with DrawerStore(database, embedder(), read_only=True) as reader:
                records = reader.context_candidates(wing="wal-proof")[0]
                observed = {drawer.id: drawer.content for drawer, _ in records}
                assert observed[committed_id] == marker
                assert tree(source) == before
            assert tree(source) == before
            assert not list(scratch.iterdir())
            record["orphan_committed_wal"] = {
                "new_content_absent_from_main_database": True,
                "new_content_present_in_wal": True,
                "committed_id": committed_id,
                "exact_content_visible_through_readonly_store": True,
                "source_unchanged_during_and_after_read": True,
                "private_snapshot_removed": True,
            }
        finally:
            tempfile.tempdir = previous_tempdir
    assert not workspace.exists()
    record["owned_probe_workspace_cleaned"] = True
    record["verdict"] = "PASS"
    (ROOT / "plans/v2-foundation-round1-wal-probe.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
