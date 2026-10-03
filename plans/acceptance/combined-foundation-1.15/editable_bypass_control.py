"""Inert wrong control: allow generic edits to structured records in this process."""

import pytest

from cairntir import obsidian_bridge


@pytest.fixture(autouse=True)
def bypass_structured_correction_guard(monkeypatch):
    monkeypatch.setattr(obsidian_bridge, "_editable", lambda _drawer: True)
