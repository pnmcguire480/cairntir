"""Resolve real Q07 inputs and independently observe the selected tool versions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from cairntir import paladin_bootstrap as bootstrap

HERE = Path(__file__).resolve().parent
LOCK = HERE / "approved-pytest.lock"
LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"


def settings() -> dict[str, Path | str]:
    assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == LOCK_SHA256
    assert Path(bootstrap.__file__).resolve().is_relative_to(HERE.parents[2] / "src")
    python = Path(sys.executable).resolve(strict=True)
    available_uv = shutil.which("uv")
    assert available_uv is not None, "Real bootstrap controls require the available uv executable"
    uv = Path(available_uv).resolve(strict=True)
    configured = os.environ.get("CAIRNTIR_Q07_WHEELHOUSE")
    assert configured, "CAIRNTIR_Q07_WHEELHOUSE must name the six approved real wheels"
    wheelhouse = Path(configured).resolve(strict=True)
    assert wheelhouse.is_dir()
    approved = json.loads((HERE / "wheel-inputs.json").read_bytes())
    assert approved["approved_lock_sha256"] == LOCK_SHA256
    wheels = approved["wheels"]
    assert {path.name for path in wheelhouse.iterdir()} == set(wheels)
    for name, expected in wheels.items():
        path = wheelhouse / name
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == expected["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
    return {
        "python_executable": python,
        "uv_executable": uv,
        "approved_requirements": LOCK,
        "approved_sha256": LOCK_SHA256,
        "wheelhouse": wheelhouse,
    }


@lru_cache(maxsize=1)
def observed_versions() -> tuple[str, str]:
    current = settings()
    observations = []
    for command, pattern in (
        ([str(current["python_executable"]), "-I", "-B", "--version"], r"Python (3\.\d+\.\d+)"),
        ([str(current["uv_executable"]), "--version"], r"uv (0\.\d+\.\d+)(?: \([^\r\n]+\))?"),
    ):
        result = subprocess.run(  # noqa: S603 - Independently observe explicitly selected local tools.
            command, capture_output=True, text=True, timeout=20, check=False
        )
        assert result.returncode == 0 and not result.stderr.strip(), result.stderr
        match = re.fullmatch(pattern, result.stdout.strip())
        assert match is not None, result.stdout
        observations.append(match.group(1))
    actual_python = tuple(map(int, observations[0].split(".")))
    assert actual_python == sys.version_info[:3]
    assert actual_python[0] == 3 and actual_python[1] in (11, 12, 13)
    return observations[0], observations[1]
