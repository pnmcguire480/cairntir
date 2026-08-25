"""The declared embedder window must match the model's real tokenizer.

This is the guard that would have caught the defect found 2026-08-10.
``cost.py`` hardcoded a 512-token window; ``all-MiniLM-L6-v2`` actually
truncated at **128**; and fastembed's own ``model_description`` claimed
256. Three numbers, no two of which agreed, and the one the tool
reported was the most flattering. 73.4% of the live corpus was invisible
to semantic recall while a purpose-built cost report said the window was
four times larger than it was.

The lesson encoded here: **read the tokenizer, never the description.**
Marked ``eval`` because it loads the real model, so it runs in the same
CI job that already downloads models for the LongMemEval gate.
"""

from __future__ import annotations

import pytest

from cairntir.config import db_path
from cairntir.cost import EMBEDDER_CHAR_WINDOW, EMBEDDER_TOKEN_LIMIT
from cairntir.memory.embeddings import (
    PRODUCTION_DIMENSION,
    PRODUCTION_MODEL,
    PRODUCTION_TOKEN_WINDOW,
    FastEmbedProvider,
)
from cairntir.memory.store import DrawerStore

LONGEST_LIVE_DRAWER_TOKENS = 2_377
"""Longest drawer on the 413-drawer live store, 2026-08-10 (8,924 chars).

Kept only as the *floor* the corpus was known to reach. It is no longer the
thing asserted against: a reviewer running a 3,586-drawer store on
2026-08-11 measured a real longest drawer of 6,414 tokens, so this literal
understated the true figure by 2.7x while the test that used it stayed
green — because it compared this constant to another constant and never
opened a store at all.
"""

REQUIRED_HEADROOM = 1.2
"""Multiple of the longest real drawer the window must clear.

Was an implicit 2x asserted against a stale literal. 2x is not achievable
at 8,192 tokens once a corpus contains a 6,414-token drawer, and pretending
otherwise is how the old assertion passed while being false.
"""


@pytest.mark.eval
@pytest.mark.slow
def test_declared_embedder_window_matches_the_model() -> None:
    """PRODUCTION_TOKEN_WINDOW must equal the tokenizer's configured truncation."""
    provider = FastEmbedProvider()
    provider.dimension  # noqa: B018 — force the production model/cache path
    tokenizer = provider._model.model.tokenizer  # type: ignore[union-attr]
    assert tokenizer is not None, "cannot verify a window without a tokenizer"

    configured = tokenizer.truncation["max_length"]
    assert configured == PRODUCTION_TOKEN_WINDOW, (
        f"{PRODUCTION_MODEL} truncates at {configured} tokens but Cairntir declares "
        f"{PRODUCTION_TOKEN_WINDOW}. Every drawer longer than the real limit is "
        "partially invisible to semantic recall, and `cairntir cost` is lying about "
        "how much. Fix PRODUCTION_TOKEN_WINDOW; do not relax this test."
    )
    assert EMBEDDER_TOKEN_LIMIT == PRODUCTION_TOKEN_WINDOW
    assert EMBEDDER_CHAR_WINDOW == PRODUCTION_TOKEN_WINDOW * 4


@pytest.mark.eval
@pytest.mark.slow
def test_the_window_covers_the_whole_live_corpus() -> None:
    """The point of the swap: no drawer is partially embedded any more.

    Measures the store under test with the real tokenizer. The previous
    version of this test asserted ``PRODUCTION_TOKEN_WINDOW >
    LONGEST_LIVE_DRAWER_TOKENS * 2`` — two module constants, ``8192 > 4754``
    — so it opened no store, loaded no model, and could not fail for any
    reason other than someone editing a literal. It carried ``eval`` and
    ``slow`` markers for work it never did, and it stayed green on a corpus
    where the property it named was already false. A guard whose ground
    truth is a snapshot is not a guard.
    """
    store_path = db_path()
    if not store_path.exists():
        pytest.skip(f"no live store at {store_path}")

    provider = FastEmbedProvider()
    provider.dimension  # noqa: B018 — force the model load so the tokenizer exists
    tokenizer = provider._model.model.tokenizer  # type: ignore[union-attr]

    with DrawerStore(store_path, provider) as store:
        drawers = store.list_by(limit=100_000, include_expired=True)
    if not drawers:
        pytest.skip("live store is empty")

    longest = max(drawers, key=lambda d: len(d.content))
    longest_tokens = len(tokenizer.encode(longest.content).ids)

    assert longest_tokens >= 1, "tokenizer returned nothing for the longest drawer"
    assert longest_tokens * REQUIRED_HEADROOM <= PRODUCTION_TOKEN_WINDOW, (
        f"drawer #{longest.id} is {longest_tokens:,} tokens and the production "
        f"window is {PRODUCTION_TOKEN_WINDOW:,}, leaving only "
        f"{PRODUCTION_TOKEN_WINDOW / longest_tokens:.2f}x headroom (need "
        f"{REQUIRED_HEADROOM}x). Drawers are outgrowing the embedder: either "
        "split the longest ones or move to a wider model. Do not relax this "
        "test — it is measured, not assumed."
    )
    assert longest_tokens >= LONGEST_LIVE_DRAWER_TOKENS or len(drawers) < 413, (
        f"the longest drawer measured {longest_tokens:,} tokens, below the "
        f"{LONGEST_LIVE_DRAWER_TOKENS:,} recorded on 2026-08-10 for a corpus "
        "at least this size — the recorded floor is stale or the store shrank; "
        "reconcile it rather than editing the number."
    )


@pytest.mark.eval
@pytest.mark.slow
def test_the_tail_of_a_long_document_changes_its_vector() -> None:
    """The empirical form of the bug, as a regression test.

    Under MiniLM this produced cosine 1.0000000000 — appending a whole
    sentence to a 2,880-char document left the vector byte-identical.
    A vector that ignores its own document's tail cannot retrieve it.
    """
    provider = FastEmbedProvider()
    body = "The project uses a sqlite database for storage. " * 60
    tail = " The commissioning authority is Wing Commander Fluorescent Wombat."

    plain, marked = provider.embed([body, body + tail])
    assert len(plain) == PRODUCTION_DIMENSION

    def cosine(a: list[float], b: list[float]) -> float:
        norm = sum(x * x for x in a) ** 0.5 * sum(y * y for y in b) ** 0.5
        return sum(x * y for x, y in zip(a, b, strict=True)) / norm

    assert cosine(plain, marked) < 0.9999, (
        "appending a sentence left the vector unchanged — the embedder is "
        "truncating before the tail, which is the 2026-08-10 defect returning"
    )

    query = provider.embed(["who is the commissioning authority"])[0]
    assert cosine(query, marked) > cosine(query, plain), (
        "a fact in the tail must make the document more retrievable, not less"
    )
