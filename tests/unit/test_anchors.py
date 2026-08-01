"""Unit tests for structural anchors and recall-for-change (Tier 1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.errors import AnchorError, RetrievalError
from cairntir.memory.anchors import (
    Anchor,
    normalize_path,
    parse_anchors,
    paths_intersect,
    recall_for_change,
)
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[DrawerStore]:
    with DrawerStore(tmp_path / "anchors.db", HashEmbeddingProvider(dimension=32)) as s:
        yield s


def _anchored(
    room: str,
    content: str,
    *paths: str,
    symbol: str | None = None,
) -> Drawer:
    entries: list[dict[str, str]] = []
    for path in paths:
        entry: dict[str, str] = {"path": path}
        if symbol is not None:
            entry["symbol"] = symbol
        entries.append(entry)
    return Drawer(
        wing="cairntir",
        room=room,
        content=content,
        metadata={"anchors": entries},
    )


# --------- normalize_path ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/cairntir/cli.py", "src/cairntir/cli.py"),
        ("src\\cairntir\\cli.py", "src/cairntir/cli.py"),
        ("./src/cairntir/cli.py", "src/cairntir/cli.py"),
        (".//src//cairntir//cli.py", "src/cairntir/cli.py"),
        ("  src/cairntir/cli.py  ", "src/cairntir/cli.py"),
        ("src/cairntir/", "src/cairntir"),
        ("/", "/"),
    ],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


def test_normalize_path_preserves_case() -> None:
    """POSIX filesystems are case-sensitive; folding would create false matches."""
    assert normalize_path("src/Cairntir/CLI.py") == "src/Cairntir/CLI.py"


# --------- paths_intersect -----------------------------------------------


def test_paths_intersect_exact() -> None:
    assert paths_intersect("src/cairntir/cli.py", "src/cairntir/cli.py")


def test_paths_intersect_across_separator_styles() -> None:
    assert paths_intersect("src/cairntir/cli.py", "src\\cairntir\\cli.py")


def test_paths_intersect_absolute_changed_path_matches_relative_anchor() -> None:
    assert paths_intersect("src/cairntir/cli.py", "C:/Dev/Cairntir/src/cairntir/cli.py")


def test_paths_intersect_relative_changed_path_matches_absolute_anchor() -> None:
    assert paths_intersect("C:/Dev/Cairntir/src/cairntir/cli.py", "src/cairntir/cli.py")


def test_paths_intersect_respects_segment_boundary() -> None:
    """cli.py must not match fastcli.py — the load-bearing half of suffix matching."""
    assert not paths_intersect("cli.py", "src/cairntir/fastcli.py")
    assert not paths_intersect("memory/store.py", "src/other/inmemory/store.py")


def test_paths_intersect_rejects_empty() -> None:
    assert not paths_intersect("", "src/cairntir/cli.py")
    assert not paths_intersect("src/cairntir/cli.py", "   ")


def test_paths_intersect_distinct_files_do_not_match() -> None:
    assert not paths_intersect("src/cairntir/cli.py", "src/cairntir/store.py")


# --------- parse_anchors -------------------------------------------------


def test_parse_anchors_absent_key_is_not_an_error() -> None:
    assert parse_anchors({}) == ()
    assert parse_anchors({"topic": "release"}) == ()


def test_parse_anchors_reads_full_shape() -> None:
    parsed = parse_anchors(
        {
            "anchors": [
                {
                    "path": "src\\cairntir\\memory\\embeddings.py",
                    "symbol": "SentenceTransformerProvider",
                    "symbol_source_hash": "9f86d081",
                }
            ]
        }
    )
    assert parsed == (
        Anchor(
            path="src/cairntir/memory/embeddings.py",
            symbol="SentenceTransformerProvider",
            symbol_source_hash="9f86d081",
        ),
    )


def test_parse_anchors_path_only_is_valid() -> None:
    parsed = parse_anchors({"anchors": [{"path": "src/cairntir/cli.py"}]})
    assert parsed == (Anchor(path="src/cairntir/cli.py", symbol=None, symbol_source_hash=None),)


@pytest.mark.parametrize(
    "metadata",
    [
        {"anchors": "src/cairntir/cli.py"},
        {"anchors": ["src/cairntir/cli.py"]},
        {"anchors": [{"symbol": "main"}]},
        {"anchors": [{"path": ""}]},
        {"anchors": [{"path": "   "}]},
        {"anchors": [{"path": "a.py", "symbol": 42}]},
        {"anchors": [{"path": "a.py", "symbol_source_hash": []}]},
    ],
)
def test_parse_anchors_rejects_malformed(metadata: dict[str, object]) -> None:
    with pytest.raises(AnchorError):
        parse_anchors(metadata)


def test_anchor_error_is_a_retrieval_error() -> None:
    """Typed and surfaced — AnchorError must slot into the existing hierarchy."""
    assert issubclass(AnchorError, RetrievalError)


# --------- recall_for_change ---------------------------------------------


def test_recall_for_change_surfaces_anchored_drawer(store: DrawerStore) -> None:
    kept = store.add(
        _anchored("architecture", "cold-start arc", "src/cairntir/memory/embeddings.py")
    )
    store.add(_anchored("architecture", "unrelated", "src/cairntir/cli.py"))

    result = recall_for_change(store, ["src/cairntir/memory/embeddings.py"], wing="cairntir")

    assert [m.drawer.id for m in result.matches] == [kept.id]
    assert result.matches[0].anchors[0].path == "src/cairntir/memory/embeddings.py"
    assert result.matches[0].files == ("src/cairntir/memory/embeddings.py",)


def test_recall_for_change_matches_windows_separators(store: DrawerStore) -> None:
    kept = store.add(_anchored("architecture", "arc", "src/cairntir/memory/embeddings.py"))
    result = recall_for_change(store, ["src\\cairntir\\memory\\embeddings.py"], wing="cairntir")
    assert [m.drawer.id for m in result.matches] == [kept.id]


def test_recall_for_change_matches_absolute_changed_path(store: DrawerStore) -> None:
    kept = store.add(_anchored("architecture", "arc", "src/cairntir/cli.py"))
    result = recall_for_change(store, ["C:/Dev/Cairntir/src/cairntir/cli.py"], wing="cairntir")
    assert [m.drawer.id for m in result.matches] == [kept.id]


def test_recall_for_change_ignores_unanchored_drawers(store: DrawerStore) -> None:
    """The opt-in mechanism: no anchors means never surfaced, by construction."""
    store.add(Drawer(wing="cairntir", room="identity", content="who Patrick is"))
    result = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")
    assert result.matches == ()
    assert result.scanned == 0


def test_recall_for_change_scopes_by_room(store: DrawerStore) -> None:
    code = store.add(_anchored("architecture", "code-facing", "src/cairntir/cli.py"))
    store.add(_anchored("release", "collab-facing", "src/cairntir/cli.py"))

    result = recall_for_change(
        store, ["src/cairntir/cli.py"], wing="cairntir", rooms=["architecture"]
    )
    assert [m.drawer.id for m in result.matches] == [code.id]


def test_recall_for_change_scopes_by_wing(store: DrawerStore) -> None:
    store.add(_anchored("architecture", "cairntir drawer", "src/cairntir/cli.py"))
    other = Drawer(
        wing="other-project",
        room="architecture",
        content="different project",
        metadata={"anchors": [{"path": "src/cairntir/cli.py"}]},
    )
    store.add(other)

    scoped = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")
    assert {m.drawer.wing for m in scoped.matches} == {"cairntir"}

    unscoped = recall_for_change(store, ["src/cairntir/cli.py"])
    assert {m.drawer.wing for m in unscoped.matches} == {"cairntir", "other-project"}


def test_recall_for_change_reports_only_matching_anchors(store: DrawerStore) -> None:
    store.add(
        _anchored(
            "architecture",
            "two anchors",
            "src/cairntir/cli.py",
            "src/cairntir/memory/store.py",
        )
    )
    result = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")
    assert len(result.matches) == 1
    assert [a.path for a in result.matches[0].anchors] == ["src/cairntir/cli.py"]


def test_recall_for_change_surfaces_malformed_rather_than_raising(store: DrawerStore) -> None:
    """One bad anchor must not blind the whole recall — but must stay visible."""
    good = store.add(_anchored("architecture", "good", "src/cairntir/cli.py"))
    bad = store.add(
        Drawer(
            wing="cairntir",
            room="architecture",
            content="bad anchor",
            metadata={"anchors": [{"symbol": "no path here"}]},
        )
    )

    result = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")

    assert [m.drawer.id for m in result.matches] == [good.id]
    assert result.malformed_drawer_ids == (bad.id,)


def test_recall_for_change_respects_limit(store: DrawerStore) -> None:
    for index in range(5):
        store.add(_anchored("architecture", f"drawer {index}", "src/cairntir/cli.py"))
    result = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir", limit=2)
    assert len(result.matches) == 2


@pytest.mark.parametrize("files", [[], [""], ["   "]])
def test_recall_for_change_empty_input_returns_empty(store: DrawerStore, files: list[str]) -> None:
    store.add(_anchored("architecture", "drawer", "src/cairntir/cli.py"))
    result = recall_for_change(store, files, wing="cairntir")
    assert result.matches == ()
    assert result.scanned == 0


def test_recall_for_change_nonpositive_limit_returns_empty(store: DrawerStore) -> None:
    store.add(_anchored("architecture", "drawer", "src/cairntir/cli.py"))
    assert recall_for_change(store, ["src/cairntir/cli.py"], limit=0).matches == ()


def test_recall_for_change_does_not_flag_staleness(store: DrawerStore) -> None:
    """A2 hold: symbol_source_hash is stored and never compared.

    A drawer whose recorded hash no longer matches anything still surfaces
    normally, with no staleness marker anywhere on the result. This test is
    the guard that keeps the hold honest — it fails the moment someone wires
    hash comparison in without testing rename survival first.
    """
    store.add(
        Drawer(
            wing="cairntir",
            room="architecture",
            content="anchored with a stale hash",
            metadata={
                "anchors": [
                    {
                        "path": "src/cairntir/cli.py",
                        "symbol": "main",
                        "symbol_source_hash": "definitely-not-the-current-hash",
                    }
                ]
            },
        )
    )
    result = recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")

    assert len(result.matches) == 1
    assert not hasattr(result, "stale")
    assert not hasattr(result.matches[0], "stale")
    assert result.matches[0].anchors[0].symbol_source_hash == "definitely-not-the-current-hash"


def test_recall_for_change_is_read_only(store: DrawerStore) -> None:
    """Recall must not demote, touch, or otherwise mutate what it surfaces."""
    added = store.add(_anchored("architecture", "unchanged", "src/cairntir/cli.py"))
    assert added.id is not None
    before = store.get(added.id)
    assert before is not None

    recall_for_change(store, ["src/cairntir/cli.py"], wing="cairntir")

    after = store.get(added.id)
    assert after is not None
    assert after.content == before.content
    assert after.layer == before.layer
    assert after.metadata == before.metadata
    assert after.belief_mass == before.belief_mass
