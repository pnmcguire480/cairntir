"""Tests for the non-blocking update notifier."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cairntir import __version__, update


@pytest.fixture()
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    # Re-enable the notifier for these focused tests — conftest
    # disables it globally so unrelated tests do not hit PyPI.
    monkeypatch.delenv("CAIRNTIR_DISABLE_UPDATE_CHECK", raising=False)
    return home


def test_disable_env_var_blocks_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    assert update.pending_update_banner() is None


def test_disable_env_var_blocks_background_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    assert update.maybe_check_in_background() is None


def test_no_cache_returns_no_banner(_tmp_home: Path) -> None:
    assert update.pending_update_banner() is None


def test_banner_appears_when_newer_version_cached(_tmp_home: Path) -> None:
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "latest": "999.0.0",
    }
    update._cache_path().write_text(json.dumps(payload), encoding="utf-8")
    banner = update.pending_update_banner()
    assert banner is not None
    assert "999.0.0" in banner
    assert __version__ in banner
    assert "pip install -U cairntir" in banner


def test_banner_skipped_when_cached_version_is_older(_tmp_home: Path) -> None:
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "latest": "0.0.1",
    }
    update._cache_path().write_text(json.dumps(payload), encoding="utf-8")
    assert update.pending_update_banner() is None


def test_banner_skipped_when_cached_version_equals_current(_tmp_home: Path) -> None:
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "latest": __version__,
    }
    update._cache_path().write_text(json.dumps(payload), encoding="utf-8")
    assert update.pending_update_banner() is None


def test_corrupt_cache_swallowed(_tmp_home: Path) -> None:
    update._cache_path().write_text("not json at all", encoding="utf-8")
    assert update.pending_update_banner() is None


def test_fresh_cache_skips_background_check(_tmp_home: Path) -> None:
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "latest": __version__,
    }
    update._cache_path().write_text(json.dumps(payload), encoding="utf-8")
    assert update.maybe_check_in_background() is None


def test_stale_cache_triggers_background_check(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache older than the interval triggers a refresh thread."""
    payload = {
        "checked_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        "latest": __version__,
    }
    update._cache_path().write_text(json.dumps(payload), encoding="utf-8")

    called: list[bool] = []

    def _fake_fetch() -> str | None:
        called.append(True)
        return "9.9.9"

    monkeypatch.setattr(update, "_fetch_latest_from_pypi", _fake_fetch)
    thread = update.maybe_check_in_background()
    assert thread is not None
    thread.join(timeout=5)
    assert called, "background fetch was not invoked"
    cache = json.loads(update._cache_path().read_text(encoding="utf-8"))
    assert cache["latest"] == "9.9.9"


def test_version_tuple_parser_handles_pre_release() -> None:
    assert update._parse_version_tuple("1.2.3rc1") == (1, 2, 3)
    assert update._parse_version_tuple("2.0.0") == (2, 0, 0)
    assert update._parse_version_tuple("0.5") == (0, 5)
    assert update._parse_version_tuple("garbage") == ()


def test_is_newer_strict_inequality() -> None:
    assert update._is_newer("1.1.0", "1.0.0")
    assert update._is_newer("2.0.0", "1.99.99")
    assert not update._is_newer("1.0.0", "1.0.0")
    assert not update._is_newer("0.9.9", "1.0.0")


def test_failed_pypi_fetch_does_not_write_cache(
    _tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update, "_fetch_latest_from_pypi", lambda: None)
    update._check_now()
    assert not update._cache_path().exists()
