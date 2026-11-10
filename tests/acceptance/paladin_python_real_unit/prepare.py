"""Produce one fresh, bounded current-tool input set for three real PALADIN tests."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import sys
import tomllib
from pathlib import Path, PurePosixPath

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


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(path):
    path = Path(path)
    require(path.is_absolute(), "An absolute path is required")
    canonical = Path(os.path.abspath(path))
    require(canonical == path, "Noncanonical input path")
    for candidate in (*reversed(canonical.parents), canonical):
        info = candidate.lstat()
        require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            f"Linked input path: {candidate}",
        )
    require(canonical.resolve(strict=True) == canonical, "Noncanonical resolved path")
    return canonical


def row(path):
    path = plain(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), f"Nonregular input: {path}")
    data = path.read_bytes()
    after = path.stat()
    require(
        (info.st_ino, info.st_size, info.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns)
        and len(data) == info.st_size,
        f"Input changed while reading: {path}",
    )
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": stat.S_IMODE(info.st_mode),
    }


def validate_record(record_path: Path, prefix: Path) -> list[dict]:
    """Verify only one declared RECORD closure without writes or tool dispatch."""
    prefix, record_path = plain(prefix), plain(record_path)
    require(prefix.is_dir() and record_path.is_relative_to(prefix), "RECORD outside prefix")
    before = row(record_path)
    entries = list(csv.reader(io.StringIO(record_path.read_text(encoding="utf-8"))))
    require(entries and all(len(entry) == 3 for entry in entries), "Malformed RECORD")
    selected = {}
    for name, encoded, size in entries:
        require(name, "Empty RECORD path")
        parts = PurePosixPath(name.replace("\\", "/")).parts
        require(
            parts and not PurePosixPath(name.replace("\\", "/")).is_absolute(),
            "Absolute RECORD path",
        )
        require(not any(":" in part or part == "." for part in parts), "Unsafe RECORD path")
        path = record_path.parent.parent
        for part in parts:
            path = path.parent if part == ".." else path / part
            require(path.is_relative_to(prefix), "RECORD path escapes selected prefix")
            plain(path)
        require(path not in selected, "Duplicate RECORD target")
        actual = row(path)
        if encoded:
            expected = "sha256=" + base64.urlsafe_b64encode(
                bytes.fromhex(actual["sha256"])
            ).decode().rstrip("=")
            require(
                encoded == expected and size.isascii() and size.isdecimal(),
                "Bad RECORD digest/size",
            )
            require(int(size) == actual["bytes"], "RECORD size mismatch")
        else:
            require(path == record_path and size == "", "Unhashed RECORD payload")
        selected[path] = actual
    require(
        record_path in selected and row(record_path) == before, "RECORD changed or omits itself"
    )
    return [selected[path] for path in sorted(selected)]


def selected_sources():
    prefix = plain(Path(sys.prefix).resolve())
    sources = []
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        members = [Path(distribution.locate_file(item)) for item in distribution.files or ()]
        records = [
            path
            for path in members
            if path.name == "RECORD" and path.parent.name.endswith(".dist-info")
        ]
        require(len(records) == 1, f"Missing or ambiguous selected RECORD: {name}")
        record = Path(os.path.abspath(records[0]))
        files = validate_record(record, prefix)
        sources.append(
            {
                "name": name,
                "version": distribution.version,
                "record_path": str(record),
                "record_sha256": sha(record),
                "files": files,
            }
        )
    return prefix, sources


def q05_module(repo):
    source = plain(repo / "scripts/provision_q05.py")
    spec = importlib.util.spec_from_file_location("bounded_q05_input_verifier", source)
    require(spec is not None and spec.loader is not None, "Q05 verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_row(source, destination):
    require(not destination.exists() and not destination.is_symlink(), "Copy target already exists")
    ancestor = destination.parent
    while not ancestor.exists():
        require(not ancestor.is_symlink(), "Linked missing copy ancestor")
        ancestor = ancestor.parent
    plain(ancestor)
    destination.parent.mkdir(parents=True, exist_ok=True)
    plain(destination.parent)
    shutil.copy2(Path(source["path"]), destination)
    actual = row(destination)
    require(destination.stat().st_nlink == 1, "Owned copy is hardlinked")
    require(
        {key: actual[key] for key in ("bytes", "sha256", "mode")}
        == {key: source[key] for key in ("bytes", "sha256", "mode")},
        "Copied input differs",
    )


def owned_files(q05, root):
    return [item for item in q05._walk(root) if item["path"] != "preparation.json"]


def verify_preparation(platform_path: Path, repo: Path) -> dict:
    """Recheck declared current inputs and complete owned bytes without dispatch."""
    platform_path, repo = plain(platform_path), plain(repo)
    root = platform_path.parent
    require(platform_path.name == "platform.json", "Wrong owned input root")
    receipt = json.loads((root / "preparation.json").read_bytes())
    require(
        receipt["schema"] == "cairntir.python-seven-preparation.v1", "Unknown preparation schema"
    )
    require(
        sha(repo / "scripts/provision_q05.py") == receipt["q05_verifier_sha256"],
        "Q05 verifier changed",
    )
    require(
        sha(repo / "tests/acceptance/paladin_python_real_unit/stage-template.json")
        == receipt["stage_template_sha256"],
        "Stage template changed",
    )
    q05 = q05_module(repo)
    require(owned_files(q05, root) == receipt["files"], "Owned files, modes or membership changed")
    q05_path = Path(receipt["q05_platform"])
    require(sha(q05_path) == receipt["q05_platform_sha256"], "Q05 platform changed")
    q05.verify_platform(q05_path)
    prefix, sources = selected_sources()
    require(
        str(prefix) == receipt["source_prefix"] and sources == receipt["distributions"],
        "Selected source closure changed",
    )
    platform = json.loads(platform_path.read_bytes())
    require(
        {tool["id"] for tool in platform["tools"]}
        == {
            "python",
            "ruff",
            "mypy",
            "pytest",
            "pytest-cov",
            "coverage",
            "uv",
        }
        and len(platform["tools"]) == 7,
        "Seven actual tool identities required",
    )
    for tool in platform["tools"]:
        require(sha(plain(Path(tool["executable"]))) == tool["sha256"], "Executable changed")
        payload = plain(Path(tool["payload_root"]))
        require(payload.is_relative_to(root), "Payload escapes owned root")
        require(
            tool["payload_files"]
            == [{"path": item["path"], "sha256": item["sha256"]} for item in q05._walk(payload)],
            "Tool payload changed",
        )
        evidence = payload / tool["version_evidence"]["path"]
        require(sha(evidence) == tool["version_evidence"]["sha256"], "Version evidence changed")
    return platform


def prepare(output: Path, q05_platform: Path, repo: Path) -> Path:
    """Copy only verified selected inputs into the one new owned tool directory."""
    require(output.is_absolute(), "Output must be an absolute fresh directory")
    plain(output.parent)
    require(not output.exists() and not output.is_symlink(), "Refusing an existing output")
    require(sys.dont_write_bytecode, "Run the producer with Python -I -B")
    repo, q05_platform = plain(repo), plain(q05_platform)
    q05 = q05_module(repo)
    platform = q05.verify_platform(q05_platform)
    source_prefix, distributions = selected_sources()
    versions = {item["name"]: item["version"] for item in distributions}
    original = {tool["id"]: tool for tool in platform["tools"]}
    require(original["python"]["version"] == sys.version.split()[0], "Driver/Q05 Python mismatch")
    require(original["ruff"]["version"] == versions["ruff"], "Driver/Q05 Ruff mismatch")
    q05_hash, verifier_hash = sha(q05_platform), sha(repo / "scripts/provision_q05.py")
    template_path = plain(repo / "tests/acceptance/paladin_python_real_unit/stage-template.json")
    template_hash = sha(template_path)
    output.mkdir()
    environment = q05._environment(output / "environment")
    toolchain, build = output / "toolchain", output / "build"
    q05._run(
        output,
        "venv",
        [
            platform["python"],
            "-I",
            "-B",
            "-m",
            "venv",
            "--without-pip",
            "--copies",
            str(toolchain),
        ],
        environment["values"],
        output,
    )
    alias = toolchain / "lib64"
    if alias.is_symlink() and os.readlink(alias) == "lib":
        require(plain(toolchain / "lib").is_dir(), "Venv lib target must be plain")
        alias.unlink()
    for distribution in distributions:
        for source in distribution["files"]:
            destination = toolchain / Path(source["path"]).relative_to(source_prefix)
            copy_row(source, destination)
    wheels = Path(platform["wheelhouse"])
    for source in sorted(wheels.iterdir()):
        copy_row(row(source), build / "wheelhouse" / source.name)
    copy_row(row(Path(platform["build_constraints"])), build / "build-constraints.txt")
    python = plain(toolchain / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    probe = (
        "import importlib,importlib.metadata,json,sys;names=json.loads(sys.argv[1]);"
        "modules=('ruff','mypy','pytest','pytest_cov','coverage','packaging');"
        "print(json.dumps({'python':sys.executable,'base':sys.base_prefix,'version':sys.version.split()[0],"
        "'versions':{n:importlib.metadata.version(n)for n in names},"
        "'origins':{n:importlib.import_module(n).__file__ for n in modules}}))"
    )
    observed = q05._run(
        output,
        "source-observation",
        [
            str(python),
            "-I",
            "-B",
            "-c",
            probe,
            json.dumps(DISTRIBUTIONS),
        ],
        environment["values"],
        output,
    )
    actual = json.loads(observed["stdout"])
    require(Path(actual["python"]).resolve() == python, "Wrong observed interpreter")
    require(
        Path(actual["base"]).resolve() == Path(sys.base_prefix).resolve(), "Wrong observed base"
    )
    require(
        actual["version"] == sys.version.split()[0] and actual["versions"] == versions,
        "Observed tool versions differ",
    )
    require(
        all(Path(path).resolve().is_relative_to(toolchain) for path in actual["origins"].values()),
        "Tool imports escape owned environment",
    )
    tools = []
    for name in ("python", "ruff", "mypy", "pytest", "pytest-cov", "coverage", "uv"):
        expected = (
            actual["version"]
            if name == "python"
            else original["uv"]["version"]
            if name == "uv"
            else versions[name]
        )
        if name == "uv":
            command, executable, payload = (
                [platform["uv"], "--version"],
                Path(platform["uv"]),
                build,
            )
        else:
            executable, payload = python, toolchain
            if name == "python":
                arguments = ["--version"]
            elif name == "pytest-cov":
                arguments = [
                    "-c",
                    "import importlib.metadata;"
                    "print('pytest-cov '+importlib.metadata.version('pytest-cov'))",
                ]
            else:
                arguments = ["-m", name, "--version"]
            command = [str(python), "-I", "-B", *arguments]
        result = q05._run(output, "version-" + name, command, environment["values"], output)
        text = (result["stdout"] + result["stderr"]).strip()
        match = re.search(r"(?<![\w.])([0-9]+\.[0-9]+\.[0-9]+)(?![\w.])", text)
        require(match is not None and match[1] == expected, f"Actual {name} version mismatch")
        evidence = payload / "prepared-evidence" / (name + ".json")
        q05._save(
            evidence,
            {
                "schema": "cairntir.tool-version.v1",
                "argv": command,
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "version": match[1],
            },
        )
        tools.append((name, executable, match[1], payload, evidence))
    template = json.loads(template_path.read_bytes())
    bindings = {
        "@python": str(python),
        "@uv": platform["uv"],
        "@wheelhouse": str(build / "wheelhouse"),
        "@build_constraints": str(build / "build-constraints.txt"),
    }
    for command in template.values():
        command["argv"] = [
            bindings.get(arg, arg) if isinstance(arg, str) else arg for arg in command["argv"]
        ]
    q05._save(output / "stage-commands.json", template)
    ready = {
        "schema": "cairntir.paladin-python.platform-ready.v1",
        "python": str(python),
        "uv": platform["uv"],
        "wheelhouse": str(build / "wheelhouse"),
        "build_constraints": str(build / "build-constraints.txt"),
        "tools": [q05._tool(*tool) for tool in tools],
        "environment": environment,
    }
    q05._save(output / "platform.json", ready)
    q05.verify_platform(q05_platform)
    after_prefix, after_sources = selected_sources()
    require(
        after_prefix == source_prefix and after_sources == distributions,
        "Read-only source inputs changed",
    )
    require(
        sha(q05_platform) == q05_hash and sha(template_path) == template_hash,
        "Prepared inputs changed",
    )
    locked = {
        item["name"]: item["version"]
        for item in tomllib.loads((repo / "uv.lock").read_text(encoding="utf-8"))["package"]
    }
    q05._save(
        output / "preparation.json",
        {
            "schema": "cairntir.python-seven-preparation.v1",
            "files": owned_files(q05, output),
            "source_prefix": str(source_prefix),
            "distributions": distributions,
            "q05_platform": str(q05_platform),
            "q05_platform_sha256": q05_hash,
            "q05_verifier_sha256": verifier_hash,
            "stage_template_sha256": template_hash,
            "observations": actual,
            "packaging": {"selected": versions["packaging"], "project_lock": locked["packaging"]},
            "qualification": (
                "New selected current inputs; shared base runtime, "
                "no whole-machine custody or historical qualification transfer"
            ),
        },
    )
    return output / "platform.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--q05-platform", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    print(prepare(arguments.output, arguments.q05_platform, arguments.repo))


if __name__ == "__main__":
    main()
