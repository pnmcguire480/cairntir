"""Prepare offline, versioned test environments without running project code."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Any

_MAX_FILE = 2 * 1024 * 1024
_MAX_SOURCE = 8 * 1024 * 1024
_MAX_WHEELS = 32 * 1024 * 1024
_LOCK_LINE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_-]*) --hash=sha256:([0-9a-f]{64})"
)


class BootstrapError(ValueError):
    """A named refusal that never implies successful preparation."""

    def __init__(self, code: str, detail: str) -> None:
        """Keep the blocker machine-readable alongside its explanation."""
        self.code = code
        super().__init__(detail)


def _require(value: bool, code: str, detail: str) -> None:
    if not value:
        raise BootstrapError(code, detail)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _identity(value: Any) -> str:
    return _sha(_json(value).encode())


def _table(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BootstrapError("UNSUPPORTED_STACK", f"{label} must be a table")
    return value


def _plain(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            _require(
                not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400,
                "UNSAFE_INPUT",
                f"Symbolic links and reparse points are unsupported: {part}",
            )
    return path


def _read(path: Path, limit: int = _MAX_FILE) -> bytes:
    path = _plain(path)
    before = path.stat()
    _require(
        stat.S_ISREG(before.st_mode) and before.st_size <= limit,
        "UNSAFE_INPUT",
        f"Not a bounded regular file: {path}",
    )
    raw = path.read_bytes()
    after = path.stat()
    _require(
        (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns)
        and len(raw) <= limit,
        "INPUT_CHANGED",
        f"Input changed while reading: {path}",
    )
    return raw


def _files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        _plain(path)
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(_read(path, _MAX_WHEELS))
        else:
            _require(path.is_dir(), "UNSAFE_INPUT", f"Unsupported entry: {path}")
    return result


def _python_matches(spec: str, version: tuple[int, ...]) -> bool:
    for term in spec.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*(3\.\d+(?:\.\d+)?)\s*", term)
        _require(match is not None, "UNSUPPORTED_STACK", "Unsupported requires-python syntax")
        if match is None:
            return False
        operator, value = match.groups()
        parts = tuple(int(part) for part in value.split("."))
        left = version[: len(parts)]
        if not {
            ">=": left >= parts,
            "<=": left <= parts,
            "==": left == parts,
            ">": left > parts,
            "<": left < parts,
        }[operator]:
            return False
    return True


def _supports_python(spec: str) -> bool:
    patches = {0}
    for value in re.findall(r"3\.\d+\.(\d+)", spec):
        patch = int(value)
        patches.update((max(0, patch - 1), patch, patch + 1))
    return any(
        _python_matches(spec, (3, minor, patch)) for minor in (11, 12, 13) for patch in patches
    )


def _project(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    root = _plain(root)
    _require(root.is_dir(), "UNSAFE_INPUT", "Project root must be a directory")
    pyproject = root / "pyproject.toml"
    others = any(
        (root / name).exists() for name in ("package.json", "Cargo.toml", "go.mod", "pom.xml")
    )
    _require(
        not (pyproject.exists() and others), "MIXED_STACK", "Mixed project stacks are unsupported"
    )
    _require(
        pyproject.is_file(), "UNSUPPORTED_STACK", "Expected a pure Python pyproject.toml project"
    )
    raw = _read(pyproject)
    config = tomllib.loads(raw.decode("utf-8"))
    project = _table(config.get("project", {}), "project")
    _require(
        isinstance(project.get("name"), str) and bool(project["name"].strip()),
        "UNSUPPORTED_STACK",
        "Missing project declaration",
    )
    _require(
        not config.get("build-system")
        and not project.get("dependencies")
        and not project.get("dynamic")
        and not project.get("optional-dependencies"),
        "UNSUPPORTED_STACK",
        "Build systems and project dependencies require a separate bootstrap",
    )
    requires = project.get("requires-python")
    if not isinstance(requires, str) or not requires:
        raise BootstrapError("UNSUPPORTED_STACK", "Declare requires-python")
    _require(
        _supports_python(requires),
        "UNSUPPORTED_STACK",
        "Only Python 3.11-3.13 projects are supported",
    )
    for name in ("pytest.ini", "setup.cfg", "tox.ini", "setup.py"):
        _require(
            not (root / name).exists(),
            "UNSUPPORTED_STACK",
            f"External configuration is unsupported: {name}",
        )
    tool = _table(config.get("tool", {}), "tool")
    pytest = _table(tool.get("pytest", {}), "tool.pytest")
    options = pytest.get("ini_options", {})
    _require(isinstance(options, dict), "UNSUPPORTED_STACK", "Invalid pytest configuration")
    for key, expected in (("pythonpath", ["src"]), ("testpaths", ["tests"])):
        value = options.get(key, expected)
        _require(value == expected, "UNSAFE_INPUT", f"Only {key}={expected} is supported")
    _require(
        not set(options) - {"pythonpath", "testpaths"},
        "UNSUPPORTED_STACK",
        "Unsupported pytest options",
    )
    contents = {"pyproject.toml": raw}
    for directory in (root / "src", root / "tests"):
        if not directory.exists():
            continue
        _plain(directory)
        _require(directory.is_dir(), "UNSAFE_INPUT", "Source/test path is not a directory")
        for path in sorted(directory.rglob("*")):
            _plain(path)
            if path.is_dir():
                continue
            _require(
                path.suffix not in {".pth", ".pyc"} and "__pycache__" not in path.parts,
                "UNSAFE_INPUT",
                "Cached code and path injection files are unsupported",
            )
            name = path.relative_to(root).as_posix()
            _require(":" not in name and "\\" not in name, "UNSAFE_INPUT", "Ambiguous source path")
            contents[name] = _read(path)
            _require(
                len(contents) <= 1024 and sum(map(len, contents.values())) <= _MAX_SOURCE,
                "UNSAFE_INPUT",
                "Project snapshot exceeds its bound",
            )
    if (root / "conftest.py").exists():
        contents["conftest.py"] = _read(root / "conftest.py")
    tests = sorted(
        name for name in contents if name.startswith("tests/") and Path(name).match("test_*.py")
    )
    _require(bool(tests), "NO_TESTS", "No existing tests/test_*.py files were found")
    return {
        "schema": "cairntir.test-stack.v1",
        "status": "SUPPORTED",
        "stack": "python-pytest",
        "detected_python": requires,
        "test_files": tests,
        "project_sha256": _identity({name: _sha(data) for name, data in contents.items()}),
    }, contents


def _blocked(schema: str, exc: Exception) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": "BLOCKED",
        "blocker": {
            "code": exc.code if isinstance(exc, BootstrapError) else "PREPARATION_FAILED",
            "detail": str(exc),
        },
    }


def inspect_test_infrastructure(project_root: Path) -> dict[str, Any]:
    """Inspect supported metadata and source bytes without importing project code."""
    try:
        inspection, _ = _project(project_root)
    except (BootstrapError, OSError, ValueError, TypeError, KeyError) as exc:
        return _blocked("cairntir.test-stack.v1", exc)
    else:
        return inspection


def _locked(
    requirements: Path, expected: str, wheelhouse: Path
) -> tuple[bytes, list[dict[str, str]], dict[str, str]]:
    raw = _read(requirements)
    _require(_sha(raw) == expected, "UNAPPROVED_LOCK", "Caller-approved lock SHA256 does not match")
    packages: list[dict[str, str]] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        match = _LOCK_LINE.fullmatch(line)
        _require(
            match is not None, "UNAPPROVED_LOCK", "Use exact name==version and one SHA256 per line"
        )
        if match is None:
            continue
        name, version, digest = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        _require(
            name not in {row["name"] for row in packages},
            "UNAPPROVED_LOCK",
            "Duplicate locked package",
        )
        packages.append({"name": name, "version": version, "wheel_sha256": digest})
    _require(
        0 < len(packages) <= 32 and any(row["name"] == "pytest" for row in packages),
        "UNAPPROVED_LOCK",
        "Lock must include pytest and bounded exact dependencies",
    )
    wheelhouse = _plain(wheelhouse)
    _require(wheelhouse.is_dir(), "WHEELHOUSE_INCOMPLETE", "Approved wheelhouse is missing")
    wheels = list(wheelhouse.iterdir())
    _require(
        len(wheels) == len(packages)
        and all(path.is_file() and path.suffix == ".whl" for path in wheels),
        "WHEELHOUSE_INCOMPLETE",
        "Wheelhouse must contain exactly the approved wheels",
    )
    hashes: dict[str, str] = {}
    found: set[str] = set()
    total = 0
    for path in sorted(wheels):
        match = re.fullmatch(
            r"([A-Za-z0-9_]+)-([A-Za-z0-9.!+_]+)-(?:py3|py2\.py3)-none-any\.whl", path.name
        )
        _require(
            match is not None,
            "WHEELHOUSE_INCOMPLETE",
            "Only matching universal wheels are supported",
        )
        if match is None:
            continue
        name, version = match.groups()
        name = name.replace("_", "-").lower()
        package = next(
            (row for row in packages if row["name"] == name and row["version"] == version), None
        )
        _require(
            package is not None and name not in found,
            "WHEELHOUSE_INCOMPLETE",
            "Unapproved or duplicate wheel",
        )
        if package is None:
            continue
        data = _read(path, _MAX_WHEELS)
        total += len(data)
        _require(total <= _MAX_WHEELS, "UNSAFE_INPUT", "Wheelhouse exceeds byte bound")
        _require(
            _sha(data) == package["wheel_sha256"],
            "WHEEL_HASH_MISMATCH",
            f"Wheel SHA256 mismatch: {path.name}",
        )
        with zipfile.ZipFile(path) as archive:
            _require(
                not any(info.filename.endswith(".pth") for info in archive.infolist()),
                "UNSAFE_INPUT",
                "Path injection wheels are unsupported",
            )
        hashes[path.name] = _sha(data)
        found.add(name)
    return raw, sorted(packages, key=lambda row: row["name"]), hashes


def _environment(home: Path) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "SYSTEMROOT", "COMSPEC")
        if key in os.environ
    }
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        TMP=str(home / "tmp"),
        TEMP=str(home / "tmp"),
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        UV_NO_CONFIG="1",
        UV_OFFLINE="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_CACHE_DIR=str(home / "uv-cache"),
    )
    return env


def _run(argv: list[str], *, env: dict[str, str], cwd: Path, timeout: int = 120) -> str:
    result = subprocess.run(  # noqa: S603 - explicit caller tools, no shell.
        argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    _require(result.returncode == 0, "TOOL_FAILED", (result.stderr or result.stdout)[-4000:])
    return result.stdout.strip()


def _tool_sha(path: Path) -> str:
    with _plain(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _remove_venv_lib64_alias(venv: Path) -> None:
    alias = venv / "lib64"
    if alias.is_symlink() and alias.readlink() == Path("lib"):
        _require(_plain(venv / "lib").is_dir(), "UNSAFE_INPUT", "Invalid venv lib directory")
        alias.unlink()


def _command(python: Path, snapshot: Path, version: Path) -> dict[str, Any]:
    junit = version / "result.xml"
    return {
        "argv": [
            str(python),
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--junitxml",
            str(junit),
            "tests",
        ],
        "cwd": str(snapshot),
        "env": _environment(version / "home"),
        "junit_path": str(junit),
    }


def prepare_test_bootstrap(
    project_root: Path,
    bootstrap_root: Path,
    *,
    python_executable: Path,
    uv_executable: Path,
    approved_requirements: Path,
    approved_sha256: str,
    wheelhouse: Path,
) -> dict[str, Any]:
    """Prepare exact approved wheels offline; return a command, never a test verdict."""
    try:
        return _prepare(
            project_root,
            bootstrap_root,
            python_executable=python_executable,
            uv_executable=uv_executable,
            approved_requirements=approved_requirements,
            approved_sha256=approved_sha256,
            wheelhouse=wheelhouse,
        )
    except (
        BootstrapError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as exc:
        return _blocked("cairntir.test-bootstrap.v1", exc)


def _prepare(
    project_root: Path,
    bootstrap_root: Path,
    *,
    python_executable: Path,
    uv_executable: Path,
    approved_requirements: Path,
    approved_sha256: str,
    wheelhouse: Path,
) -> dict[str, Any]:
    inspection, contents = _project(project_root)
    root, project, wheels = _plain(bootstrap_root), _plain(project_root), _plain(wheelhouse)
    lock, packages, wheel_hashes = _locked(approved_requirements, approved_sha256, wheels)
    for source in (project, wheels, _plain(approved_requirements)):
        _require(
            not (root.is_relative_to(source) or source.is_relative_to(root)),
            "UNSAFE_INPUT",
            "Bootstrap output must not overlap its inputs",
        )
    python, uv = _plain(python_executable), _plain(uv_executable)
    tool_hashes = {"python": _tool_sha(python), "uv": _tool_sha(uv)}
    env = _environment(root / "preflight-home")
    runtime = json.loads(
        _run(
            [
                str(python),
                "-I",
                "-B",
                "-S",
                "-c",
                "import json,sys; print(json.dumps(list(sys.version_info[:3])))",
            ],
            env=env,
            cwd=project,
        )
    )
    _require(
        isinstance(runtime, list)
        and len(runtime) == 3
        and runtime[0] == 3
        and runtime[1] in (11, 12, 13),
        "UNSUPPORTED_PYTHON",
        "Interpreter must be Python 3.11-3.13",
    )
    _require(
        _python_matches(inspection["detected_python"], tuple(runtime)),
        "UNSUPPORTED_PYTHON",
        "Interpreter does not satisfy project requires-python",
    )
    python_version = ".".join(map(str, runtime))
    uv_text = _run([str(uv), "--version"], env=env, cwd=project)
    match = re.fullmatch(r"uv (0\.[0-9]+\.[0-9]+)(?: .*)?", uv_text)
    _require(match is not None, "UNSUPPORTED_TOOL", "Unsupported uv version response")
    uv_version = match[1] if match else ""
    identity = {
        "schema": "cairntir.test-bootstrap.v1",
        "snapshot_sha256": inspection["project_sha256"],
        "approved_lock_sha256": approved_sha256,
        "wheelhouse_sha256": _identity(wheel_hashes),
        "python_version": python_version,
        "uv_version": uv_version,
        "tool_sha256": tool_hashes,
    }
    bootstrap_id = _identity(identity)
    version = root / bootstrap_id
    snapshot, venv = version / "snapshot", version / "venv"
    manifest = version / "PREPARED.json"
    venv_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command = _command(venv_python, snapshot, version)
    expected_inputs = {name: _sha(raw) for name, raw in contents.items()}
    site = venv / (
        "Lib/site-packages"
        if os.name == "nt"
        else f"lib/python{runtime[0]}.{runtime[1]}/site-packages"
    )
    paths = {
        "snapshot_path": str(snapshot),
        "venv_path": str(venv),
        "manifest_path": str(manifest),
        "python_origin": str(venv_python),
        "pytest_origin": str(site / "pytest/__init__.py"),
    }
    if version.exists():
        _require(manifest.is_file(), "INCOMPLETE_BOOTSTRAP", "An incomplete version already exists")
        receipt: dict[str, Any] = json.loads(_read(manifest))
        _require(
            isinstance(receipt, dict)
            and all(receipt.get(key) == value for key, value in identity.items())
            and receipt.get("bootstrap_id") == bootstrap_id
            and receipt.get("status") == "PREPARED"
            and receipt.get("command") == command
            and receipt.get("packages") == packages
            and all(receipt.get(key) == value for key, value in paths.items())
            and set(receipt)
            == set(identity)
            | set(paths)
            | {"status", "bootstrap_id", "packages", "command", "venv_files"},
            "SNAPSHOT_TAMPERED",
            "Prepared manifest identity changed",
        )
        _require(
            _files(snapshot) == expected_inputs
            and _files(venv) == receipt.get("venv_files")
            and _read(version / "approved.lock") == lock,
            "SNAPSHOT_TAMPERED",
            "Published snapshot or environment bytes changed",
        )
        return receipt
    version.mkdir(parents=True, exist_ok=False)
    home = version / "home"
    (home / "tmp").mkdir(parents=True)
    for name, raw in contents.items():
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (version / "approved.lock").write_bytes(lock)
    env = command["env"]
    _run(
        [str(python), "-I", "-B", "-m", "venv", "--without-pip", "--copies", str(venv)],
        env=env,
        cwd=version,
    )
    _remove_venv_lib64_alias(venv)
    _run(
        [
            str(uv),
            "--no-config",
            "--cache-dir",
            str(home / "uv-cache"),
            "pip",
            "install",
            "--python",
            str(venv_python),
            "--offline",
            "--no-index",
            "--find-links",
            str(wheels),
            "--require-hashes",
            "--no-deps",
            "--only-binary",
            ":all:",
            "--link-mode",
            "copy",
            "-r",
            str(version / "approved.lock"),
        ],
        env=env,
        cwd=version,
    )
    probe = json.loads(
        _run(
            [
                str(venv_python),
                "-I",
                "-B",
                "-c",
                "import importlib.metadata as m,json,sys,pytest; "
                "print(json.dumps({'packages':"
                "{d.metadata['Name'].lower():d.version for d in m.distributions()},"
                "'python_origin':sys.executable,'pytest_origin':pytest.__file__,'prefix':sys.prefix,'base':sys.base_prefix}))",
            ],
            env=env,
            cwd=version,
        )
    )
    _require(
        probe["packages"] == {row["name"]: row["version"] for row in packages}
        and Path(probe["prefix"]).resolve() == venv.resolve()
        and probe["prefix"] != probe["base"]
        and Path(probe["python_origin"]).resolve().is_relative_to(venv.resolve())
        and Path(probe["pytest_origin"]).resolve().is_relative_to(venv.resolve()),
        "ENVIRONMENT_MISMATCH",
        "Installed versions or origins do not match the isolated lock",
    )
    _require(
        "include-system-site-packages = false" in (venv / "pyvenv.cfg").read_text().lower(),
        "ENVIRONMENT_MISMATCH",
        "System site packages must be disabled",
    )
    current, _ = _project(project)
    current_lock, current_packages, current_wheels = _locked(
        approved_requirements, approved_sha256, wheels
    )
    _require(
        current == inspection
        and current_lock == lock
        and current_packages == packages
        and current_wheels == wheel_hashes
        and _files(snapshot) == expected_inputs
        and tool_hashes == {"python": _tool_sha(python), "uv": _tool_sha(uv)},
        "INPUT_CHANGED",
        "Bootstrap inputs changed during preparation",
    )
    receipt = {
        **identity,
        "status": "PREPARED",
        "bootstrap_id": bootstrap_id,
        "packages": packages,
        "python_origin": probe["python_origin"],
        "pytest_origin": probe["pytest_origin"],
        "snapshot_path": str(snapshot),
        "venv_path": str(venv),
        "manifest_path": str(manifest),
        "command": command,
        "venv_files": _files(venv),
    }
    _require(
        all(receipt.get(key) == value for key, value in paths.items()),
        "ENVIRONMENT_MISMATCH",
        "Observed environment origins differ from their published paths",
    )
    temporary = version / "manifest.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(_json(receipt) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(manifest)
    return receipt
