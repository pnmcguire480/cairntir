"""An actual interpreter must refuse a different exact patch before installing."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from cairntir import paladin_bootstrap as bootstrap

from . import inputs


def _inventory(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_wrong_current_python_patch_refuses_before_install(tmp_path, monkeypatch):
    settings = inputs.settings()
    python = Path(settings["python_executable"]).resolve(strict=True)
    assert python == Path(sys.executable).resolve(strict=True)
    observation = subprocess.run(  # noqa: S603 - Explicitly configured local interpreter.
        [str(python), "-I", "-B", "--version"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert observation.returncode == 0
    match = re.fullmatch(
        r"Python (3)\.(11|12|13)\.([0-9]+)",
        (observation.stdout + observation.stderr).strip(),
    )
    assert match is not None
    actual = tuple(map(int, match.groups()))
    assert actual == tuple(sys.version_info[:3])
    wrong = f"=={actual[0]}.{actual[1]}.{actual[2] + 1}"
    package = Path(inputs.__file__).resolve().parent
    project = Path(shutil.copytree(package / "fixtures/clean", tmp_path / "project"))
    pyproject = project / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    replacement = original.replace(
        'requires-python = ">=3.11,<3.14"', f'requires-python = "{wrong}"'
    )
    assert replacement != original
    pyproject.write_text(replacement, encoding="utf-8")
    inspected = bootstrap.inspect_test_infrastructure(project)
    assert inspected["status"] == "SUPPORTED"
    assert inspected["detected_python"] == wrong
    lock = Path(settings["approved_requirements"])
    wheels = Path(settings["wheelhouse"])
    before_source, before_wheels, before_lock = (
        _inventory(project),
        _inventory(wheels),
        lock.read_bytes(),
    )
    assert hashlib.sha256(before_lock).hexdigest() == (
        "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"
    )
    before_python = hashlib.sha256(python.read_bytes()).hexdigest()
    real_popen = subprocess.Popen
    dispatched = []

    def no_install(argv, *args, **kwargs):
        assert not isinstance(argv, (str, bytes, os.PathLike))
        tokens = [str(part).lower() for part in argv]
        assert tokens
        assert not {"venv", "pip", "install", "sync", "build"}.intersection(tokens), argv
        assert Path(tokens[0]).stem != "pip"
        assert not any(token.startswith(("http://", "https://")) for token in tokens)
        dispatched.append(Path(argv[0]).resolve(strict=True))
        return real_popen(argv, *args, **kwargs)

    output = tmp_path / "bootstrap"
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", no_install)
        result = bootstrap.prepare_test_bootstrap(project, output, **settings)

    assert python in dispatched
    assert result["status"] == "BLOCKED"
    assert result["blocker"]["code"] == "UNSUPPORTED_PYTHON"
    assert _inventory(project) == before_source
    assert _inventory(wheels) == before_wheels
    assert lock.read_bytes() == before_lock
    assert hashlib.sha256(python.read_bytes()).hexdigest() == before_python
    assert not list(output.rglob("pyvenv.cfg"))
    assert not list(output.rglob("PREPARED.json"))
    for path in output.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        assert not (isinstance(payload, dict) and payload.get("status") == "PREPARED")
