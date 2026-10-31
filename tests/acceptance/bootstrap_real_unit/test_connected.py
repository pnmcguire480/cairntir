"""Independent connected proof for a Python/pytest test bootstrap."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cairntir import paladin_bootstrap as bootstrap

from . import inputs

if sys.flags.optimize:
    raise RuntimeError("Q07 acceptance requires Python assertions")

PACKET = Path(__file__).resolve().parent

LOCK = PACKET / "approved-pytest.lock"

LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"

PACKAGES = {
    "colorama": "0.4.6",
    "iniconfig": "2.3.0",
    "packaging": "26.0",
    "pluggy": "1.6.0",
    "pygments": "2.20.0",
    "pytest": "9.0.3",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


def _settings() -> dict[str, Path | str]:
    inputs.observed_versions()
    return inputs.settings()


def _project(source: str, target: Path) -> Path:
    shutil.copytree(PACKET / "fixtures" / source, target)
    return target


def _prepare(project: Path, output: Path) -> dict:
    return bootstrap.prepare_test_bootstrap(project, output, **_settings())


def _run_exact(receipt: dict) -> tuple[subprocess.CompletedProcess, list[ET.Element]]:
    command = receipt["command"]
    assert not Path(command["junit_path"]).exists()
    result = subprocess.run(  # noqa: S603 - Execute the validated owned bootstrap command, no shell.
        command["argv"],
        cwd=command["cwd"],
        env=command["env"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    cases = ET.parse(command["junit_path"]).findall(".//testcase")  # noqa: S314 - Owned pytest report.
    return result, cases


def _receipt(receipt: dict, output: Path) -> None:
    assert receipt["schema"] == "cairntir.test-bootstrap.v1"
    assert receipt["status"] == "PREPARED"
    assert len(receipt["bootstrap_id"]) == 64
    assert len(receipt["snapshot_sha256"]) == 64
    assert receipt["approved_lock_sha256"] == LOCK_SHA256
    assert len(receipt["wheelhouse_sha256"]) == 64
    assert receipt["python_version"] == inputs.observed_versions()[0]
    assert receipt["uv_version"] == inputs.observed_versions()[1]
    assert {row["name"]: row["version"] for row in receipt["packages"]} == PACKAGES
    approved_hashes = {
        line.split("==", 1)[0]: line.rsplit("sha256:", 1)[1].strip()
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert {row["name"]: row["wheel_sha256"] for row in receipt["packages"]} == approved_hashes
    venv = Path(receipt["venv_path"]).resolve()
    snapshot = Path(receipt["snapshot_path"]).resolve()
    assert venv.is_relative_to(output.resolve())
    assert snapshot.is_relative_to(output.resolve())
    assert receipt["bootstrap_id"][:12] in str(venv)
    assert receipt["bootstrap_id"][:12] in str(snapshot)
    assert "include-system-site-packages = false" in (venv / "pyvenv.cfg").read_text().lower()
    assert Path(receipt["manifest_path"]).resolve().is_relative_to(output.resolve())
    assert Path(receipt["python_origin"]).resolve().is_relative_to(venv)
    assert Path(receipt["pytest_origin"]).resolve().is_relative_to(venv)
    command = receipt["command"]
    assert Path(command["argv"][0]).resolve().is_relative_to(venv)
    assert command["argv"][1:3] == ["-m", "pytest"]
    assert Path(command["cwd"]).resolve() == snapshot
    assert Path(command["junit_path"]).resolve().is_relative_to(output.resolve())
    assert "PYTHONPATH" not in command["env"]
    assert command["env"]["PYTHONNOUSERSITE"] == "1"
    inspect_imports = subprocess.run(  # noqa: S603 - Inspect the validated owned interpreter.
        [
            command["argv"][0],
            "-c",
            "import importlib, importlib.metadata, json; "
            "names=('colorama','iniconfig','packaging','pluggy','pygments','pytest'); "
            "print(json.dumps({n: {'version': importlib.metadata.version(n), "
            "'origin': importlib.import_module(n).__file__} for n in names}))",
        ],
        cwd=command["cwd"],
        env=command["env"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert inspect_imports.returncode == 0, inspect_imports.stderr
    installed = json.loads(inspect_imports.stdout)
    assert {name: row["version"] for name, row in installed.items()} == PACKAGES
    assert all(Path(row["origin"]).resolve().is_relative_to(venv) for row in installed.values())
    assert Path(installed["pytest"]["origin"]).resolve() == Path(receipt["pytest_origin"]).resolve()
    assert "tests_passed" not in receipt
    assert "test_result" not in receipt


def test_supported_fixture_prepares_two_reproducible_isolated_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project("clean", tmp_path / "source")
    settings = _settings()
    before_project = _inventory(project)
    before_wheels = _inventory(settings["wheelhouse"])
    inspection = bootstrap.inspect_test_infrastructure(project)
    assert inspection["schema"] == "cairntir.test-stack.v1"
    assert inspection["status"] == "SUPPORTED"
    assert inspection["stack"] == "python-pytest"
    assert inspection["test_files"] == ["tests/test_decision_log.py"]
    assert _inventory(project) == before_project

    bare = tmp_path / "bare"
    created = subprocess.run(  # noqa: S603 - Create an owned environment with the selected interpreter.
        [str(settings["python_executable"]), "-m", "venv", str(bare)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    bare_python = bare / "Scripts" / "python.exe" if os.name == "nt" else bare / "bin" / "python"
    bare_env = dict(os.environ)
    bare_env.pop("PYTHONPATH", None)
    bare_env["PYTHONNOUSERSITE"] = "1"
    missing = subprocess.run(  # noqa: S603 - Probe pytest absence in the owned bare environment.
        [str(bare_python), "-c", "import pytest"],
        env=bare_env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert missing.returncode != 0

    class NetworkTrap(BaseHTTPRequestHandler):
        requests = 0

        def do_GET(self) -> None:
            type(self).requests += 1
            self.send_response(503)
            self.end_headers()

        do_CONNECT = do_GET  # noqa: N815 - BaseHTTPRequestHandler protocol method.

        def log_message(self, *args: object) -> None:
            return

    trap = ThreadingHTTPServer(("127.0.0.1", 0), NetworkTrap)
    thread = threading.Thread(target=trap.serve_forever, daemon=True)
    thread.start()
    real_popen = subprocess.Popen
    installs = []

    def capture_install(argv, *args, **kwargs):
        assert isinstance(argv, (list, tuple))
        tokens = [str(part) for part in argv]
        if "install" in tokens:
            installs.append((tokens, kwargs.get("env") or {}))
        return real_popen(argv, *args, **kwargs)

    try:
        url = f"http://127.0.0.1:{trap.server_port}"
        with monkeypatch.context() as patch:
            patch.setenv("UV_INDEX_URL", f"{url}/simple")
            patch.setenv("PIP_INDEX_URL", f"{url}/simple")
            patch.setenv("HTTP_PROXY", url)
            patch.setenv("HTTPS_PROXY", url)
            patch.setenv("NO_PROXY", "")
            patch.setattr(subprocess, "Popen", capture_install)
            first = _prepare(project, tmp_path / "first")
    finally:
        trap.shutdown()
        thread.join(timeout=5)
        trap.server_close()
    assert NetworkTrap.requests == 0
    assert len(installs) == 1
    install, install_env = installs[0]
    assert Path(install[0]).resolve() == settings["uv_executable"]
    assert all(
        any(token == flag or token.startswith(flag + "=") for token in install)
        for flag in (
            "--offline",
            "--no-index",
            "--find-links",
            "--require-hashes",
            "--no-deps",
            "--only-binary",
            "--link-mode",
        )
    )
    assert ":all:" in " ".join(install)
    assert "copy" in " ".join(install)
    assert str(settings["wheelhouse"]) in " ".join(install)
    assert any(
        Path(value).resolve().is_relative_to((tmp_path / "first").resolve())
        for value in (
            install_env.get("UV_CACHE_DIR", ""),
            install[install.index("--cache-dir") + 1] if "--cache-dir" in install else "",
        )
        if value
    )
    assert inspection["project_sha256"] == first["snapshot_sha256"]
    second = _prepare(project, tmp_path / "second")
    for receipt, output in ((first, tmp_path / "first"), (second, tmp_path / "second")):
        _receipt(receipt, output)
        snapshot = Path(receipt["snapshot_path"])
        assert _inventory(snapshot) == before_project
        run, cases = _run_exact(receipt)
        assert run.returncode == 0, run.stdout + run.stderr
        assert len(cases) == 3
        assert all(case.find("failure") is None and case.find("error") is None for case in cases)
    assert first["bootstrap_id"] == second["bootstrap_id"]
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert first["venv_path"] != second["venv_path"]
    assert _inventory(project) == before_project
    assert _inventory(settings["wheelhouse"]) == before_wheels


def test_broken_reversal_fails_and_corrected_source_gets_new_version(tmp_path: Path) -> None:
    project = _project("broken", tmp_path / "source")
    original = _inventory(project)
    before_tests = (project / "tests" / "test_decision_log.py").read_bytes()
    broken = _prepare(project, tmp_path / "bootstrap")
    _receipt(broken, tmp_path / "bootstrap")
    failed, cases = _run_exact(broken)
    assert failed.returncode != 0
    assert len(cases) == 3
    assert sum(case.find("failure") is not None for case in cases) >= 2
    assert all(case.find("error") is None for case in cases)
    assert _inventory(project) == original
    old_snapshot = _inventory(Path(broken["snapshot_path"]))

    shutil.copyfile(PACKET / "fixtures/clean/src/decision_log.py", project / "src/decision_log.py")
    assert (project / "tests/test_decision_log.py").read_bytes() == before_tests
    corrected = _prepare(project, tmp_path / "bootstrap")
    _receipt(corrected, tmp_path / "bootstrap")
    assert corrected["bootstrap_id"] != broken["bootstrap_id"]
    assert corrected["snapshot_sha256"] != broken["snapshot_sha256"]
    assert _inventory(Path(broken["snapshot_path"])) == old_snapshot
    passed, cases = _run_exact(corrected)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert len(cases) == 3
    assert all(case.find("failure") is None and case.find("error") is None for case in cases)


def test_identical_replay_is_verified_without_reinstallation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project("clean", tmp_path / "source")
    first = _prepare(project, tmp_path / "bootstrap")
    _receipt(first, tmp_path / "bootstrap")
    manifest = Path(first["manifest_path"])
    assert manifest.exists()
    before = manifest.read_bytes()
    real_popen = subprocess.Popen

    def no_reinstall(argv, *args, **kwargs):
        tokens = (
            argv.lower().split() if isinstance(argv, str) else [str(part).lower() for part in argv]
        )
        assert not {"venv", "install", "sync"}.intersection(tokens), argv
        return real_popen(argv, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", no_reinstall)
        second = _prepare(project, tmp_path / "bootstrap")
    assert second == first
    assert manifest.read_bytes() == before
    snapshot_source = Path(first["snapshot_path"]) / "src/decision_log.py"
    snapshot_source.write_bytes(snapshot_source.read_bytes() + b"\n# tampered\n")
    tampered_bytes = snapshot_source.read_bytes()
    blocked = _prepare(project, tmp_path / "bootstrap")
    assert blocked["status"] == "BLOCKED"
    assert blocked["blocker"]["code"] == "SNAPSHOT_TAMPERED"
    assert snapshot_source.read_bytes() == tampered_bytes
    assert manifest.read_bytes() == before
