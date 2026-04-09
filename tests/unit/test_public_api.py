"""Public API snapshot for v1.0.

If this test fails, you have changed Cairntir's public surface. That is
a *stability-affecting* change under the v1.0 deprecation policy:

* Adding a name is a minor bump; update the snapshot.
* Removing or renaming a name requires two minor releases of
  ``CairntirDeprecationWarning`` first.
* Changing what a name *points to* — e.g. swapping a protocol for a
  concrete class — is never allowed silently; it is either a bugfix
  (no visible change) or a breaking change (major bump).

The snapshot is intentionally a flat set. Attribute drift on the
value types themselves is covered by the contract and property
tests, not here.
"""

from __future__ import annotations

import cairntir

EXPECTED_PUBLIC_NAMES: frozenset[str] = frozenset(
    {
        # Protocols — the stable seam.
        "BeliefStore",
        "EmbeddingProvider",
        "ExperimentRunner",
        "HypothesisProposer",
        "MemoryGateway",
        "Store",
        # Frozen value types.
        "BeliefUpdate",
        "Drawer",
        "Experiment",
        "Hypothesis",
        "Layer",
        "Outcome",
        # Typed exceptions.
        "CairntirDeprecationWarning",
        "CairntirError",
        "ConfigError",
        "EmbeddingError",
        "ExternalUrlError",
        "MCPError",
        "MemoryStoreError",
        "PortableFormatError",
        "RetrievalError",
        "SkillError",
        "TaxonomyError",
        # Version.
        "__version__",
    }
)


def _public_names() -> frozenset[str]:
    import types

    names = {
        name
        for name in dir(cairntir)
        if not name.startswith("_")
        and name != "annotations"  # from __future__ import annotations leaks this name
        and not isinstance(getattr(cairntir, name), types.ModuleType)
    }
    names.add("__version__")
    return frozenset(names)


def test_public_api_matches_snapshot() -> None:
    actual = _public_names()
    extra = actual - EXPECTED_PUBLIC_NAMES
    missing = EXPECTED_PUBLIC_NAMES - actual
    assert not extra and not missing, (
        f"cairntir public API drifted.\nunexpected: {sorted(extra)}\nmissing:    {sorted(missing)}"
    )


def test_dunder_all_matches_snapshot() -> None:
    assert frozenset(cairntir.__all__) == EXPECTED_PUBLIC_NAMES


def test_version_is_v1() -> None:
    assert cairntir.__version__.startswith("1.")
