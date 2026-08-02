"""Unit tests for cairntir.cost — P5, closed at last.

The audit that scored P5 MISSING deferred it "until cost becomes a real
concern." These tests exist so the number, once it exists, stays honest:
an estimate that silently drifts is worse than no estimate, because
decisions get made on it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.cost import (
    EMBEDDER_CHAR_WINDOW,
    _percentile,
    corpus_stats,
    estimate_tokens,
    measure,
    render,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "cost.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _add(store: DrawerStore, chars: int, *, layer: Layer = Layer.ESSENTIAL) -> None:
    store.add(Drawer(wing="cairntir", room="journey", content="x" * chars, layer=layer))


# ------------------------------------------------------------------ estimates


def test_the_token_estimate_uses_the_documented_divisor() -> None:
    """Comparability with the research document depends on this staying 4."""
    assert estimate_tokens(4_000) == 1_000


def test_percentiles_are_nearest_rank_with_no_interpolation() -> None:
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert _percentile(values, 50) == 50
    assert _percentile(values, 90) == 90
    assert _percentile(values, 100) == 100


def test_percentile_of_nothing_is_zero_not_a_crash() -> None:
    assert _percentile([], 50) == 0


# -------------------------------------------------------------------- corpus


def test_drawers_over_the_embedder_window_are_counted(store: DrawerStore) -> None:
    """The finding this makes measurable: content stored but never vectorised."""
    _add(store, 500)
    _add(store, 900)
    _add(store, EMBEDDER_CHAR_WINDOW + 1_000)

    stats = corpus_stats(store, wing="cairntir")

    assert stats.drawers == 3
    assert stats.over_window == 1
    assert stats.over_window_pct == 33


def test_the_worst_embedded_share_is_reported(store: DrawerStore) -> None:
    _add(store, EMBEDDER_CHAR_WINDOW * 4)

    stats = corpus_stats(store, wing="cairntir")

    assert stats.worst_embedded_pct == 25


def test_a_corpus_that_fits_reports_no_truncation(store: DrawerStore) -> None:
    _add(store, 100)

    stats = corpus_stats(store, wing="cairntir")

    assert stats.over_window == 0
    assert "every drawer fits" in render(measure(store, wing="cairntir"))


def test_an_empty_wing_does_not_divide_by_zero(store: DrawerStore) -> None:
    stats = corpus_stats(store, wing="cairntir")

    assert stats.drawers == 0
    assert stats.over_window_pct == 0


# ------------------------------------------------------------------- measure


def test_the_report_measures_all_three_surfaces(store: DrawerStore) -> None:
    _add(store, 800)

    report = measure(store, wing="cairntir")

    names = [m.name for m in report.measurements]
    assert any(n.startswith("tool catalog") for n in names)
    assert "session_start" in names
    assert any(n.startswith("handoff") for n in names)


def test_the_tool_catalog_is_counted_because_it_is_never_free(store: DrawerStore) -> None:
    """1,918 tokens measured across 18 tools, paid whether or not any is called."""
    report = measure(store, wing="cairntir")

    catalog = next(m for m in report.measurements if m.name.startswith("tool catalog"))
    assert catalog.chars > 0
    assert "every session" in catalog.note


def test_measuring_does_not_write_to_the_store(store: DrawerStore) -> None:
    """The report must not change what it reports."""
    _add(store, 800)
    before = len(store.list_by(wing="cairntir", limit=1_000))

    measure(store, wing="cairntir")

    assert len(store.list_by(wing="cairntir", limit=1_000)) == before


def test_the_comparison_is_honest_when_handoff_costs_more(store: DrawerStore) -> None:
    """handoff is not universally cheaper, and must never claim to be.

    On a wing holding a few large drawers, stubs genuinely cost less than
    whole content — the saving on the live store comes from `session_start`
    also loading every other wing's identity drawers and 40 essential
    stubs. A report that only ever said "cheaper" would be marketing.
    """
    for _ in range(4):
        _add(store, 6_000)

    report = measure(store, wing="cairntir")
    session = next(m for m in report.measurements if m.name == "session_start")
    handoff = next(m for m in report.measurements if m.name.startswith("handoff"))
    rendered = render(report)

    assert handoff.tokens > session.tokens, "expected whole content to cost more here"
    assert "more expensive than session_start" in rendered
    assert "cheaper than session_start" not in rendered


def test_the_comparison_names_the_saving_when_there_is_one(store: DrawerStore) -> None:
    """The live-store case: many stubs, most of them never read."""
    for _ in range(40):
        _add(store, 120)

    report = measure(store, wing="cairntir")
    session = next(m for m in report.measurements if m.name == "session_start")
    handoff = next(m for m in report.measurements if m.name.startswith("handoff"))

    assert handoff.tokens < session.tokens
    assert "cheaper than session_start" in render(report)


def test_render_reports_the_embedder_window_finding(store: DrawerStore) -> None:
    _add(store, EMBEDDER_CHAR_WINDOW * 3)

    rendered = render(measure(store, wing="cairntir"))

    assert "exceed the embedder" in rendered
    assert "retrieval defect, not a storage one" in rendered
