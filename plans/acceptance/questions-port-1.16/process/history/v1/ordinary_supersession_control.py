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
    for name, module in tuple(sys.modules.items()):
        if name.startswith("frozen_questions_") and hasattr(module, "list_questions"):
            monkeypatch.setattr(module, "list_questions", wrong_register)
