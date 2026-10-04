"""Inert pytest plugin detecting a disabled ambient-transaction guard."""

from __future__ import annotations

from unittest.mock import patch


def pytest_collection_modifyitems(items):
    """Patch only invocation-time durability visibility, preserving the original assertions."""
    from cairntir.memory.store import DrawerStore

    patched = set()
    for item in items:
        if item.originalname != "test_caller_transaction_cannot_issue_managed_durable_receipts":
            continue
        namespace = item.obj.__globals__
        identity = id(namespace)
        if identity in patched:
            continue
        patched.add(identity)
        original = namespace["operation"]

        def mutated_operation(*args, _original=original, **kwargs):
            store, invoke = _original(*args, **kwargs)

            def masked_invocation():
                with patch.object(DrawerStore, "transaction_active", property(lambda _: False)):
                    return invoke()

            return store, masked_invocation

        namespace["operation"] = mutated_operation
