"""A supported patch-specific Python requirement must remain discoverable."""

import hashlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from cairntir import paladin_bootstrap as bootstrap

from . import inputs

if sys.flags.optimize:
    raise RuntimeError("Q07 acceptance requires Python assertions")

HERE = Path(__file__).resolve().parent

BASE = HERE

LOCK = BASE / "approved-pytest.lock"

LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"


def test_exact_supported_python_patch_prepares_and_runs(tmp_path: Path) -> None:
    observed_python, _ = inputs.observed_versions()
    assert sys.version_info[:3] == tuple(map(int, observed_python.split(".")))
    assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == LOCK_SHA256
    repo = HERE.parents[2]
    assert Path(bootstrap.__file__).resolve().is_relative_to(repo / "src")
    project = Path(shutil.copytree(BASE / "fixtures/clean", tmp_path / "project"))
    pyproject = project / "pyproject.toml"
    current = pyproject.read_text(encoding="utf-8")
    pinned = current.replace(
        'requires-python = ">=3.11,<3.14"', f'requires-python = "=={observed_python}"'
    )
    assert pinned != current
    pyproject.write_text(pinned, encoding="utf-8")

    inspected = bootstrap.inspect_test_infrastructure(project)
    assert inspected["status"] == "SUPPORTED"
    assert inspected["detected_python"] == f"=={observed_python}"
    prepared = bootstrap.prepare_test_bootstrap(
        project,
        tmp_path / "bootstrap",
        **inputs.settings(),
    )
    assert prepared["status"] == "PREPARED"
    command = prepared["command"]
    result = subprocess.run(  # noqa: S603 - Execute the owned bootstrap's exact returned command.
        command["argv"],
        cwd=command["cwd"],
        env=command["env"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = ET.parse(command["junit_path"]).findall(".//testcase")  # noqa: S314 - Owned pytest report.
    assert len(cases) == 3
    assert all(case.find("failure") is None and case.find("error") is None for case in cases)
