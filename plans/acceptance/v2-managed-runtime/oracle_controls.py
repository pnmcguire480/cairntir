"""Qualify the independent child's commit boundary without candidate code."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def main():
    with tempfile.TemporaryDirectory(prefix="managed-oracle-") as directory:
        root = Path(directory)
        database = root / "oracle.db"
        marker = root / "marker.jsonl"
        release = root / "release"
        release.touch()
        action_id = str(uuid4())
        request = {"claim": "  Public café\r\n", "predicted_outcome": "Committed before marker"}
        intent = {"action_id": action_id, "prediction_drawer_id": 1, "request": request}
        argv = [
            sys.executable,
            "-X",
            "utf8",
            str(Path(__file__).with_name("process_child.py")),
            "--database",
            str(database),
            "--action-id",
            action_id,
            "--marker",
            str(marker),
            "--release",
            str(release),
            "--done",
            str(root / "done"),
        ]
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                "CREATE TABLE drawers(id INTEGER PRIMARY KEY, content TEXT, claim TEXT, predicted_outcome TEXT);"
                "CREATE TABLE workflow_runs(operation TEXT, state TEXT, result TEXT);"
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO drawers VALUES(1, ?, ?, ?)",
                (request["claim"], request["claim"], request["predicted_outcome"]),
            )
            connection.execute(
                "INSERT INTO workflow_runs VALUES('managed.dispatch.v1', 'committed', ?)",
                (json.dumps(intent),),
            )

            def child():
                return subprocess.run(
                    argv,
                    cwd=root,
                    env={**os.environ, "PYTHONUTF8": "1"},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=10,
                    check=False,
                )

            uncommitted = child()
            assert uncommitted.returncode == 23, uncommitted.stderr
            assert "NO UNIQUE COMMITTED PRE-ACTION INTENT" in uncommitted.stderr
            assert not marker.exists(), "Uncommitted writer incorrectly passed child oracle"
            connection.commit()
            committed = child()
            assert committed.returncode == 0, committed.stderr
            records = [json.loads(line) for line in marker.read_text(encoding="utf-8").splitlines()]
            assert len(records) == 1
            assert records[0]["claim"] == request["claim"]
            assert records[0]["action_id"] == action_id
            assert records[0]["prediction_drawer_id"] == 1
            assert (root / "done").read_text(encoding="utf-8") == "done"
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "uncommitted_control": {
                            "exit_code": uncommitted.returncode,
                            "stderr": uncommitted.stderr.strip(),
                            "markers": 0,
                        },
                        "committed_control": {
                            "exit_code": committed.returncode,
                            "stdout": committed.stdout.strip(),
                            "markers": 1,
                        },
                        "candidate_imported": False,
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
