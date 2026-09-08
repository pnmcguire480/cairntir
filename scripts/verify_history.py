"""Run behavioral regressions against actual pre-fix and fixed Git trees."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = "tests/verification/test_historical_regressions.py"
CASES = (
    (
        "mcp-version",
        "60ccbbf",
        TEST,
        "test_handshake_identifies_cairntir",
        "REGRESSION: handshake reports SDK version",
    ),
    (
        "export-atomicity",
        "a67c000",
        TEST,
        "test_interrupted_export_preserves_previous_file",
        "REGRESSION: interrupted export destroyed prior file",
    ),
    (
        "checkpoint-text",
        "d88beab",
        TEST,
        "test_invalid_checkpoint_preserves_resumable_task",
        "REGRESSION: checkpoint leaked an untyped error",
    ),
    (
        "store-reopen",
        "e27fe04",
        TEST,
        "test_reopening_current_store_preserves_database_bytes",
        "REGRESSION: unchanged store reopen rewrote database",
    ),
    (
        "backup-ownership",
        "5584ff7",
        "tests/acceptance/test_backup_worker_ownership.py",
        "test_orphan_worker_never_removes_a_live_replacement_attempt",
        "orphan worker deleted another live attempt's staging directory",
    ),
)


def command(args: list[str], *, cwd: Path, env: dict[str, str] | None = None):
    """Bound every child and retain both streams for diagnosis."""
    return subprocess.run(  # noqa: S603 - explicit verification commands, no shell
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def behavior_proved(xml: Path, returncode: int, witness: str | None) -> bool:
    """Accept one passing control or one specific behavioral assertion failure."""
    if not xml.is_file():
        return False
    cases = ET.parse(xml).findall(".//testcase")  # noqa: S314 - local pytest output
    if len(cases) != 1 or cases[0].findall("error") or cases[0].findall("skipped"):
        return False
    failures = cases[0].findall("failure")
    if witness is None:
        return returncode == 0 and not failures
    if returncode != 1 or len(failures) != 1:
        return False
    detail = failures[0].text or ""
    return witness in detail and "AssertionError" in detail


def run(output: Path) -> bool:
    """Require one behavioral failure before each fix and a passing fixed control."""
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, fix, test, node, witness in CASES:
        for phase, ref in (("broken", fix + "^"), ("fixed", fix)):
            resolved = command(["git", "rev-parse", ref], cwd=ROOT)
            if resolved.returncode:
                raise RuntimeError(resolved.stderr)
            commit = resolved.stdout.strip()
            with tempfile.TemporaryDirectory(prefix="cairntir-history-", dir=output) as temporary:
                checkout = Path(temporary)
                archive = checkout / "source.zip"
                result = command(
                    ["git", "archive", "--format=zip", f"--output={archive}", commit, "src"],
                    cwd=ROOT,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr)
                with zipfile.ZipFile(archive) as package:
                    package.extractall(checkout)
                for relative in {
                    test,
                    "pyproject.toml",
                    "tests/conftest.py",
                    "tests/acceptance/test_automatic_backups.py",
                }:
                    destination = checkout / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, destination)
                home = checkout / "home"
                home.mkdir()
                environment = os.environ | {
                    "PYTHONPATH": str(checkout / "src"),
                    "PYTHONUTF8": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "CAIRNTIR_HOME": str(home),
                    "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
                    "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
                environment.pop("CAIRNTIR_GRANT_FILE", None)
                xml = output / f"{name}-{phase}.xml"
                result = command(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-c",
                        str(checkout / "pyproject.toml"),
                        "-o",
                        "addopts=",
                        "--no-cov",
                        "-q",
                        "--tb=short",
                        f"--junitxml={xml}",
                        f"{test}::{node}",
                    ],
                    cwd=checkout,
                    env=environment,
                )
                log = result.stdout + result.stderr
                (output / f"{name}-{phase}.txt").write_text(log, encoding="utf-8")
                proven = behavior_proved(
                    xml, result.returncode, witness if phase == "broken" else None
                )
                rows.append(
                    {
                        "case": name,
                        "phase": phase,
                        "commit": commit,
                        "test": f"{test}::{node}",
                        "test_sha256": hashlib.sha256((ROOT / test).read_bytes()).hexdigest(),
                        "returncode": result.returncode,
                        "behavior_proved": proven,
                        "expected_failure": witness if phase == "broken" else None,
                    }
                )
                print(f"{name} {phase}: {'PASS' if proven else 'FAIL'}", flush=True)
    (output / "history.json").write_text(
        json.dumps({"python": sys.version, "results": rows}, indent=2) + "\n", encoding="utf-8"
    )
    return all(row["behavior_proved"] for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args().output.resolve()) else 1)
