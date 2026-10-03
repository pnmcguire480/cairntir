"""Replay the historical typed-question closure wrong control in one process."""

import sys

import pytest

from cairntir import questions


@pytest.fixture(autouse=True)
def close_typed_question_on_ordinary_supersession(monkeypatch):
    original = questions.list_questions

    def wrong_register(store, *, wing, include_resolved=False):
        register = original(store, wing=wing, include_resolved=include_resolved)
        rows, _ = store.context_candidates(wing=wing)
        superseded = {drawer.supersedes_id for drawer, _ in rows}
        return {
            **register,
            "questions": [
                entry for entry in register["questions"] if entry["drawer_id"] not in superseded
            ],
        }

    monkeypatch.setattr(questions, "list_questions", wrong_register)
    # The unchanged historical tests retain the direct imported API reference.
    patched = set()
    for module in tuple(sys.modules.values()):
        for target in (module, getattr(module, "_core", None)):
            if (
                target is not None
                and target.__name__.startswith("frozen_questions_")
                and hasattr(target, "list_questions")
                and id(target) not in patched
            ):
                monkeypatch.setattr(target, "list_questions", wrong_register)
                patched.add(id(target))
    assert patched, "wrong control did not reach the unchanged historical imported API"
