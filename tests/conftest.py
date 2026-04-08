"""Shared pytest fixtures for the Cairntir test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_cairntir_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Provide an isolated temporary Cairntir home directory for a single test."""
    home = tmp_path / ".cairntir"
    home.mkdir()
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    yield home
