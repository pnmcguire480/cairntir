"""GitHub-only pre-releases need their own tag; stable versions get no such route."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_release_tags.py"


def _gate(
    monkeypatch: pytest.MonkeyPatch, versions: list[str], tags: set[str], published: set[str]
) -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_release_tags_alpha", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "changelog_versions", lambda: versions)
    monkeypatch.setattr(module, "current_version", lambda: versions[0])
    monkeypatch.setattr(module, "existing_tags", lambda: tags)
    monkeypatch.setattr(module, "pypi_published_versions", lambda: published)
    monkeypatch.delenv("CAIRNTIR_RELEASE_RECOVERY", raising=False)
    return module


def test_tagged_github_prerelease_passes_without_pypi(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = _gate(
        monkeypatch,
        ["2.0.0a2", "2.0.0a1", "1.12.4"],
        {"alpha-2.0.0a1", "v1.12.4"},
        {"1.12.4"},
    )
    assert gate.main() == 0


def test_prerelease_with_no_tag_still_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _gate(monkeypatch, ["2.0.0a2", "2.0.0a1", "1.12.4"], {"v1.12.4"}, {"1.12.4"})
    assert gate.main() == 1
    assert "declares 2.0.0a1" in capsys.readouterr().err


def test_alpha_tag_cannot_excuse_a_stable_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _gate(
        monkeypatch, ["2.0.0a2", "1.13.0", "1.12.4"], {"alpha-1.13.0", "v1.12.4"}, {"1.12.4"}
    )
    assert gate.main() == 1
    assert "declares 1.13.0" in capsys.readouterr().err


def test_v_tagged_prerelease_must_still_reach_pypi(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _gate(monkeypatch, ["2.0.0a2", "2.0.0a1"], {"v2.0.0a1"}, set())
    assert gate.main() == 1
    assert "tag v2.0.0a1 exists but PyPI" in capsys.readouterr().err
