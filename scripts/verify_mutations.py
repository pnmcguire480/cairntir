"""Require outcome tests to detect specific incorrect operations in isolated copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from verify_history import ROOT, behavior_proved, command

RECOVERY = "tests/verification/test_recovery_outcomes.py"
RESTORE = RECOVERY + "::test_restored_backup_preserves_every_table_and_resumes_task"
MUTATIONS = (
    {
        "name": "discard-backup-during-status-observation",
        "file": "src/cairntir/backups.py",
        "before": (
            "def _lock(database: Path, *, create: bool) -> Iterator[bool]:\n"
            "    deadline = time.monotonic() + 0.25\n"
            "    while True:\n"
            "        with _file_lock(_paths(database)[1], create=create) as acquired:\n"
            "            if acquired or not create or time.monotonic() >= deadline:\n"
            "                yield acquired\n"
            "                return\n"
            "        time.sleep(0.01)\n"
        ),
        "after": (
            "def _lock(database: Path, *, create: bool) -> Iterator[bool]:\n"
            "    with _file_lock(_paths(database)[1], create=create) as acquired:\n"
            "        yield acquired\n"
        ),
        "test": (
            "tests/verification/test_backup_observer_outcomes.py::"
            "test_status_observation_does_not_discard_a_due_backup"
        ),
        "witness": "RECOVERY: status observer discarded due backup",
    },
    {
        "name": "reject-committed-snapshot",
        "file": "src/cairntir/memory/store.py",
        "before": "if _status != sqlite3.SQLITE_DONE and time.monotonic() >= deadline:",
        "after": "if time.monotonic() >= deadline:",
        "test": "tests/verification/test_snapshot_deadline_outcomes.py::"
        "test_snapshot_deadline_respects_sqlite_completion_and_rollback[committed]",
        "witness": "RECOVERY: committed snapshot rejected after callback delay",
    },
    {
        "name": "trim-original-transcript",
        "file": "src/cairntir/transcript.py",
        "before": 'content = payload["message"]',
        "after": 'content = payload["message"].strip()',
        "test": "tests/verification/test_transcript_failure_outcomes.py::"
        "test_recovered_request_retains_exact_whitespace_and_unicode[codex-event]",
        "witness": "RECOVERY: transcript altered original whitespace",
    },
    {
        "name": "commit-invalid-workflow-result",
        "file": "src/cairntir/memory/store.py",
        "before": "if not isinstance(result, dict):",
        "after": "if False:",
        "test": "tests/verification/test_store_failure_outcomes.py::"
        "test_nonobject_workflow_result_rolls_back_before_reporting_failure[done]",
        "witness": "RECOVERY: invalid workflow result committed its writes",
    },
    {
        "name": "discard-valid-transcript",
        "file": "src/cairntir/transcript.py",
        "before": 'with path.open("rb") as handle:\n            line = handle.readline(262_145)',
        "after": 'with path.open("r", encoding="utf-8") as handle:\n'
        "            line = handle.readline(262_145)",
        "test": "tests/verification/test_transcript_failure_outcomes.py::"
        "test_codex_valid_request_survives_invalid_utf8_later_in_the_file",
        "witness": "RECOVERY: valid transcript request was lost",
    },
    {
        "name": "omit-memory",
        "file": "src/cairntir/backups.py",
        "before": '        connection.execute("PRAGMA journal_mode=DELETE")',
        "after": '        connection.execute("PRAGMA journal_mode=DELETE")\n'
        '        connection.execute("DELETE FROM portable_records WHERE drawer_id=1")\n'
        '        connection.execute("DELETE FROM vec_drawers WHERE drawer_id=1")\n'
        '        connection.execute("DELETE FROM drawers WHERE id=1")\n'
        "        connection.commit()",
        "test": RESTORE,
        "witness": "RECOVERY: restored tables differ",
    },
    {
        "name": "omit-vector",
        "file": "src/cairntir/backups.py",
        "before": '        connection.execute("PRAGMA journal_mode=DELETE")',
        "after": '        connection.execute("PRAGMA journal_mode=DELETE")\n'
        '        connection.execute("DELETE FROM vec_drawers WHERE drawer_id=1")\n'
        "        connection.commit()",
        "test": RESTORE,
        "witness": "RECOVERY: restored tables differ",
    },
    {
        "name": "commit-instead-of-rollback",
        "file": "src/cairntir/memory/store.py",
        "before": (
            "            self._bulk_embedding = None\n            try:\n"
            "                if savepoint is None:\n                    self._conn.rollback()"
        ),
        "after": (
            "            self._bulk_embedding = None\n            try:\n"
            "                if savepoint is None:\n                    self._conn.commit()"
        ),
        "test": RECOVERY + "::test_failed_write_after_vector_insert_rolls_back_every_table",
        "witness": "RECOVERY: failed write left partial data",
    },
    {
        "name": "report-sdk-version",
        "file": "src/cairntir/mcp/server.py",
        "before": "Server(_SERVER_NAME, version=__version__)",
        "after": "Server(_SERVER_NAME)",
        "test": (
            "tests/verification/test_historical_regressions.py::test_handshake_identifies_cairntir"
        ),
        "witness": "REGRESSION: handshake reports SDK version",
    },
)


def run(output: Path) -> bool:
    """Fail for survivors, unrelated failures, skipped tests or broken controls."""
    output.mkdir(parents=True, exist_ok=True)
    inventory = command(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src"], cwd=ROOT
    )
    if inventory.returncode:
        raise RuntimeError(inventory.stderr)
    rows = []
    for mutation in MUTATIONS:
        for phase in ("control", "mutant"):
            with tempfile.TemporaryDirectory(prefix="mutation-", dir=output) as temporary:
                checkout = Path(temporary)
                for relative in inventory.stdout.splitlines():
                    destination = checkout / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, destination)
                shutil.copytree(
                    ROOT / "tests/verification",
                    checkout / "tests/verification",
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
                shutil.copyfile(ROOT / "tests/conftest.py", checkout / "tests/conftest.py")
                shutil.copyfile(ROOT / "pyproject.toml", checkout / "pyproject.toml")
                target = checkout / mutation["file"]
                original = target.read_text(encoding="utf-8")
                if original.count(mutation["before"]) != 1:
                    raise RuntimeError(f"mutation no longer has one target: {mutation['name']}")
                if phase == "mutant":
                    target.write_text(
                        original.replace(mutation["before"], mutation["after"]),
                        encoding="utf-8",
                        newline="\n",
                    )
                home = checkout / "home"
                home.mkdir()
                environment = os.environ | {
                    "PYTHONPATH": str(checkout / "src"),
                    "CAIRNTIR_HOME": str(home),
                    "PYTHONUTF8": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
                    "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
                environment.pop("CAIRNTIR_GRANT_FILE", None)
                label = f"{mutation['name']}-{phase}"
                xml = output / f"{label}.xml"
                result = command(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-o",
                        "addopts=",
                        "--no-cov",
                        "-q",
                        "--tb=short",
                        f"--junitxml={xml}",
                        mutation["test"],
                    ],
                    cwd=checkout,
                    env=environment,
                )
                (output / f"{label}.txt").write_text(
                    result.stdout + result.stderr, encoding="utf-8"
                )
                proved = behavior_proved(
                    xml, result.returncode, mutation["witness"] if phase == "mutant" else None
                )
                rows.append(
                    {
                        "mutation": mutation["name"],
                        "phase": phase,
                        "proved": proved,
                        "returncode": result.returncode,
                        "test": mutation["test"],
                        "source_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "test_sha256": hashlib.sha256(
                            (ROOT / mutation["test"].split("::")[0]).read_bytes()
                        ).hexdigest(),
                    }
                )
                print(f"{label}: {'PASS' if proved else 'FAIL'}", flush=True)
    (output / "mutations.json").write_text(
        json.dumps({"results": rows}, indent=2) + "\n", encoding="utf-8"
    )
    return all(row["proved"] for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args().output.resolve()) else 1)
