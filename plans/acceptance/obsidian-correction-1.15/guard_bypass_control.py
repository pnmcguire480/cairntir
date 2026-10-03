"""Deliberate wrong control: suppress transaction detection in test process only."""

import pytest

from cairntir.memory.store import DrawerStore


@pytest.fixture(autouse=True)
def bypass_transaction_guard(monkeypatch):
    monkeypatch.setattr(DrawerStore, "transaction_active", property(lambda self: False))
