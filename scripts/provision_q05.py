"""Prepare actual, offline Q05 tools and verify their current selected bytes."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
import venv
import zipfile
from pathlib import Path
from typing import Any

_FIXTURE = Path(__file__).resolve().parents[1] / "tests/acceptance/paladin_resources_unit"
_PINS = {
    "hatchling": "1.32.3",
    "packaging": "26.2",
    "pathspec": "1.1.1",
    "pluggy": "1.6.0",
    "tomlkit": "0.15.1",
    "trove-classifiers": "2026.6.1.19",
}
_QUALIFICATION = (
    "Complete selected current runtime and owned preparation bytes; "
    "shared base runtime, not whole-machine custody"
)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(path: Path, root: Path | None = None) -> dict[str, Any]:
    info = path.lstat()
    _require(
        stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
        f"Expected a regular, unlinked file: {path}",
    )
    return {
        "path": path.relative_to(root).as_posix() if root else str(path),
        "bytes": info.st_size,
        "sha256": _sha(path),
        "mode": stat.S_IMODE(info.st_mode),
    }


def _walk(root: Path, excluded: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    _require(root.is_dir() and root.resolve() == root, f"Noncanonical inventory root: {root}")
    rows = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in excluded)
        for name in names:
            path = Path(directory) / name
            info = path.lstat()
            _require(
                stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                f"Linked or nonregular inventory directory: {path}",
            )
        rows.extend(_row(Path(directory) / name, root) for name in sorted(files))
    return sorted(rows, key=lambda row: row["path"])


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def _selection() -> dict[str, Any]:
    directories = {Path(sysconfig.get_path("stdlib")).resolve()}
    native = sysconfig.get_config_var("DESTSHARED")
    if native and Path(native).is_dir():
        directories.add(Path(native).resolve())
    base = Path(sys.base_prefix)
    if os.name == "nt" and (base / "DLLs").is_dir():
        directories.add((base / "DLLs").resolve())
    directories = {
        path
        for path in directories
        if not any(path != other and path.is_relative_to(other) for other in directories)
    }
    files = {Path(getattr(sys, "_base_executable", sys.executable)).resolve()}
    for path in base.iterdir():
        if path.is_file() and (
            path.suffix.lower() in {".exe", ".dll", ".zip", ".dylib"} or ".so" in path.name
        ):
            files.add(path.resolve())
    library, libdir = sysconfig.get_config_var("LDLIBRARY"), sysconfig.get_config_var("LIBDIR")
    if library and libdir and (Path(libdir) / library).is_file():
        files.add((Path(libdir) / library).resolve())
    return {
        "directories": sorted(map(str, directories)),
        "direct_files": sorted(map(str, files)),
        "excluded_directory_names": ["site-packages"],
    }


def _runtime() -> dict[str, Any]:
    selection = _selection()
    files, caches = {}, {}
    for directory in selection["directories"]:
        root = Path(directory)
        for row in _walk(root, ("site-packages",)):
            path = root / row["path"]
            target = (
                caches if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"} else files
            )
            target[str(path)] = {**row, "path": str(path)}
    for filename in selection["direct_files"]:
        files[filename] = _row(Path(filename))
    return {
        "schema": "cairntir.q05-current-runtime.v1",
        "selection": selection,
        "files": [files[path] for path in sorted(files)],
        "cache_files": [caches[path] for path in sorted(caches)],
    }


def _environment(root: Path) -> dict[str, Any]:
    values = {
        "PATH": os.defpath,
        "TEMP": str(root / "tmp"),
        "TMP": str(root / "tmp"),
        "HOME": str(root / "home"),
        "USERPROFILE": str(root / "home"),
        "LOCALAPPDATA": str(root / "home/local"),
        "APPDATA": str(root / "home/roaming"),
        "UV_CACHE_DIR": str(root / "uv-cache"),
        "UV_OFFLINE": "1",
        "UV_NO_INDEX": "1",
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_LINK_MODE": "copy",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
        "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
        "HF_HUB_OFFLINE": "1",
        "NO_COLOR": "1",
        "SOURCE_DATE_EPOCH": "1704067200",
    }
    if os.name == "nt":
        system = os.environ["SYSTEMROOT"]
        values.update(
            SystemRoot=system,
            WINDIR=system,
            COMSPEC=str(Path(system) / "System32/cmd.exe"),
            PATH=str(Path(system) / "System32"),
        )
    for key in ("TEMP", "HOME", "LOCALAPPDATA", "APPDATA"):
        Path(values[key]).mkdir(parents=True, exist_ok=True)
    return {
        "policy_id": "q05-current-actual-tools-v1",
        "values": values,
        "absent": [
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTEST_ADDOPTS",
            "PYTEST_PLUGINS",
            "COVERAGE_PROCESS_START",
            "FASTEMBED_CACHE_PATH",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "UV_INDEX",
            "UV_INDEX_URL",
            "UV_EXTRA_INDEX_URL",
            "UV_FIND_LINKS",
            "UV_PROJECT",
            "UV_CONFIG_FILE",
            "VIRTUAL_ENV",
        ],
    }


def _run(
    root: Path, label: str, argv: list[str], environment: dict[str, str], cwd: Path
) -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603 - fixed actual tool commands, never shell text
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    receipts = root / "receipts"
    receipts.mkdir(exist_ok=True)
    (receipts / f"{label}.stdout").write_bytes(result.stdout)
    (receipts / f"{label}.stderr").write_bytes(result.stderr)
    record = {
        "argv": argv,
        "cwd": str(cwd),
        "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", "replace"),
        "stderr": result.stderr.decode("utf-8", "replace"),
    }
    _save(receipts / f"{label}.json", record)
    _require(result.returncode == 0, f"{label} failed; exact command and output retained")
    return record


def _ruff(toolchain: Path) -> dict[str, Any]:
    distribution = importlib.metadata.distribution("ruff")
    files = {Path(distribution.locate_file(item)).resolve() for item in distribution.files or ()}
    records = [
        path for path in files if path.name == "RECORD" and path.parent.name.endswith(".dist-info")
    ]
    _require(len(records) == 1, "Ruff must have exactly one installed RECORD")
    record = records[0]
    entries = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    _require(len(entries) == len(files), "Ruff RECORD membership differs from installed files")
    _require(
        {Path(distribution.locate_file(row[0])).resolve() for row in entries} == files,
        "Ruff RECORD file set differs",
    )
    source = Path(sys.prefix).resolve()
    for name, encoded, length in entries:
        path = Path(distribution.locate_file(name)).resolve()
        _row(path)
        if encoded:
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
                .decode()
                .rstrip("=")
            )
            _require(
                encoded == "sha256=" + digest and int(length) == path.stat().st_size,
                f"Ruff RECORD verification failed: {path}",
            )
        else:
            _require(path == record and length == "", "Unhashed Ruff payload")
        destination = toolchain / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _require(not destination.exists(), f"Ruff payload overlaps interpreter: {destination}")
        shutil.copy2(path, destination)
        _require(
            _row(destination, toolchain)
            == {**_row(path), "path": path.relative_to(source).as_posix()},
            "Ruff copy differs",
        )
    return {
        "distribution_version": distribution.version,
        "record_path": str(record),
        "files": [_row(path) for path in sorted(files)],
    }


def _wheels(build: Path, source: Path | None) -> None:
    manifest = json.loads((_FIXTURE / "build-wheels.json").read_bytes())
    rows = manifest["inputs"]
    _require(
        {row["name"]: row["version"] for row in rows} == _PINS and len(rows) == 6,
        "Unexpected build input identities",
    )
    wheelhouse = build / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    if source is not None:
        _require(
            {path.name for path in source.iterdir()} == {row["filename"] for row in rows},
            "Supplied wheelhouse membership differs",
        )
    for row in rows:
        path = wheelhouse / row["filename"]
        _require(Path(row["filename"]).name == row["filename"], "Unsafe wheel filename")
        if source is None:
            _require(
                row["url"].startswith("https://files.pythonhosted.org/"), "Unapproved wheel host"
            )
            with urllib.request.urlopen(row["url"], timeout=60) as response:  # noqa: S310
                path.write_bytes(response.read(row["bytes"] + 1))
        else:
            original = source / row["filename"]
            _require(
                original.stat().st_size == row["bytes"] and _sha(original) == row["sha256"],
                "Supplied wheel differs from approved upstream archive",
            )
            shutil.copy2(original, path)
        _require(
            path.stat().st_size == row["bytes"] and _sha(path) == row["sha256"],
            "Downloaded wheel differs from approved upstream archive",
        )
        with zipfile.ZipFile(path) as wheel:
            _require(wheel.testzip() is None, "Invalid build wheel CRC")
    shutil.copy2(_FIXTURE / "build-wheels.json", build / "inputs.json")
    (build / "build-constraints.txt").write_text(
        "".join(f"{name}=={version}\n" for name, version in _PINS.items()),
        encoding="utf-8",
        newline="\n",
    )


def _tool(name: str, executable: Path, version: str, root: Path, evidence: Path) -> dict[str, Any]:
    return {
        "id": name,
        "executable": str(executable),
        "sha256": _sha(executable),
        "version": version,
        "version_evidence": {
            "path": evidence.relative_to(root).as_posix(),
            "sha256": _sha(evidence),
        },
        "payload_root": str(root),
        "payload_files": [{"path": row["path"], "sha256": row["sha256"]} for row in _walk(root)],
    }


def verify_platform(platform_path: Path) -> dict[str, Any]:
    """Recheck complete selected runtime and owned bytes without dispatching tools."""
    root = platform_path.parent
    _require(platform_path == root.resolve() / "platform.json", "Expected canonical platform.json")
    preparation = json.loads((root / "preparation.json").read_bytes())
    _require(
        preparation["schema"] == "cairntir.q05-public-preparation.v1", "Unknown preparation schema"
    )
    actual = [row for row in _walk(root) if row["path"] != "preparation.json"]
    _require(actual == preparation["files"], "Owned preparation bytes, membership or modes changed")
    for name in ("platform", "runtime"):
        _require(
            _row(root / (name + ".json"), root) == preparation[name], f"{name} receipt changed"
        )
    runtime = json.loads((root / "runtime.json").read_bytes())
    _require(runtime == _runtime(), "Selected shared runtime, caches or selection changed")
    platform = json.loads(platform_path.read_bytes())
    _require(
        platform["schema"] == "cairntir.paladin-python.platform-ready.v1", "Unknown platform schema"
    )
    _require(
        {tool["id"] for tool in platform["tools"]} == {"python", "ruff", "uv"},
        "Missing actual tools",
    )
    for tool in platform["tools"]:
        _require(_sha(Path(tool["executable"])) == tool["sha256"], "Tool executable changed")
        payload = Path(tool["payload_root"])
        _require(payload.is_relative_to(root), "Tool payload is outside owned preparation")
        _require(
            tool["payload_files"]
            == [{"path": row["path"], "sha256": row["sha256"]} for row in _walk(payload)],
            "Tool payload membership or hashes changed",
        )
        reference = tool["version_evidence"]
        evidence = payload / reference["path"]
        _require(_sha(evidence) == reference["sha256"], "Version observation changed")
        observed = json.loads(evidence.read_bytes())
        _require(
            observed["schema"] == "cairntir.tool-version.v1"
            and observed["exit_code"] == 0
            and observed["version"] == tool["version"]
            and observed["argv"][0] == tool["executable"],
            "Invalid tool version observation",
        )
    smoke = preparation["smoke"]
    _require(
        _row(root / smoke["wheel"]["path"], root) == smoke["wheel"], "Actual smoke wheel changed"
    )
    _require(
        json.loads((root / smoke["command"]).read_bytes())["exit_code"] == 0,
        "Offline build did not succeed",
    )
    return platform


def prepare(output: Path, wheelhouse: Path | None = None) -> Path:
    """Prepare actual tools under a new owned directory and retain their evidence."""
    output = output.resolve()
    output.mkdir(parents=True)
    build, toolchain = output / "build", output / "toolchain"
    build.mkdir()
    _wheels(build, wheelhouse)
    uv_name = shutil.which("uv")
    _require(uv_name is not None, "An installed uv executable is required")
    uv = Path(uv_name).resolve()
    venv.EnvBuilder(with_pip=False, symlinks=False).create(toolchain)
    alias = toolchain / "lib64"
    if alias.is_symlink() and alias.resolve() == (toolchain / "lib").resolve():
        alias.unlink()
    python = toolchain / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _row(python)
    ruff_source = _ruff(toolchain)
    environment = _environment(output / "environment")
    versions = {}
    for name, argv, target in (
        (
            "python",
            [str(python), "-I", "-B", "--version"],
            toolchain / "prepared-evidence/python.json",
        ),
        (
            "ruff",
            [str(python), "-I", "-B", "-m", "ruff", "--version"],
            toolchain / "prepared-evidence/ruff.json",
        ),
        ("uv", [str(uv), "--version"], build / "uv-version.json"),
    ):
        observed = _run(output, "version-" + name, argv, environment["values"], output)
        version = (observed["stdout"] + observed["stderr"]).strip().split()[1]
        if name == "ruff":
            _require(version == ruff_source["distribution_version"], "Copied Ruff version differs")
        versions[name] = version
        _save(
            target,
            {
                "schema": "cairntir.tool-version.v1",
                "argv": argv,
                "exit_code": observed["exit_code"],
                "stdout": observed["stdout"],
                "stderr": observed["stderr"],
                "version": version,
            },
        )
    source, destination = output / "smoke/source", output / "smoke/output"
    shutil.copytree(_FIXTURE / "fixture", source)
    command = [
        str(uv),
        "build",
        "--offline",
        "--no-index",
        "--find-links",
        str(build / "wheelhouse"),
        "--no-config",
        "--no-python-downloads",
        "--link-mode",
        "copy",
        "--python",
        str(python),
        "--build-constraints",
        str(build / "build-constraints.txt"),
        "--wheel",
        "--out-dir",
        str(destination),
        str(source),
    ]
    with tempfile.TemporaryDirectory(prefix="q05-build-", dir=output / "environment") as cache:
        _run(
            output,
            "offline-build",
            command,
            {**environment["values"], "UV_CACHE_DIR": cache},
            source,
        )
    wheel_path = destination / "q05_notes-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path) as wheel:
        _require(wheel.testzip() is None, "Offline smoke produced an invalid wheel")
        for path in (source / "src/q05_notes").rglob("*.py"):
            _require(
                wheel.read(path.relative_to(source / "src").as_posix()) == path.read_bytes(),
                "Smoke wheel source differs",
            )
    platform = {
        "schema": "cairntir.paladin-python.platform-ready.v1",
        "python": str(python),
        "uv": str(uv),
        "wheelhouse": str(build / "wheelhouse"),
        "build_constraints": str(build / "build-constraints.txt"),
        "tools": [
            _tool(
                "python",
                python,
                versions["python"],
                toolchain,
                toolchain / "prepared-evidence/python.json",
            ),
            _tool(
                "ruff",
                python,
                versions["ruff"],
                toolchain,
                toolchain / "prepared-evidence/ruff.json",
            ),
            _tool("uv", uv, versions["uv"], build, build / "uv-version.json"),
        ],
        "environment": environment,
    }
    _save(output / "platform.json", platform)
    _save(output / "runtime.json", _runtime())
    _save(
        output / "preparation.json",
        {
            "schema": "cairntir.q05-public-preparation.v1",
            "platform": _row(output / "platform.json", output),
            "runtime": _row(output / "runtime.json", output),
            "files": _walk(output),
            "smoke": {"command": "receipts/offline-build.json", "wheel": _row(wheel_path, output)},
            "ruff_source": ruff_source,
            "qualification": _QUALIFICATION,
        },
    )
    verify_platform(output / "platform.json")
    return output / "platform.json"


def main() -> None:
    """Prepare the current interpreter's real tools and print the platform path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    print(prepare(args.output, args.wheelhouse))


if __name__ == "__main__":
    main()
