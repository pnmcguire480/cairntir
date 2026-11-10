"""A host that guesses the wing wrong must be told what exists, not that memory is empty.

Reported on 2026-11-08: hosts other than the one doing the development "don't
recognize" Cairntir. The server connected for every host. Codex asked
``cairntir_handoff`` for a wing named after its working folder, which had never
been used, and was told the store "may be new or misconfigured" while it held
about 5,650 drawers in 80 wings. Other chats sent the folder name with a space
and were refused, while the wing existed under the hyphenated spelling.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import types

from cairntir.access import bind_grant, issue_grant
from cairntir.mcp.backend import CairntirBackend
from cairntir.mcp.server import build_server
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import canonical_wing


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DrawerStore:
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    return DrawerStore(tmp_path / "wings.db", HashEmbeddingProvider(dimension=32))


@pytest.fixture
def backend(store: DrawerStore) -> CairntirBackend:
    backend = CairntirBackend(store)
    backend.remember(wing="musician-pile", room="notes", content="the album plan")
    backend.remember(wing="completion-engine-source", room="notes", content="djinn checks")
    backend.remember(wing="cairntir", room="decisions", content="we chose sqlite")
    return backend


def _call(backend: CairntirBackend, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    handler = build_server(backend).request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = asyncio.run(handler(request)).root
    assert isinstance(result, types.CallToolResult)
    return result


def _text(result: types.CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if isinstance(block, types.TextContent))


def test_handoff_on_an_unused_wing_names_the_real_wings(backend: CairntirBackend) -> None:
    out = backend.handoff(wing="can")

    assert "DOES NOT EXIST" in out
    assert "not empty" in out
    assert "3 drawers across 3 wings" in out
    for wing in ("musician-pile", "completion-engine-source", "cairntir"):
        assert wing in out
    assert "misconfigured" not in out
    assert "without asking" in out


def test_handoff_puts_the_closest_wing_names_first(backend: CairntirBackend) -> None:
    for index in range(14):
        backend.remember(wing=f"filler-{index:02d}", room="notes", content="x")
        backend.remember(wing=f"filler-{index:02d}", room="notes", content="y")

    out = backend.handoff(wing="completion-engine")

    closest = next(line for line in out.splitlines() if line.startswith("Closest names:"))
    assert "completion-engine-source" in closest
    assert "filler" not in closest


def test_session_start_puts_the_closest_wing_names_first(backend: CairntirBackend) -> None:
    out = backend.session_start(wing="musician")

    closest = next(line for line in out.splitlines() if line.startswith("Closest names:"))
    assert "musician-pile" in closest


@pytest.mark.parametrize("wing", ["zzz", "pile", "engine"])
def test_no_closest_line_when_nothing_resembles_the_wing(
    backend: CairntirBackend, wing: str
) -> None:
    out = backend.handoff(wing=wing)

    assert "DOES NOT EXIST" in out
    assert "Closest names:" not in out


def test_handoff_on_a_genuinely_empty_store_keeps_its_plain_statement(
    store: DrawerStore,
) -> None:
    out = CairntirBackend(store).handoff(wing="anything")

    assert "Nothing is recorded for wing 'anything'" in out
    assert "do not substitute model memory" in out
    assert "DOES NOT EXIST" not in out


def test_handoff_on_a_real_wing_carries_no_warning(backend: CairntirBackend) -> None:
    out = backend.handoff(wing="cairntir")

    assert "DOES NOT EXIST" not in out
    assert "we chose sqlite" in out


def test_restricted_session_is_not_told_about_wings_it_cannot_read(store: DrawerStore) -> None:
    owner = CairntirBackend(store)
    owner.remember(wing="secret-project", room="notes", content="private plan")
    owner.remember(wing="shared", room="other-room", content="outside the granted room")
    token = issue_grant(
        store, scopes=[{"wing": "shared", "rooms": ["notes"]}], capabilities=["read"]
    )

    out = CairntirBackend(bind_grant(store, token)).handoff(wing="shared")

    assert "secret-project" not in out
    assert "private plan" not in out
    assert "other-room" not in out


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Musician Pile", "musician-pile"),
        ("musician pile", "musician-pile"),
        ("  Musician   Pile ", "musician-pile"),
        ("Musician	Pile", "musician-pile"),
        ("Youtube ideas for growth", "youtube-ideas-for-growth"),
        ("CAIRNTIR", "cairntir"),
    ],
)
def test_folder_style_names_become_the_hyphenated_wing(given: str, expected: str) -> None:
    assert canonical_wing(given) == expected


@pytest.mark.parametrize(
    "wing", ["cairntir", "agent:crucible", "i-x20", "v1.2", "a--b", "musician_pile"]
)
def test_valid_wings_are_left_exactly_as_given(wing: str) -> None:
    assert canonical_wing(wing) == wing


@pytest.mark.parametrize("wing", ["c", "", "a/b", "-lead", "Video (fork)", "x" * 80])
def test_names_that_cannot_become_a_wing_are_returned_unchanged(wing: str) -> None:
    assert canonical_wing(wing) == wing


def test_spaced_wing_reads_the_existing_hyphenated_wing_and_says_so(
    backend: CairntirBackend,
) -> None:
    result = _call(backend, "cairntir_handoff", {"wing": "Musician Pile"})

    out = _text(result)
    assert not result.isError
    assert "wing='musician-pile'" in out
    assert "the album plan" in out
    assert "'Musician Pile' was read as 'musician-pile'" in out


@pytest.mark.parametrize(
    ("tool", "extra"),
    [
        ("cairntir_remember", {"room": "notes", "content": "second track", "model": "test"}),
        (
            "cairntir_discover",
            {"title": "t", "summary": "s", "novelty": "user", "evidence_ids": [1]},
        ),
    ],
)
def test_a_write_under_a_spaced_wing_is_refused_with_the_spelling_to_use(
    backend: CairntirBackend, store: DrawerStore, tool: str, extra: dict[str, Any]
) -> None:
    before = store.wing_counts()

    result = _call(backend, tool, {"wing": "Musician Pile", **extra})

    assert result.isError
    assert "[cairntir error]" in _text(result)
    assert "Did you mean wing 'musician-pile'?" in _text(result)
    assert "was read as" not in _text(result)
    assert store.wing_counts() == before


def test_every_tool_that_reads_a_wing_accepts_the_folder_name() -> None:
    from cairntir.mcp.server import _WING_READ_TOOLS, _tool_specs

    takes_a_wing = {
        tool.name for tool in _tool_specs() if "wing" in tool.inputSchema.get("properties", {})
    }
    writers = {
        "cairntir_remember",
        "cairntir_discover",
        "cairntir_discover_scan",
        "cairntir_codeglass_record",
        "cairntir_audit",
        "cairntir_correct",
    }
    assert takes_a_wing - writers == _WING_READ_TOOLS


def test_valid_wing_gets_no_note(backend: CairntirBackend) -> None:
    result = _call(backend, "cairntir_handoff", {"wing": "cairntir"})

    assert "was read as" not in _text(result)


@pytest.mark.parametrize("wing", ["c", "a/b", "Video (fork)"])
def test_unusable_wing_is_still_refused_and_writes_nothing(
    backend: CairntirBackend, store: DrawerStore, wing: str
) -> None:
    before = store.wing_counts()

    result = _call(
        backend,
        "cairntir_remember",
        {"wing": wing, "room": "notes", "content": "should not land", "model": "test"},
    )

    assert result.isError
    assert "invalid" in _text(result)
    assert "Did you mean" not in _text(result)
    assert store.wing_counts() == before


def test_bounded_recall_stays_one_block_inside_its_budget(backend: CairntirBackend) -> None:
    result = _call(
        backend,
        "cairntir_recall",
        {"query": "album", "wing": "Musician Pile", "budget_chars": 4096},
    )

    assert not result.isError
    assert len(result.content) == 1, "a note would break the caller's size ceiling"
    assert len(_text(result)) <= 4096
    payload = json.loads(_text(result))
    found = [
        *payload["omitted"]["drawer_ids"],
        *(item["drawer_id"] for item in payload["evidence"]),
    ]
    assert found == [1], "the search ran in musician-pile, whose only drawer is #1"
