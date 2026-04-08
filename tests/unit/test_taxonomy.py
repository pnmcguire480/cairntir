"""Unit tests for the wing/room/drawer taxonomy."""

from __future__ import annotations

import pytest

from cairntir.errors import TaxonomyError
from cairntir.memory.taxonomy import Drawer, Layer


def test_drawer_defaults_to_on_demand_layer() -> None:
    d = Drawer(wing="cairntir", room="phase-1", content="hello")
    assert d.layer is Layer.ON_DEMAND
    assert d.metadata == {}
    assert d.id is None


def test_drawer_accepts_custom_layer_and_metadata() -> None:
    d = Drawer(
        wing="cairntir",
        room="identity",
        content="Patrick owns this repo.",
        layer=Layer.IDENTITY,
        metadata={"source": "claude.md"},
    )
    assert d.layer is Layer.IDENTITY
    assert d.metadata == {"source": "claude.md"}


@pytest.mark.parametrize("bad", ["", "A", "has space", "-leading", "trailing-", "with/slash"])
def test_drawer_rejects_invalid_wing(bad: str) -> None:
    with pytest.raises(TaxonomyError):
        Drawer(wing=bad, room="ok", content="x")


def test_drawer_rejects_blank_content() -> None:
    with pytest.raises(TaxonomyError):
        Drawer(wing="cairntir", room="phase-1", content="   ")


def test_layer_is_string_enum() -> None:
    assert Layer.IDENTITY.value == "identity"
    assert Layer("deep") is Layer.DEEP
