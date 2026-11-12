"""Fail when a draft test promised to the alpha goes missing or is duplicated."""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "plans/acceptance/alpha-portable-tests-20261105/MANIFEST.json"
# Joined so this file never matches its own scan if the scan is ever widened.
MACHINE_PREFIXES = ("C:" + "\\Users", "C:" + "/Users", "/" + "Users/")
SCANNED_SUFFIXES = {".py", ".cjs", ".js", ".md"}


def manifest_entries(decision: str | None = None) -> list[dict[str, Any]]:
    """Return manifest entries, optionally limited to one decision."""
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["tests"]
    return [entry for entry in entries if decision in (None, entry["decision"])]


def package_files(package: str) -> list[Path]:
    """Return a ported package's test modules; a missing package has none."""
    return sorted((REPO / package).glob("test_*.py"))


def defined_tests(path: Path) -> list[str]:
    """Return every test function or method defined in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")
    ]


def problems_for(pr: int) -> list[str]:
    """Name each promised test of one draft PR that is missing or duplicated."""
    problems: list[str] = []
    for package in sorted(
        {entry["package"] for entry in manifest_entries("port") if entry["pr"] == pr}
    ):
        found = Counter(name for path in package_files(package) for name in defined_tests(path))
        for entry in manifest_entries("port"):
            if entry["pr"] != pr or entry["package"] != package:
                continue
            count = found[entry["test"]]
            if count != 1:
                problems.append(f"{package}: {entry['test']} defined {count} times")
    return problems


def machine_paths() -> list[str]:
    """Return ported files carrying a user-profile path from one machine."""
    hits: list[str] = []
    for package in sorted({entry["package"] for entry in manifest_entries("port")}):
        for path in sorted((REPO / package).rglob("*")):
            if path.suffix not in SCANNED_SUFFIXES or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if any(prefix in text for prefix in MACHINE_PREFIXES):
                hits.append(path.relative_to(REPO).as_posix())
    return hits


def test_manifest_accounts_for_every_draft_test() -> None:
    assert Counter(entry["decision"] for entry in manifest_entries()) == {"port": 112, "leave": 30}


def test_manifest_names_each_draft_test_once_per_pr() -> None:
    keys = Counter((entry["pr"], entry["test"]) for entry in manifest_entries())
    assert [key for key, count in keys.items() if count != 1] == []


def test_every_left_behind_test_records_a_reason_and_source_hash() -> None:
    left = manifest_entries("leave")
    assert all(entry["reason"] and entry["source_sha256"] for entry in left)


@pytest.mark.parametrize("pr", [125, 126, 128, 129, 131])
def test_every_ported_test_exists_exactly_once(pr: int) -> None:
    assert problems_for(pr) == []


def test_ported_packages_contain_no_machine_paths() -> None:
    assert machine_paths() == []
