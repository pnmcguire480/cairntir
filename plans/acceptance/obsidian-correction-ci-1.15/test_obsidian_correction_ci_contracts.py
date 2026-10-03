"""Frozen CI seam controls: typed errors, live grants and exact request boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_recovery_outcomes import contents

from cairntir import obsidian_bridge
from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant
from cairntir.errors import MemoryStoreError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

_ROOT = Path(__file__).resolve().parents[2]
_PACKET = _ROOT / "plans" / "acceptance" / "obsidian-correction-ci-1.15"
_FREEZE = json.loads((_PACKET / "FREEZE.json").read_text(encoding="utf-8"))
for _relative, _expected in _FREEZE["files_sha256"].items():
    _path = _ROOT / _relative
    if hashlib.sha256(_path.read_bytes()).hexdigest() != _expected:
        raise pytest.UsageError(
            f"independent correction CI acceptance custody changed: {_relative}"
        )


@pytest.fixture
def correction_case(tmp_path: Path):
    database = tmp_path / "source.db"
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    store = DrawerStore(database, HashEmbeddingProvider(dimension=16))
    source = store.add(Drawer(wing="fixture", room="notes", content="Exact source café\r\n"))
    request = {
        "schema": "cairntir.obsidian-correction.v1",
        "request_id": str(uuid4()),
        "wing": "fixture",
        "source_drawer_id": source.id,
        "source_identity": store.portable_identity(source.id),
        "source_sha256": hashlib.sha256(source.content.encode("utf-8")).hexdigest(),
        "content": "Exact correction 雪\r\n",
    }
    try:
        yield database, vault, store, request
    finally:
        store.close()


def _vault_state(vault: Path):
    return {
        path.relative_to(vault).as_posix(): path.read_bytes() if path.is_file() else None
        for path in vault.rglob("*")
    }


def _operation(store, request, vault, operation):
    if operation == "state":
        return store.transaction_active
    if operation == "apply":
        return obsidian_bridge.apply_correction(store, request, wing="fixture")
    return obsidian_bridge.sync_workspace(store, vault=vault, wing="fixture")


@pytest.mark.parametrize("operation", ["state", "apply", "sync"])
def test_closed_store_transaction_state_is_typed_without_writes(correction_case, operation):
    database, vault, store, request = correction_case
    before = contents(database)
    files = _vault_state(vault)
    store.close()
    with pytest.raises(MemoryStoreError, match="cannot inspect transaction state"):
        _operation(store, request, vault, operation)
    assert contents(database) == before
    assert _vault_state(vault) == files


@pytest.mark.parametrize("operation", ["state", "apply", "sync"])
@pytest.mark.parametrize("grant_state", ["revoked", "write-only"])
def test_scoped_transaction_state_requires_a_live_read_grant(
    correction_case, operation, grant_state
):
    database, vault, store, request = correction_case
    capabilities = ["write"] if grant_state == "write-only" else ["read", "write"]
    token = issue_grant(
        store, scopes=[{"wing": "fixture", "rooms": ["notes"]}], capabilities=capabilities
    )
    scoped = bind_grant(store, token)
    if grant_state == "revoked":
        assert scoped.transaction_active is False
        revoke_grant(store, token)
    before = contents(database)
    files = _vault_state(vault)
    with pytest.raises(AccessDenied, match="access denied"):
        _operation(scoped, request, vault, operation)
    assert contents(database) == before
    assert _vault_state(vault) == files


@pytest.mark.parametrize(
    "invalid",
    [
        "extra-field",
        "missing-field",
        "not-object",
        "request-uuid-type",
        "identity-uuid-type",
        "request-uuid-noncanonical",
        "identity-uuid-noncanonical",
        "surrogate-text",
        "source-id-overflow",
        "digest-type",
        "digest-uppercase",
        "wing-invalid",
    ],
)
def test_exact_request_schema_uuid_utf8_and_identity_boundaries(correction_case, invalid):
    database, vault, store, request = correction_case
    request = dict(request)
    wing = "fixture"
    if invalid == "extra-field":
        request["unexpected"] = "must not be accepted"
    elif invalid == "missing-field":
        del request["schema"]
    elif invalid == "not-object":
        request = [request]
    elif invalid == "request-uuid-type":
        request["request_id"] = 123
    elif invalid == "identity-uuid-type":
        request["source_identity"] = None
    elif invalid == "request-uuid-noncanonical":
        request["request_id"] = "{" + request["request_id"] + "}"
    elif invalid == "identity-uuid-noncanonical":
        request["source_identity"] = "{" + request["source_identity"] + "}"
    elif invalid == "surrogate-text":
        request["content"] = "Invalid UTF-8 scalar \ud800"
    elif invalid == "source-id-overflow":
        request["source_drawer_id"] = 2**63
    elif invalid == "digest-type":
        request["source_sha256"] = 123
    elif invalid == "digest-uppercase":
        request["source_sha256"] = "A" * 64
    else:
        request["wing"] = wing = "invalid wing"
    before = contents(database)
    files = _vault_state(vault)
    with pytest.raises(obsidian_bridge.CorrectionError):
        obsidian_bridge.apply_correction(store, request, wing=wing)
    assert contents(database) == before
    assert _vault_state(vault) == files
