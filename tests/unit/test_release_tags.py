from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_release_tags.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_release_tags", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_released_changelog_version_is_tagged() -> None:
    # Shallow clones carry no tags. The binding gate is the release workflow,
    # which fetches them explicitly; skipping here keeps forks and shallow
    # checkouts from failing on clone depth rather than on a real defect.
    if not _load_script().existing_tags():
        pytest.skip("no v*.*.* tags in this checkout")

    result = subprocess.run(  # noqa: S603 - argv is sys.executable plus a literal path
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_changelog_versions_are_parsed_newest_first() -> None:
    versions = _load_script().changelog_versions()
    assert "1.2.0" in versions
    assert "1.0.0" in versions
    assert versions.index("1.2.0") < versions.index("1.0.0")


def test_current_version_matches_the_newest_changelog_entry() -> None:
    module = _load_script()
    assert module.changelog_versions()[0] == module.current_version()


def test_known_unreleased_records_the_versions_that_never_shipped() -> None:
    known = _load_script().KNOWN_UNRELEASED
    assert set(known) == {"1.0.1", "1.1.3"}
    assert all(reason.strip() for reason in known.values())


def test_the_check_runs_as_a_release_gate_with_tags_fetched() -> None:
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "scripts/check_release_tags.py" in release
    assert "fetch-depth: 0" in release
