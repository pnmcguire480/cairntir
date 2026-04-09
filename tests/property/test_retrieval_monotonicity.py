"""Property-based retrieval monotonicity invariants.

These exercise the v1.0 guarantees the roadmap committed to:

1. The belief scorer is monotone in both inputs — reinforcing a drawer
   never makes its effective distance worse; weakening never makes it
   better; raising the raw vector distance never shrinks the effective
   distance.
2. A round-tripped drawer is always retrievable from the store under
   its own exact content (no-op for the semantic search layer, but
   the protocol promise is that the store never silently loses a
   drawer between add() and search()).

All of these are deterministic under :class:`HashEmbeddingProvider`,
which makes them safe to parametrize with Hypothesis.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from cairntir import Drawer
from cairntir.impl import DrawerStore, HashEmbeddingProvider
from cairntir.memory.belief import (
    DEFAULT_DELTA_BOOST,
    DEFAULT_MASS_FLOOR,
    effective_distance,
)

# Finite, non-negative floats the scorer actually sees in practice.
_finite_distance = st.floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False)
_non_negative_mass = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)


def _drawer(mass: float, *, delta: str | None = None) -> Drawer:
    return Drawer(
        wing="cairntir",
        room="monotonicity",
        content="x",
        belief_mass=mass,
        delta=delta,
    )


# --------- pure-scorer monotonicity ------------------------------------


@given(
    distance=_finite_distance,
    low_mass=_non_negative_mass,
    delta=_non_negative_mass,
)
def test_reinforcing_never_worsens_effective_distance(
    distance: float, low_mass: float, delta: float
) -> None:
    """Raising belief mass only ever lowers (or equals) effective distance."""
    before = effective_distance(_drawer(low_mass), distance)
    after = effective_distance(_drawer(low_mass + delta), distance)
    assert after <= before + 1e-12


@given(
    distance=_finite_distance,
    mass=_non_negative_mass,
    delta=_non_negative_mass,
)
def test_weakening_never_improves_effective_distance(
    distance: float, mass: float, delta: float
) -> None:
    """Lowering belief mass only ever raises (or equals) effective distance."""
    weakened = max(0.0, mass - delta)
    before = effective_distance(_drawer(mass), distance)
    after = effective_distance(_drawer(weakened), distance)
    assert after >= before - 1e-12


@given(
    raw=_finite_distance,
    extra=st.floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False),
    mass=_non_negative_mass,
)
def test_effective_distance_is_monotone_in_raw_distance(
    raw: float, extra: float, mass: float
) -> None:
    """A farther drawer never out-ranks a closer one at identical mass."""
    near = effective_distance(_drawer(mass), raw)
    far = effective_distance(_drawer(mass), raw + extra)
    assert far >= near - 1e-12


@given(distance=_finite_distance, mass=_non_negative_mass)
def test_delta_never_worsens_effective_distance(distance: float, mass: float) -> None:
    """Recording a surprise in ``delta`` never makes a drawer harder to find."""
    plain = effective_distance(_drawer(mass), distance)
    surprised = effective_distance(_drawer(mass, delta="observation diverged"), distance)
    assert surprised <= plain + 1e-12


@given(distance=_finite_distance)
def test_mass_floor_bounds_effective_distance_from_above(distance: float) -> None:
    """Zero-mass drawers are punished at the floor, not silently removed."""
    zero = effective_distance(_drawer(0.0), distance)
    assert zero == distance / DEFAULT_MASS_FLOOR  # exact by construction


@given(distance=_finite_distance, mass=_non_negative_mass)
def test_boost_factor_is_exactly_one_plus_delta_boost(distance: float, mass: float) -> None:
    """For any mass, the delta boost shrinks effective distance by the exact factor."""
    plain = effective_distance(_drawer(mass), distance)
    surprised = effective_distance(_drawer(mass, delta="x"), distance)
    if plain == 0:
        assert surprised == 0
    else:
        ratio = surprised / plain
        expected = 1.0 / (1.0 + DEFAULT_DELTA_BOOST)
        assert abs(ratio - expected) < 1e-9


# --------- store-level round-trip property -----------------------------


_content_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_characters={'"', "\\"},
    ),
    min_size=3,
    max_size=80,
).filter(lambda s: s.strip() != "")


@given(content=_content_strategy)
@settings(max_examples=25, deadline=None)
def test_round_tripped_drawer_is_retrievable_by_exact_content(
    content: str, tmp_path_factory: object
) -> None:
    """Any drawer added to the store must be retrievable under its own content.

    Cairntir's North Star: nothing remembered should ever silently
    disappear. This property checks the contract at the store level
    across arbitrary printable-ASCII content.
    """
    # Hypothesis rewinds state, so each example gets a fresh on-disk db.
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "rt.db"
        with DrawerStore(db, HashEmbeddingProvider(dimension=32)) as store:
            saved = store.add(Drawer(wing="cairntir", room="monotonicity", content=content))
            assert saved.id is not None
            hits = store.search(content, wing="cairntir", limit=5)
            assert any(d.content == content for d, _ in hits), (
                f"store lost a drawer it had just persisted: {content!r}"
            )
