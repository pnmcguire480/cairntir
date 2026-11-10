"""Public Dream durability and concurrency acceptance on disposable stores."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import test_dream_pilot_r1 as pilot


def _start_tick(home: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(
        CAIRNTIR_HOME=str(home),
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HTTP_PROXY="",
        HTTPS_PROXY="",
        ALL_PROXY="",
        NO_PROXY="127.0.0.1,localhost",
        PYTHONPATH=str(pilot.ROOT / "src") + os.pathsep + env.get("PYTHONPATH", ""),
    )
    return subprocess.Popen(  # noqa: S603 - fixed Python executable invokes the public CLI
        [sys.executable, "-c", pilot.BOOT, "dream", "tick", "--timeout-seconds", "10"],
        cwd=pilot.ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _finished(process: subprocess.Popen[str], timeout: float = 12) -> dict[str, Any]:
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    assert process.returncode == 0, stderr
    receipt = json.loads(stdout)
    assert receipt["schema"] == "cairntir.dream-tick.v1"
    return receipt


def _wait_for_post(calls: list[dict[str, Any]], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert calls, "the first tick never reached the fake local model"


def test_backup_snapshot_restores_dream_config_receipt_and_pending_candidate(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source_id = pilot._seed(home, "alpha", "Retry policy evidence survives backup.")
    with pilot._server() as (endpoint, calls):
        pilot._enable(home, endpoint)
        first = pilot._tick(home)
        assert first["status"] == "candidate"
        assert len(calls) == 1
        original = pilot._status(home)

        backup_dir = tmp_path / "backups"
        configured = pilot._json(home, "backup", "configure", str(backup_dir))
        assert configured["enabled"] is True
        created = pilot._json(home, "backup", "run", timeout=20)
        assert created["status"] == "created"
        snapshot = Path(created["snapshot"]["path"])
        assert snapshot.is_file()

        restored = tmp_path / "restored"
        restored.mkdir()
        shutil.copy2(snapshot, restored / "cairntir.db")
        status = pilot._status(restored)
        assert status["enabled"] is True
        assert status["last_tick"]["receipt_id"] == first["receipt_id"]
        assert status["pending_candidates"] == 1
        candidate = pilot._json(restored, "dream", "candidate", first["candidate_id"])
        assert candidate["status"] == "pending"
        assert candidate["evidence_ids"] == [source_id]
        assert status["last_tick"] == original["last_tick"]
        assert pilot._drawer_ids(restored) == [source_id]


def test_concurrent_ticks_for_one_evidence_make_one_model_call_and_candidate(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source_id = pilot._seed(home, "alpha", "One unresolved retry incident.")
    with pilot._server(delay_seconds=5) as (endpoint, calls):
        pilot._enable(home, endpoint)
        first_process = _start_tick(home)
        second_process: subprocess.Popen[str] | None = None
        try:
            _wait_for_post(calls)
            second_process = _start_tick(home)
            first = _finished(first_process)
            second = _finished(second_process)
        finally:
            for process in (first_process, second_process):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate()
        candidates = [item["candidate_id"] for item in (first, second) if item["candidate_id"]]
        assert len(calls) == 1
        assert len(set(candidates)) == 1
        assert pilot._status(home)["pending_candidates"] == 1
        candidate = pilot._json(home, "dream", "candidate", candidates[0])
        assert candidate["evidence_ids"] == [source_id]


def test_stalled_local_model_does_not_hold_sqlite_writer_lock(tmp_path: Path) -> None:
    home = tmp_path / "home"
    pilot._seed(home, "alpha", "Dream may inspect this evidence.")
    with pilot._server(delay_seconds=6) as (endpoint, calls):
        pilot._enable(home, endpoint)
        process = _start_tick(home)
        try:
            _wait_for_post(calls)
            with ThreadPoolExecutor(max_workers=1) as executor:
                start = time.monotonic()
                written = executor.submit(
                    pilot._seed, home, "beta", "A normal memory write during inference."
                )
                new_id = written.result(timeout=2)
                assert time.monotonic() - start < 2
            assert new_id in pilot._drawer_ids(home)
            assert _finished(process)["status"] == "candidate"
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
