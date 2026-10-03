"""Inert process-only wrong control for premature durable acknowledgement."""

import pytest

from cairntir import questions
from cairntir.memory.store import DrawerStore


@pytest.fixture(autouse=True)
def conceal_caller_transaction(monkeypatch):
    for name in ("open_question", "resolve_question"):
        original = getattr(questions, name)

        def bypass(*args, _original=original, **kwargs):
            with monkeypatch.context() as fault:
                fault.setattr(DrawerStore, "transaction_active", property(lambda _self: False))
                return _original(*args, **kwargs)

        monkeypatch.setattr(questions, name, bypass)
