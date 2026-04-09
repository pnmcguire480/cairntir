"""LongMemEval-style R@5 subset, run with sentence-transformers.

This test exercises the full memory stack end-to-end with the production
embedder on a small, hand-curated subset modeled on LongMemEval's
single-session-user questions. The subset is paraphrased — questions are
written in different words than the target drawer — so a non-trivial
semantic model is required to rank the relevant drawer in the top-5.

**Bar:** R@5 >= 0.80 — the Phase 1 target from ``docs/roadmap.md``.

The test is gated behind ``@pytest.mark.eval`` so it is opt-in:

    pytest -m eval

Run it explicitly; the default ``pytest`` invocation skips eval tests to
keep CI fast and hermetic. When the real LongMemEval dataset ships, this
file will load it from ``tests/eval/data/`` instead of the inline fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cairntir.memory.embeddings import SentenceTransformerProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

# Each tuple: (question, relevant_drawer_content).
# Questions are deliberately paraphrased so lexical overlap with the target
# drawer is low — exercising semantic retrieval, not substring matching.
_RELEVANT: list[tuple[str, str]] = [
    (
        "how does cairntir stop an AI from forgetting between chats?",
        "Cairntir is a memory-first reasoning layer that kills cross-chat AI amnesia.",
    ),
    (
        "what vector database backs the drawer store?",
        "The persistence layer uses sqlite-vec — an embedded vector index on top of SQLite.",
    ),
    (
        "who owns the project and wrote its manifesto?",
        "Patrick McGuire is the owner of the Cairntir repository and author of the manifesto.",
    ),
    (
        "what is the taxonomy for organizing memories?",
        "Memories are organized as wings, rooms, and drawers for projects, topics, and text.",
    ),
    (
        "how many retrieval layers does the system have?",
        "Cairntir loads context in four layers: identity, essential, on-demand, and deep.",
    ),
    (
        "which skill is used to stress-test assumptions?",
        "The Crucible skill performs epistemic stress-testing of claims and assumptions.",
    ),
    (
        "what license is cairntir released under?",
        "Cairntir is open source and distributed under the MIT license.",
    ),
    (
        "what replaces the old init and wrapup ceremony?",
        "A background daemon auto-captures conversations and restores context automatically.",
    ),
    (
        "what is the project's pronunciation?",
        "Cairntir is pronounced CAIRN-teer, blending 'cairn' and 'palantir'.",
    ),
    (
        "which MCP tool starts a fresh session?",
        "The session_start tool loads the 4-layer context for a wing at the beginning of a chat.",
    ),
]

# Generic distractors added to the store so recall is non-trivial.
_DISTRACTORS: list[str] = [
    "The weather in Portland is usually overcast in November.",
    "Rust's borrow checker prevents data races at compile time.",
    "Sourdough starters need to be fed with flour and water daily.",
    "The Fibonacci sequence appears frequently in nature.",
    "TCP uses a three-way handshake to establish connections.",
    "Espresso is brewed by forcing pressurized water through coffee grounds.",
    "The Voyager 1 probe crossed into interstellar space in 2012.",
    "Go channels synchronize goroutines without explicit locks.",
    "The Pacific Ocean covers about 30% of Earth's surface.",
    "Markdown was created by John Gruber in 2004.",
    "Python's GIL serializes bytecode execution across threads.",
    "The Great Barrier Reef is visible from low Earth orbit.",
    "Bash parameter expansion supports default values via the colon-minus operator.",
    "Docker layers are content-addressed and deduplicated across images.",
    "The speed of light in a vacuum is 299,792,458 meters per second.",
]


@pytest.mark.eval
@pytest.mark.slow
def test_longmemeval_subset_recall_at_5_sentence_transformers(tmp_path: Path) -> None:
    """R@5 >= 0.80 using sentence-transformers on a paraphrased subset."""
    embedder = SentenceTransformerProvider("all-MiniLM-L6-v2")
    store = DrawerStore(tmp_path / "eval.db", embedder)

    # Populate: relevant drawers first, then distractors.
    for _q, relevant in _RELEVANT:
        store.add(Drawer(wing="eval", room="longmemeval", content=relevant))
    for d in _DISTRACTORS:
        store.add(Drawer(wing="eval", room="longmemeval", content=d))

    hits = 0
    misses: list[str] = []
    for question, relevant in _RELEVANT:
        results = store.search(question, wing="eval", limit=5)
        contents = [drawer.content for drawer, _ in results]
        if relevant in contents:
            hits += 1
        else:
            misses.append(question)

    total = len(_RELEVANT)
    recall = hits / total
    assert recall >= 0.80, (
        f"R@5 = {recall:.2%} ({hits}/{total}) — below the 80% Phase 1 bar.\n"
        f"Misses:\n  - " + "\n  - ".join(misses)
    )
