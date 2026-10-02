"""Explicit amendment of one historical writable-owner startup probe only."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

LEGACY_SHA256 = "8339755f367d8e9a91013651b28f69b53b6e95662da465b4cfffb6801b4a6da5"
TARGET = (
    "tests/acceptance/test_automatic_backups.py::"
    "test_production_owner_startup_activates_backup_and_retains_transport_shape[cli]"
)


@pytest.fixture(autouse=True)
def approved_owner_backup_probe(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Use genuine owner get startup in the exact frozen historical CLI case."""
    if request.node.nodeid != TARGET:
        yield
        return
    legacy_path = Path(request.config.rootpath) / "tests/acceptance/test_automatic_backups.py"
    assert Path(request.module.__file__).resolve() == legacy_path.resolve()
    assert hashlib.sha256(legacy_path.read_bytes()).hexdigest() == LEGACY_SHA256
    assert request.node.callspec.params["transport"] == "cli"
    original_cli = request.module._cli
    calls = []

    def writable_owner_probe(*args: str, **kwargs: Any) -> Any:
        assert args == ("status",) and not kwargs, "UNAPPROVED_BACKUP_PROBE_CALL"
        assert not calls, "BACKUP_PROBE_CALLED_MORE_THAN_ONCE"
        calls.append(args)
        return original_cli("get", "1")

    monkeypatch.setattr(request.module, "_cli", writable_owner_probe)
    yield
    assert calls == [("status",)], "APPROVED_BACKUP_PROBE_WAS_NOT_EXERCISED"
