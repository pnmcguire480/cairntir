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


def test_known_unpublished_records_the_versions_that_never_reached_pypi() -> None:
    known = _load_script().KNOWN_UNPUBLISHED
    assert set(known) == {"0.1.0", "1.1.1"}
    assert all(reason.strip() for reason in known.values())


def test_pypi_published_versions_counts_only_releases_with_files() -> None:
    module = _load_script()
    payload = (
        '{"releases": {"1.3.0": [{"filename": "cairntir-1.3.0.tar.gz"}], '
        '"1.1.1": [], "1.2.0": [{"filename": "cairntir-1.2.0-py3-none-any.whl"}]}}'
    )
    published = module.pypi_published_versions(fetch=lambda _url: payload)
    assert published == {"1.3.0", "1.2.0"}


def test_pypi_published_versions_rejects_an_unexpected_shape() -> None:
    module = _load_script()
    with pytest.raises(TypeError, match="releases"):
        module.pypi_published_versions(fetch=lambda _url: '{"releases": "wrong"}')


def test_unpublished_flags_only_the_missing_versions() -> None:
    module = _load_script()
    missing = module.unpublished(["1.3.0", "1.2.0", "1.1.2"], {"1.3.0", "1.2.0"})
    assert missing == ["1.1.2"]


def test_current_version_is_verified_after_its_tag_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    monkeypatch.delenv(module.RELEASE_RECOVERY_ENV, raising=False)
    monkeypatch.setattr(module, "existing_tags", lambda: {"v1.7.1"})
    monkeypatch.setattr(module, "current_version", lambda: "1.7.1")
    monkeypatch.setattr(module, "changelog_versions", lambda: ["1.7.1"])
    monkeypatch.setattr(module, "pypi_published_versions", lambda: {"1.7.1"})

    assert module.main() == 0
    assert "in-flight" not in capsys.readouterr().out


def test_untagged_current_version_remains_in_flight(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    monkeypatch.delenv(module.RELEASE_RECOVERY_ENV, raising=False)
    monkeypatch.setattr(module, "existing_tags", lambda: {"v1.7.0"})
    monkeypatch.setattr(module, "current_version", lambda: "1.7.1")
    monkeypatch.setattr(module, "changelog_versions", lambda: ["1.7.1", "1.7.0"])
    monkeypatch.setattr(module, "pypi_published_versions", lambda: {"1.7.0"})

    assert module.main() == 0
    assert "in-flight: 1.7.1" in capsys.readouterr().out


def test_tagged_current_version_must_exist_on_pypi(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    monkeypatch.delenv(module.RELEASE_RECOVERY_ENV, raising=False)
    monkeypatch.setattr(module, "existing_tags", lambda: {"v1.7.1"})
    monkeypatch.setattr(module, "current_version", lambda: "1.7.1")
    monkeypatch.setattr(module, "changelog_versions", lambda: ["1.7.1"])
    monkeypatch.setattr(module, "pypi_published_versions", lambda: set())

    assert module.main() == 1
    assert "tag v1.7.1 exists but PyPI serves no files" in capsys.readouterr().err


def test_explicit_ci_recovery_defers_current_pypi_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv(module.RELEASE_RECOVERY_ENV, "1.7.1")
    monkeypatch.setattr(module, "existing_tags", lambda: {"v1.7.1"})
    monkeypatch.setattr(module, "current_version", lambda: "1.7.1")
    monkeypatch.setattr(module, "changelog_versions", lambda: ["1.7.1"])
    monkeypatch.setattr(module, "pypi_published_versions", lambda: set())

    assert module.main() == 0
    assert "release recovery: 1.7.1" in capsys.readouterr().out


def test_recovery_refuses_a_version_other_than_current(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv(module.RELEASE_RECOVERY_ENV, "1.7.0")
    monkeypatch.setattr(module, "existing_tags", lambda: {"v1.7.1", "v1.7.0"})
    monkeypatch.setattr(module, "current_version", lambda: "1.7.1")

    assert module.main() == 1
    assert "invalid CAIRNTIR_RELEASE_RECOVERY" in capsys.readouterr().err


def test_the_check_runs_as_a_release_gate_with_tags_fetched() -> None:
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "scripts/check_release_tags.py" in release
    assert "fetch-depth: 0" in release
    assert "Verify PyPI publication" in release
    assert "needs: [build, verify-published]" in release
