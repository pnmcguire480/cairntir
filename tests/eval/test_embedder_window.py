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

from cairntir.cost import EMBEDDER_CHAR_WINDOW, EMBEDDER_TOKEN_LIMIT
from cairntir.memory.embeddings import (
    PRODUCTION_DIMENSION,
    PRODUCTION_MODEL,
    PRODUCTION_TOKEN_WINDOW,
    FastEmbedProvider,
)

LONGEST_LIVE_DRAWER_TOKENS = 2_377
"""Measured on the 413-drawer live store, 2026-08-10 (8,924 chars)."""


@pytest.mark.eval
@pytest.mark.slow
def test_declared_embedder_window_matches_the_model() -> None:
    """PRODUCTION_TOKEN_WINDOW must equal the tokenizer's configured truncation."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=PRODUCTION_MODEL)
    tokenizer = model.model.tokenizer  # type: ignore[attr-defined]
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
    """The point of the swap: no drawer is partially embedded any more."""
    assert PRODUCTION_TOKEN_WINDOW > LONGEST_LIVE_DRAWER_TOKENS * 2, (
        "the production window must clear the longest real drawer with room to "
        f"spare; longest measured is {LONGEST_LIVE_DRAWER_TOKENS} tokens"
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
