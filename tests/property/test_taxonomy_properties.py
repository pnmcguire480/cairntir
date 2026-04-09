"""Property-based invariants for the wing / room / drawer taxonomy."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from cairntir import Drawer, Layer, TaxonomyError

_IDENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$")

# Valid identifiers: 2-64 chars, start/end alphanumeric, middle may include . _ -
_valid_ident = st.from_regex(_IDENT_RE, fullmatch=True).filter(lambda s: len(s) <= 64)

# Non-empty content that survives the "must not be whitespace-only" check.
_valid_content = st.text(min_size=1, max_size=500).filter(lambda s: s.strip() != "")


@given(wing=_valid_ident, room=_valid_ident, content=_valid_content)
def test_valid_identifiers_are_always_accepted(wing: str, room: str, content: str) -> None:
    drawer = Drawer(wing=wing, room=room, content=content)
    assert drawer.wing == wing
    assert drawer.room == room
    assert drawer.content == content


@given(st.text(max_size=3).filter(lambda s: not _IDENT_RE.match(s)))
def test_invalid_wing_identifiers_are_rejected(bad: str) -> None:
    try:
        Drawer(wing=bad, room="valid-room", content="x")
    except TaxonomyError:
        return
    except Exception:  # noqa: BLE001 — pydantic wraps ours; any rejection is acceptable
        return
    raise AssertionError(f"invalid wing {bad!r} was accepted")


@given(content=st.text(max_size=10).filter(lambda s: s.strip() == ""))
def test_whitespace_content_is_rejected(content: str) -> None:
    try:
        Drawer(wing="cairntir", room="room-a", content=content)
    except TaxonomyError:
        return
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("whitespace-only content was accepted")


@given(mass=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))
def test_belief_mass_round_trips_through_drawer_construction(mass: float) -> None:
    drawer = Drawer(wing="cairntir", room="room-a", content="x", belief_mass=mass)
    assert drawer.belief_mass == mass


@given(layer=st.sampled_from(list(Layer)))
def test_layer_is_preserved_on_drawer_construction(layer: Layer) -> None:
    drawer = Drawer(wing="cairntir", room="room-a", content="x", layer=layer)
    assert drawer.layer == layer
