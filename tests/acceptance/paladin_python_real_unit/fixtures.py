"""Narrow current-input binding for the original three real-tool scenarios."""

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

from paladin_python_unit import fixtures as shared

FAMILIES = shared.FAMILIES
HERE = Path(__file__).resolve().parent
DISTRIBUTIONS = (
    "mypy",
    "mypy-extensions",
    "typing-extensions",
    "pathspec",
    "librt",
    "pytest",
    "pytest-cov",
    "coverage",
    "ruff",
    "packaging",
    "pluggy",
    "iniconfig",
    "pygments",
) + (("colorama",) if os.name == "nt" else ())


@lru_cache(maxsize=1)
def current_inputs():
    configured = os.environ.get("CAIRNTIR_PALADIN_PLATFORM")
    if not configured:
        raise RuntimeError(
            "Actual PALADIN input preparation is required: fresh owned seven-tool "
            "profile and bounded current CI-extra RECORD closure; "
            "Q05's three tools are insufficient"
        )
    path = Path(configured).resolve(strict=True)
    platform = json.loads(path.read_bytes())
    tools = {tool["id"]: tool for tool in platform["tools"]}
    if len(platform["tools"]) != 7 or set(tools) != {
        "python",
        "ruff",
        "mypy",
        "pytest",
        "pytest-cov",
        "coverage",
        "uv",
    }:
        raise RuntimeError("A newly qualified actual seven-tool PALADIN profile is required")
    manifest = json.loads((HERE / "INPUTS.json").read_bytes())
    actual = {
        file.relative_to(HERE / "fixture").as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in (HERE / "fixture").rglob("*")
        if file.is_file()
    }
    assert actual == {row["path"]: row["sha256"] for row in manifest["files"]}
    q05 = json.loads(Path(os.environ["CAIRNTIR_Q05_PLATFORM"]).read_bytes())
    q05_tools = {tool["id"]: tool for tool in q05["tools"]}
    assert tools["python"]["sha256"] == q05_tools["python"]["sha256"]
    assert tools["python"]["version"] == q05_tools["python"]["version"]
    assert tools["ruff"]["version"] == q05_tools["ruff"]["version"]
    assert tools["uv"]["executable"] == q05["uv"]
    assert tools["uv"]["sha256"] == q05_tools["uv"]["sha256"]
    expected = {name: importlib.metadata.version(name) for name in DISTRIBUTIONS}
    python = Path(platform["python"]).resolve(strict=True)
    payload = Path(tools["python"]["payload_root"]).resolve(strict=True)
    assert python.is_relative_to(payload) and not python.is_symlink()
    assert hashlib.sha256(python.read_bytes()).hexdigest() == tools["python"]["sha256"]
    probe_code = (
        "import importlib,importlib.metadata,json,sys;names=json.loads(sys.argv[1]);"
        "modules=('ruff','mypy','pytest','pytest_cov','coverage','packaging');"
        "print(json.dumps({'python':sys.executable,'version':sys.version.split()[0],"
        "'versions':{n:importlib.metadata.version(n)for n in names},"
        "'origins':{n:importlib.import_module(n).__file__ for n in modules}}))"
    )
    probe = subprocess.run(  # noqa: S603 - Independently observe explicitly selected prepared tools.
        [str(python), "-I", "-B", "-c", probe_code, json.dumps(DISTRIBUTIONS)],
        env=platform["environment"]["values"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    observed = json.loads(probe.stdout)
    assert Path(observed["python"]).resolve() == python
    assert observed["version"] == sys.version.split()[0] == tools["python"]["version"]
    assert observed["versions"] == expected
    assert all(
        Path(origin).resolve().is_relative_to(payload) for origin in observed["origins"].values()
    )
    for name in ("ruff", "mypy", "pytest", "pytest-cov", "coverage"):
        assert tools[name]["version"] == expected[name]
    template = json.loads((HERE / "stage-template.json").read_bytes())
    bindings = {
        "@python": str(python),
        "@uv": platform["uv"],
        "@wheelhouse": platform["wheelhouse"],
        "@build_constraints": platform["build_constraints"],
    }
    for command in template.values():
        command["argv"] = [
            bindings.get(arg, arg) if isinstance(arg, str) else arg for arg in command["argv"]
        ]
    assert json.loads((path.parent / "stage-commands.json").read_bytes()) == template
    return path


class PreparedFixture(shared.PreparedFixture):
    def _stage(self, family):
        stage = super()._stage(family)
        if family in {"unit", "integration"}:
            source = {"root": "snapshot", "path": "src", "prefix": "pythonpath="}
            stage["command"]["argv"] = [
                "pythonpath=../src" if arg == source else arg for arg in stage["command"]["argv"]
            ]
        return stage

    def __init__(self, case, **kwargs):
        assert kwargs.get("real") is True
        path = current_inputs()
        with (
            patch.object(shared, "PACKET", HERE),
            patch.dict(os.environ, {"CAIRNTIR_PALADIN_PLATFORM": str(path)}),
        ):
            super().__init__(case, **kwargs)
        scratch = self.root / "scratch"
        writable = {
            "TEMP": str(scratch / "tmp"),
            "TMP": str(scratch / "tmp"),
            "HOME": str(scratch / "home"),
            "USERPROFILE": str(scratch / "home"),
            "LOCALAPPDATA": str(scratch / "home/local"),
            "APPDATA": str(scratch / "home/roaming"),
            "UV_CACHE_DIR": str(scratch / "uv-cache"),
        }
        for directory in set(writable.values()):
            Path(directory).mkdir(parents=True, exist_ok=True)
        self.environment["values"].update(writable)
        writable_environment = patch.dict(os.environ, self.environment["values"], clear=True)
        writable_environment.start()
        case.addCleanup(writable_environment.stop)
