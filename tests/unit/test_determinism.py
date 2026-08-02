"""Cairntir's read path must be byte-stable, so hosts can cache it.

Practical upgrade 3 of ``plans/research-2026-08-02-trends-and-practical-upgrades.md``,
and the cheapest item on that list.

Anthropic's prompt caching reads cached tokens at **10% of normal input
cost** — a 90% discount — but **any change to a block invalidates that
block and everything after it.** Cairntir's `session_start` output was
measured as deterministic on 2026-08-02 (two consecutive calls hashing
identically), so it is not poisoning any host's cache today. Nothing in
the test suite guaranteed it would stay that way.

One assertion on a stable hash protects that discount for every user, in
every host, indefinitely. The realistic ways it breaks are a wall-clock
timestamp, a `set` iterated without sorting, or a dict whose key order
follows insertion — none of which would fail any other test here.

Note what caching does and does not fix. It makes a large payload
**cheap**; it does not make it **harmless**. Cached tokens are still read
by the model, and context rot is a function of what is in the window, not
what it cost. "We cache it, so the size is fine" answers the wrong
objection — which is why `cairntir_handoff` exists alongside this test
rather than instead of it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def backend(tmp_path: Path) -> Iterator[CairntirBackend]:
    with DrawerStore(tmp_path / "determinism.db", HashEmbeddingProvider(dimension=32)) as store:
        for i in range(6):
            store.add(
                Drawer(
                    wing="cairntir",
                    room="journey",
                    content=f"session delta {i}: what happened and why",
                    layer=Layer.ESSENTIAL,
                    metadata={"anchors": [{"path": f"src/cairntir/mod_{i}.py"}]},
                )
            )
        for i in range(3):
            store.add(
                Drawer(
                    wing="cairntir",
                    room="project-identity",
                    content=f"identity {i}: how this project works",
                    layer=Layer.IDENTITY,
                )
            )
        store.add(
            Drawer(
                wing="cairntir",
                room="predictions",
                content="an unresolved question",
                layer=Layer.ON_DEMAND,
                claim="it will hold",
                predicted_outcome="no drift at the balance pass",
            )
        )
        yield CairntirBackend(store)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_session_start_is_byte_identical_across_calls(backend: CairntirBackend) -> None:
    """Protects a 90% prompt-cache read discount for every user, in every host."""
    first = backend.session_start(wing="cairntir")
    second = backend.session_start(wing="cairntir")

    assert _digest(first) == _digest(second)


def test_handoff_is_byte_identical_across_calls(backend: CairntirBackend) -> None:
    first = backend.handoff(wing="cairntir")
    second = backend.handoff(wing="cairntir")

    assert _digest(first) == _digest(second)


def test_handoff_is_stable_across_repeated_calls_not_just_two(
    backend: CairntirBackend,
) -> None:
    """`get` bumps access_count and last_accessed_at.

    If either ever leaked into a response, the second call would differ
    from the first and a third from the second. Five calls is cheap
    insurance against a drift that only appears after warm-up.
    """
    digests = {_digest(backend.handoff(wing="cairntir")) for _ in range(5)}

    assert len(digests) == 1


def test_handoff_with_files_is_deterministic(backend: CairntirBackend) -> None:
    """Anchor matching walks metadata; set iteration order must not leak out."""
    files = ["src/cairntir/mod_2.py", "src/cairntir/mod_4.py"]

    first = backend.handoff(wing="cairntir", files=files)
    second = backend.handoff(wing="cairntir", files=files)

    assert _digest(first) == _digest(second)


def test_determinism_is_within_a_store_never_across_two(tmp_path: Path) -> None:
    """The brief is deliberately **not** a pure function of drawer content.

    Two stores holding identical text still brief differently, because
    every drawer carries an immutable write receipt — host, model,
    session, trust — and `session_id` is unique per writing session. That
    is the poisoned-memory boundary doing its job, and dropping it to
    make output content-addressable would trade a security property for
    an aesthetic one.

    Prompt caching only ever needs stability **within** one store across
    consecutive calls, which the tests above cover. This test pins the
    boundary so nobody later "fixes" the difference.
    """

    def build(name: str) -> str:
        with DrawerStore(tmp_path / name, HashEmbeddingProvider(dimension=32)) as store:
            for i in range(4):
                store.add(
                    Drawer(
                        wing="cairntir",
                        room="journey",
                        content=f"delta {i}",
                        layer=Layer.ESSENTIAL,
                    )
                )
            return CairntirBackend(store).handoff(wing="cairntir")

    first, second = build("a.db"), build("b.db")

    assert _digest(first) != _digest(second)
    assert "delta 3" in first and "delta 3" in second, "the content itself must match"
    assert '"session_id"' in first, "provenance is what makes the two differ"
