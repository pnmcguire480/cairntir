"""Independent finite public integration controls; synthetic providers only."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import Sensitivity, WriteProvenance


SOURCE = "Original café 雪\r\n\r\n  exact original  \r\n"
EDIT = "  Correction café 🧭\r\n\r\nlast space \r\n"
PACKET = Path(__file__).resolve().parent
REPO = Path(importlib.import_module("cairntir").__file__).resolve().parents[2]


@pytest.fixture
def flow(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    outbox = vault / "cairntir-sync" / "outbox"
    outbox.mkdir(parents=True)
    db = home / "cairntir.db"
    store = DrawerStore(db, HashEmbeddingProvider(dimension=16))
    original = store.add(Drawer(wing="fixture", room="notes", content=SOURCE))
    request = dict(schema="cairntir.obsidian-correction.v1", request_id=str(uuid4()),
                   wing="fixture", source_drawer_id=original.id,
                   source_identity=store.portable_identity(original.id),
                   source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(), content=EDIT)
    proposal = outbox / f"{request['request_id']}.json"
    proposal.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    store.close()
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(
        "import cairntir.cli as cli\n"
        "from cairntir.memory.embeddings import HashEmbeddingProvider\n"
        "cli.production_embedding_provider = lambda: HashEmbeddingProvider(dimension=16)\n",
        encoding="utf-8")
    env = dict(os.environ, CAIRNTIR_HOME=str(home),
               CAIRNTIR_DISABLE_AUTOREGISTER="1", CAIRNTIR_DISABLE_UPDATE_CHECK="1",
               PYTHONUTF8="1", PYTHONPATH=os.pathsep.join([str(shim), str(REPO / "src")]))
    env.pop("CAIRNTIR_GRANT_FILE", None)
    return dict(home=home, vault=vault, db=db, request=request, proposal=proposal, env=env)


def cli(flow, command=None):
    args = command or ["obsidian-sync", str(flow["vault"]), "--wing", "fixture"]
    return subprocess.run([sys.executable, "-m", "cairntir", *args], env=flow["env"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def rows(flow):
    with sqlite3.connect(flow["db"]) as conn:
        return conn.execute("SELECT * FROM drawers ORDER BY id").fetchall()


def report(result):
    return json.loads(result.stdout)


def test_fresh_cli_exact_commit_restart_and_rejection(flow):
    original = rows(flow)[0]
    proposal = flow["proposal"].read_bytes()
    first = cli(flow)
    assert first.returncode == 0, (first.stdout, first.stderr)
    receipt = report(first)["results"][0]["receipt"]
    assert receipt["status"] == "committed" and receipt["replayed"] is False
    second = cli(flow)
    assert second.returncode == 0, (second.stdout, second.stderr)
    repeated = report(second)["results"][0]["receipt"]
    assert repeated["replayed"] is True
    assert {k: v for k, v in repeated.items() if k != "replayed"} == {
        k: v for k, v in receipt.items() if k != "replayed"}
    assert rows(flow)[0] == original and len(rows(flow)) == 2
    with DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16)) as store:
        assert store.get(receipt["correction_drawer_id"]).content == EDIT
    assert flow["proposal"].read_bytes() == proposal
    (flow["proposal"].parent / "bad.json").write_text("not-json", encoding="utf-8")
    rejected = cli(flow)
    assert rejected.returncode != 0
    assert any(row["status"] == "rejected" for row in report(rejected)["results"])
    assert len(rows(flow)) == 2


@pytest.mark.parametrize("failure", ["ack", "projection"])
def test_fresh_cli_partial_commit_retry_without_duplicates(flow, failure):
    original = rows(flow)[0]
    if failure == "ack":
        conflict = flow["vault"] / "cairntir-sync" / "acknowledgements" / (
            flow["request"]["request_id"] + ".json")
        conflict.mkdir(parents=True)
    else:
        conflict = flow["vault"] / "cairntir-sync" / "memory" / "drawer-1.md"
        conflict.parent.mkdir()
        conflict.write_bytes(b"User-owned conflicting note\r\n")
    result = cli(flow)
    assert result.returncode != 0
    data = report(result)
    row = data["results"][0]
    assert row["status"] == "committed"
    if failure == "ack":
        assert row["receipt_written"] is False and row["error"]
        conflict.rmdir()
    else:
        assert data["projection"]["status"] == "error"
        assert conflict.read_bytes() == b"User-owned conflicting note\r\n"
        conflict.unlink()
    retry = cli(flow)
    assert retry.returncode == 0, (retry.stdout, retry.stderr)
    retried = report(retry)["results"][0]
    assert retried["receipt"]["replayed"] is True
    assert retried["receipt"]["correction_drawer_id"] == row["receipt"]["correction_drawer_id"]
    assert rows(flow)[0] == original and len(rows(flow)) == 2


def test_scoped_cli_denied_before_vault_or_store_change(flow):
    from cairntir.access import issue_grant
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    token = issue_grant(store, scopes=[{"wing": "fixture", "room": "notes"}],
                        capabilities=["read", "write"])
    store.close()
    grant = flow["home"] / "grant.txt"
    grant.write_text(token, encoding="utf-8")
    flow["env"]["CAIRNTIR_GRANT_FILE"] = str(grant)
    before = rows(flow)
    proposal = flow["proposal"].read_bytes()
    denied = cli(flow)
    assert denied.returncode != 0
    assert "access denied" in denied.stdout + denied.stderr
    assert rows(flow) == before
    assert flow["proposal"].read_bytes() == proposal
    assert not (flow["vault"] / "cairntir-sync" / "workspace.json").exists()


def test_scoped_bridge_cannot_escape_authority(flow):
    from cairntir.access import AccessDenied, bind_grant, issue_grant
    bridge = importlib.import_module("cairntir.obsidian_bridge")
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    token = issue_grant(store, scopes=[{"wing": "another-wing"}], capabilities=["read"])
    scoped = bind_grant(store, token)
    before = rows(flow)
    try:
        with pytest.raises((AccessDenied, bridge.CorrectionError)):
            bridge.apply_correction(scoped, flow["request"], wing="fixture")
        assert rows(flow) == before
    finally:
        scoped.close()


def test_actual_cli_projection_privacy(flow):
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    store.add(Drawer(wing="foreign", room="notes", content="FOREIGN-MARKER"))
    store.add(Drawer(wing="fixture", room="notes", content="SECRET-MARKER"),
              provenance=WriteProvenance.create(host="fixture", capture_path="fixture",
                                                sensitivity=Sensitivity.SECRET))
    store.close()
    result = cli(flow)
    assert result.returncode == 0, (result.stdout, result.stderr)
    for path in (flow["vault"] / "cairntir-sync").rglob("*"):
        if path.is_file():
            assert b"FOREIGN-MARKER" not in path.read_bytes()
            assert b"SECRET-MARKER" not in path.read_bytes()


def test_legacy_identity_refuses_append_without_mutating_source(flow):
    with sqlite3.connect(flow["db"]) as conn:
        conn.execute("DELETE FROM store_metadata WHERE key LIKE 'embedding_%'")
        conn.commit()
    before = rows(flow)
    result = cli(flow)
    assert result.returncode != 0
    assert rows(flow) == before
    with sqlite3.connect(flow["db"]) as conn:
        assert conn.execute("SELECT value FROM store_metadata WHERE key='embedding_space_id'").fetchone() is None
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    try:
        assert store.get(1).content == SOURCE
    finally:
        store.close()


def test_previous_cli_contracts_still_available(flow):
    for command in ("obsidian-project", "vault-sync"):
        result = cli(flow, [command, "--help"])
        assert result.returncode == 0
        assert command in result.stdout


def test_outer_transaction_cannot_return_a_false_durable_commit(flow):
    bridge = importlib.import_module("cairntir.obsidian_bridge")
    from cairntir.errors import CairntirError
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    before = rows(flow)
    try:
        with store.transaction():
            with pytest.raises(CairntirError):
                bridge.apply_correction(store, flow["request"], wing="fixture")
        assert rows(flow) == before
        receipt = bridge.apply_correction(store, flow["request"], wing="fixture")
        assert receipt["replayed"] is False
        assert len(rows(flow)) == 2
    finally:
        store.close()


def test_scoped_hidden_successor_does_not_enable_stale_edit_or_leak(flow):
    bridge = importlib.import_module("cairntir.obsidian_bridge")
    from cairntir.access import AccessDenied, bind_grant, issue_grant
    store = DrawerStore(flow["db"], HashEmbeddingProvider(dimension=16))
    hidden = store.add(Drawer(wing="fixture", room="private", content="HIDDEN-SUCCESSOR",
                              supersedes_id=flow["request"]["source_drawer_id"]))
    identity = store.portable_identity(hidden.id)
    token = issue_grant(store, scopes=[{"wing": "fixture", "room": "notes"}],
                        capabilities=["read", "write"])
    scoped = bind_grant(store, token)
    before = rows(flow)
    try:
        with pytest.raises((AccessDenied, bridge.CorrectionError)) as error:
            bridge.apply_correction(scoped, flow["request"], wing="fixture")
        assert "HIDDEN-SUCCESSOR" not in str(error.value)
        assert identity not in str(error.value)
        assert rows(flow) == before
        try:
            result = bridge.sync_workspace(scoped, vault=flow["vault"], wing="fixture")
        except (AccessDenied, bridge.CorrectionError):
            result = {}
        assert "HIDDEN-SUCCESSOR" not in json.dumps(result)
        assert identity not in json.dumps(result)
        manifest = flow["vault"] / "cairntir-sync" / "workspace.json"
        if manifest.exists():
            assert "HIDDEN-SUCCESSOR" not in manifest.read_text(encoding="utf-8")
            assert identity not in manifest.read_text(encoding="utf-8")
            source = next((x for x in json.loads(manifest.read_text(encoding="utf-8"))["drawers"]
                           if x["drawer_id"] == flow["request"]["source_drawer_id"]), None)
            assert source is None or source["editable"] is False
    finally:
        scoped.close()
