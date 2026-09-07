"""Deterministic orphan-worker overlap regression; no snapshot logic is mocked."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from test_automatic_backups import _state

from cairntir import backups
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ROOT = Path(__file__).resolve().parents[2]
HOOK = """import os,time
from pathlib import Path
from cairntir import backups
control = Path(os.environ["BACKUP_OWNERSHIP_CONTROL"])
role = os.environ["BACKUP_OWNERSHIP_ROLE"]
publish = backups._publish_snapshot
prepare = backups._prepare_snapshot
def wait(name):
    limit = time.monotonic() + 12
    while not (control / name).exists():
        if time.monotonic() >= limit:
            raise RuntimeError("ownership test barrier exceeded deadline")
        time.sleep(.005)
def publish_gate(*args, **kwargs):
    if role != "old":
        return publish(*args, **kwargs)
    (control / "old-entered").write_text(str(os.getpid()),encoding="utf-8")
    try:
        wait("old-release")
        return publish(*args, **kwargs)
    finally:
        (control / "old-done").touch()
def prepare_gate(source, destination, deadline):
    if role == "replacement":
        (control / "replacement-path").write_text(str(destination),encoding="utf-8")
        (control / "replacement-entered").touch()
        wait("replacement-release")
    return prepare(source, destination, deadline)
backups._publish_snapshot = publish_gate
backups._prepare_snapshot = prepare_gate
"""
COORDINATOR = (
    "import json,sys; from pathlib import Path; from cairntir import backups; "
    "print(json.dumps(backups.run(Path(sys.argv[1]),force=False)),flush=True)"
)


def _wait(path: Path, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, f"barrier not reached: {path.name}"
        time.sleep(0.005)


def test_orphan_worker_never_removes_a_live_replacement_attempt(tmp_cairntir_home: Path) -> None:
    database = tmp_cairntir_home / "cairntir.db"
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store.add(
            Drawer(
                wing="worker-ownership", room="evidence", content="Keep committed café evidence."
            )
        )
    before = _state(database)
    destination = tmp_cairntir_home / "backups"
    backups.configure(database, destination)
    control = tmp_cairntir_home / "barriers"
    control.mkdir()
    (control / "sitecustomize.py").write_text(HOOK, encoding="utf-8", newline="\n")
    processes = []

    def launch(role: str) -> subprocess.Popen[str]:
        environment = os.environ | {
            "PYTHONPATH": os.pathsep.join((str(control), str(ROOT / "src"))),
            "PYTHONIOENCODING": "utf-8",
            "BACKUP_OWNERSHIP_CONTROL": str(control),
            "BACKUP_OWNERSHIP_ROLE": role,
        }
        process = subprocess.Popen(  # noqa: S603 - fixed isolated test process
            [sys.executable, "-c", COORDINATOR, str(database)],
            env=environment,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        processes.append(process)
        return process

    manual = destination / "manual-baseline.db"
    try:
        old = launch("old")
        _wait(control / "old-entered")
        old.kill()
        old.wait(timeout=3)
        destination.mkdir(exist_ok=True)
        manual.write_bytes(database.read_bytes())
        manual_hash = hashlib.sha256(manual.read_bytes()).hexdigest()
        replacement = launch("replacement")
        deadline = time.monotonic() + 8
        while not (control / "replacement-entered").exists() and replacement.poll() is None:
            assert time.monotonic() < deadline, "replacement neither proceeded nor returned busy"
            time.sleep(0.005)
        staged = None
        marker = None
        marker_bytes = None
        if (control / "replacement-entered").exists():
            staged = Path((control / "replacement-path").read_text(encoding="utf-8")).parent
            marker = staged / "pending.json"
            assert marker.is_file(), "replacement must own a real initialized staging directory"
            marker_bytes = marker.read_bytes()
        else:
            stdout, stderr = replacement.communicate(timeout=3)
            assert replacement.returncode == 0, stderr
            assert json.loads(stdout)["status"] == "busy"
        (control / "old-release").touch()
        _wait(control / "old-done")
        if staged is not None:
            assert staged.is_dir(), "orphan worker deleted another live attempt's staging directory"
            assert marker is not None and marker.read_bytes() == marker_bytes
            (control / "replacement-release").touch()
            stdout, stderr = replacement.communicate(timeout=15)
            assert replacement.returncode == 0, stderr
            receipt = json.loads(stdout)
        else:
            deadline = time.monotonic() + 8
            while True:
                receipt = backups.run(database, force=False)
                if receipt["status"] != "busy":
                    break
                assert time.monotonic() < deadline, "orphan ownership was never released"
                time.sleep(0.01)
        assert receipt["status"] == "created", receipt
        copied = Path(receipt["snapshot"]["path"])
        assert _state(copied, standalone=True) == before
        assert _state(database) == before
        assert hashlib.sha256(manual.read_bytes()).hexdigest() == manual_hash
        assert not backups.status(database)["in_progress"]
    finally:
        (control / "old-release").touch()
        (control / "replacement-release").touch()
        if (control / "old-entered").exists():
            _wait(control / "old-done", timeout=15)
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=20)
