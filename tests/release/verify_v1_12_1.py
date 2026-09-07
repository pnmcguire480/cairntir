"""One-release verifier; intentionally outside automatic pytest collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.12.1"
INPUTS = ROOT / "plans/v1.12.1-release-acceptance-inputs.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _package_files() -> dict[str, bytes]:
    package = ROOT / "src/cairntir"
    files = {
        "cairntir/" + path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file() and (path.suffix in {".py", ".md"} or path.name == "py.typed")
    }
    recipes = ROOT / "docs/recipes"
    files.update(
        {
            "cairntir/recipes/bundled/" + path.relative_to(recipes).as_posix(): path.read_bytes()
            for path in recipes.rglob("*")
            if path.is_file()
        }
    )
    return files


def verify(
    mode: str, wheel: Path | None, sdist: Path | None, backup_acceptance: Path | None
) -> dict[str, Any]:
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    for path, digest in (inputs["source_hashes"] | inputs["historical_frozen_hashes"]).items():
        check(_sha((ROOT / path).read_bytes()) == digest, f"changed frozen input: {path}")
    actual_sources = {p.relative_to(ROOT).as_posix() for p in (ROOT / "src").rglob("*.py")}
    check(
        actual_sources
        == set(inputs["source_hashes"]) | {"src/cairntir/__init__.py", "src/cairntir/backups.py"},
        "runtime Python file inventory changed",
    )
    backup_hash = _sha((ROOT / "src/cairntir/backups.py").read_bytes())
    if backup_acceptance is None:
        check(False, "independent 72-case backup repair acceptance is required")
    else:
        receipt = json.loads(backup_acceptance.read_text(encoding="utf-8"))
        check(
            receipt.get("result") == "PASS"
            and receipt.get("passed") == inputs["required_behavioral_passed"]
            and receipt.get("failed") == 0,
            "backup repair acceptance did not pass all 72 required cases",
        )
        for key in ("source_hashes_before", "source_hashes_after"):
            check(
                receipt.get(key, {}).get("src/cairntir/backups.py") == backup_hash,
                f"backup repair source differs from independent {key}",
            )
        check(
            receipt.get("source_hashes_before") == receipt.get("source_hashes_after"),
            "runtime changed during independent backup repair acceptance",
        )
        for path, digest in inputs["historical_frozen_hashes"].items():
            check(
                receipt.get("frozen_hashes", {}).get(path) == digest,
                f"independent repair did not verify frozen input: {path}",
            )
        raw = ROOT / receipt["raw_output"]
        check(_sha(raw.read_bytes()) == receipt["raw_output_sha256"], "repair raw output differs")
    version_module = (ROOT / "src/cairntir/__init__.py").read_bytes()
    check(
        _sha(version_module) == inputs["expected_version_module_sha256"],
        "version-only module delta",
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    packages = lock["package"]
    own = [p for p in packages if p["name"] == "cairntir"]
    check(project["version"] == VERSION, "pyproject version is not 1.12.1")
    check(len(own) == 1 and own[0]["version"] == VERSION, "uv.lock version is not 1.12.1")
    check(plugin["version"] == VERSION, "plugin version is not 1.12.1")
    requirements = {
        key: project.get(key)
        for key in ("requires-python", "dependencies", "optional-dependencies")
    }
    check(
        _canonical(requirements) == inputs["dependency_declarations_sha256"],
        "dependency declarations changed",
    )
    check(
        _canonical([p for p in packages if p["name"] != "cairntir"])
        == inputs["locked_dependencies_sha256"],
        "non-Cairntir locked packages changed",
    )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    check(
        bool(re.search(r"^## \[1\.12\.1\] [—-] \d{4}-\d{2}-\d{2}$", changelog, re.M)),
        "dated 1.12.1 changelog missing",
    )
    unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    check(not unreleased.strip(), "Unreleased section must be empty")
    files = _package_files()
    check(len(files) == 74, "expected exactly 74 Cairntir package files")
    hashes = {}
    if mode == "package":
        assert wheel is not None and sdist is not None
        with zipfile.ZipFile(wheel) as archive:
            members = {
                p for p in archive.namelist() if p.startswith("cairntir/") and not p.endswith("/")
            }
            check(members == set(files), "wheel package file inventory differs")
            for name in members & files.keys():
                check(archive.read(name) == files[name], f"wheel member differs: {name}")
            metadata = BytesParser().parsebytes(
                archive.read(f"cairntir-{VERSION}.dist-info/METADATA")
            )
            check(metadata["Version"] == VERSION, "wheel metadata version differs")
        with tarfile.open(sdist) as archive:
            prefix = f"cairntir-{VERSION}/"
            expected = [
                *actual_sources,
                "pyproject.toml",
                "uv.lock",
                "CHANGELOG.md",
                *(
                    p.relative_to(ROOT).as_posix()
                    for p in (ROOT / "docs/recipes").rglob("*")
                    if p.is_file()
                ),
            ]
            for name in expected:
                member = archive.extractfile(prefix + name)
                check(
                    member is not None and member.read() == (ROOT / name).read_bytes(),
                    f"sdist member differs: {name}",
                )
            metadata_file = archive.extractfile(prefix + "PKG-INFO")
            assert metadata_file is not None
            metadata = BytesParser().parsebytes(metadata_file.read())
            check(metadata["Version"] == VERSION, "sdist metadata version differs")
        hashes = {"wheel": _sha(wheel.read_bytes()), "sdist": _sha(sdist.read_bytes())}
    return {
        "result": "FAIL" if failures else "PASS",
        "gate": mode,
        "version": VERSION,
        "source_files_unchanged_except_version_and_backup_repair": len(inputs["source_hashes"]),
        "historical_frozen_hashes_checked": len(inputs["historical_frozen_hashes"]),
        "package_files": len(files),
        "artifact_hashes": hashes,
        "backups_source_sha256": backup_hash,
        "independent_backup_acceptance": str(backup_acceptance) if backup_acceptance else None,
        "failures": failures,
        "publication": "PENDING_SEPARATE_VERIFICATION",
        "production_installation_and_activation": "PENDING_SEPARATE_VERIFICATION",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("source", "package"))
    parser.add_argument("--backup-acceptance", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    if args.mode == "package" and (args.wheel is None or args.sdist is None):
        parser.error("package mode requires --wheel and --sdist")
    report = verify(args.mode, args.wheel, args.sdist, args.backup_acceptance)
    print(json.dumps(report, indent=2))
    raise SystemExit(report["result"] != "PASS")
