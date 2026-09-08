from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from test_recovery_outcomes import contents

from cairntir import backups


def test_status_observation_does_not_discard_a_due_backup(seeded, tmp_path, monkeypatch):
    database, _, _ = seeded
    backups.configure(database, tmp_path / "copies")
    before = contents(database)
    ready = tmp_path / "observing"
    observer_code = """
import sys
from pathlib import Path
from cairntir import backups
original = backups._public
def paused(*args, **kwargs):
    Path(sys.argv[2]).write_text('observing')
    input()
    return original(*args, **kwargs)
backups._public = paused
backups.status(Path(sys.argv[1]))
print('RELEASED', flush=True)
"""
    observer = subprocess.Popen(  # noqa: S603 - isolated status observer, explicit interpreter
        [sys.executable, "-c", observer_code, str(database), str(ready)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=os.environ.copy(),
    )
    lock = backups._file_lock
    observed_contention = []

    @contextmanager
    def release_observer(path, **kwargs):
        with lock(path, **kwargs) as acquired:
            if not acquired and not observed_contention:
                observed_contention.append(True)
                stdout, stderr = observer.communicate("RELEASE\n", timeout=10)
                assert observer.returncode == 0, stderr
                assert "RELEASED" in stdout
            yield acquired

    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert observer.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        with monkeypatch.context() as patch:
            patch.setattr(backups, "_file_lock", release_observer)
            result = backups.run(database, force=False)
        assert observed_contention
        assert result["status"] == "created", "RECOVERY: status observer discarded due backup"
        assert contents(Path(result["snapshot"]["path"]), standalone=True) == before
        assert contents(database) == before
        assert not backups.status(database)["in_progress"]
        assert len(backups.status(database)["snapshots"]) == 1
    finally:
        if observer.poll() is None:
            observer.kill()
        observer.communicate(timeout=10)
