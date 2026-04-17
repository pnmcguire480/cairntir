"""Shared pytest fixtures for the Cairntir test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_runtime_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quiet the CLI's silent self-heal + update notifier during tests.

    Production CLI invocations call ``ensure_registered()`` and spawn a
    background PyPI thread on every run. In tests both behaviors would
    either touch the developer's real home dir, hit the network, or
    leak a daemon thread into the next test. The env vars are the
    documented opt-out.
    """
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")


@pytest.fixture()
def tmp_cairntir_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Provide an isolated temporary Cairntir home directory for a single test."""
    home = tmp_path / ".cairntir"
    home.mkdir()
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    yield home
