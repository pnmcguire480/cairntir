"""Portable synthetic I03 controls; independent review required before execution."""

from __future__ import annotations

import copy
import http.client
import importlib
import shutil
import socket
import sqlite3
import threading
import time
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from . import i03_support as support

HERE = Path(__file__).resolve().parent


def api():
    return importlib.import_module("cairntir.ideation_channels")


class Provider:
    def __init__(self, output=None, action=None, raw=None):
        self.output = copy.deepcopy(
            output
            if output is not None
            else support.load((HERE / "fixtures/valid-output.json").read_bytes())
        )
        self.action, self.raw = action, raw
        self.prepares = self.calls = 0
        self.inputs = self.requests = None
        self._identity = MappingProxyType(
            {
                "kind": "fixture",
                "model_id": "i03-fixture",
                "prompt_version": "i03.v1",
                "endpoint": None,
                "timeout_seconds": None,
            }
        )

    @property
    def identity(self):
        return self._identity

    def prepare(self, input_bytes, output_schema):
        self.prepares += 1
        self.inputs = support.load(input_bytes)
        support.schema_check(self.output, output_schema)
        self.requests = support.canonical(
            {
                "model": self.identity["model_id"],
                "stream": False,
                "prompt": support.PREFIX + input_bytes.decode("utf-8"),
                "format": output_schema,
                "options": {"num_predict": 3072, "num_ctx": 8192, "temperature": 0},
            }
        )
        return self.requests

    def generate(self, request_bytes, *, cancel=None):
        self.calls += 1
        assert request_bytes == self.requests
        if self.action:
            self.action()
        return (
            self.raw
            if self.raw is not None
            else support.canonical(
                {
                    "model": self.identity["model_id"],
                    "done": True,
                    "done_reason": "stop",
                    "response": support.canonical(self.output).decode("utf-8"),
                    "total_duration": 0,
                    "eval_count": 0,
                }
            )
        )


@pytest.fixture
def case(tmp_path):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore

    root = tmp_path / "sources"
    shutil.copytree(HERE / "fixtures/sources", root)
    db = tmp_path / "isolated.db"
    store = DrawerStore(db, HashEmbeddingProvider(dimension=32))
    value = SimpleNamespace(
        root=root,
        db=db,
        store=store,
        tmp=tmp_path,
        selection=support.load((HERE / "fixtures/selection.json").read_bytes()),
        profiles=support.load((HERE / "fixtures/profiles.json").read_bytes()),
    )
    yield value
    store.close()


def generate(c, key, provider=None, **changes):
    provider = provider if provider is not None else Provider()
    arguments = {
        "wing": "i03-fixture",
        "selection": c.selection,
        "profiles": c.profiles,
        "source_root": c.root,
        "idempotency_key": key,
        "adapter": provider,
    }
    store = changes.pop("store", c.store)
    arguments.update(changes)
    return api().generate_channel_set(store, **arguments)


def error(code, action):
    with pytest.raises(api().ChannelError) as caught:
        action()
    assert caught.value.code in ({code} if isinstance(code, str) else set(code))
    return caught.value


def results(c):
    return [
        d
        for d in c.store.list_by(wing="i03-fixture", room="ideation-channels", limit=None)
        if support.load(d.content).get("schema") == "cairntir.channel-result.v1"
    ]


def state(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT id,content,metadata,last_accessed_at,access_count FROM drawers ORDER BY id"
        ).fetchall()


def test_u01_hash_anchor_excerpt_and_provisional_selection(case):
    c = case
    provider = Provider()
    receipt = generate(c, "origin-valid", provider)
    graph = support.graph_check(c.store, receipt)
    assert graph["origin"]["selection"] == c.selection
    for source in c.selection["sources"]:
        data = (c.root / source["path"]).read_bytes()
        assert support.sha(data) == source["sha256"]
        assert source["excerpt"] in data.decode("utf-8")
        assert support.sha(source["excerpt"].encode("utf-8")) == source["excerpt_sha256"]
    wrong = []
    for field, value in (
        ("kind", "i02"),
        ("human_confirmation", True),
        ("selected_text", "a different selection"),
    ):
        item = copy.deepcopy(c.selection)
        item[field] = value
        wrong.append((item, "UNSUPPORTED_SELECTION" if field == "kind" else "INVALID_INPUT"))
    for field, value in (
        ("sha256", "0" * 64),
        ("path", "../outside.md"),
        ("anchor", "## Missing section"),
        ("excerpt_sha256", "0" * 64),
    ):
        item = copy.deepcopy(c.selection)
        item["sources"][0][field] = value
        wrong.append((item, "INVALID_INPUT"))
    for index, (selection, code) in enumerate(wrong):
        provider = Provider()
        error(
            code,
            lambda index=index, provider=provider, selection=selection: generate(
                c, f"origin-bad-{index}", provider, selection=selection
            ),
        )
        assert provider.prepares == provider.calls == 0
    source = c.root / c.selection["sources"][0]["path"]
    original = source.read_bytes()
    source.unlink()
    provider = Provider()
    error("INVALID_INPUT", lambda: generate(c, "origin-missing", provider))
    assert provider.prepares == provider.calls == 0
    source.write_bytes(original)
    assert len(results(c)) == 1


def test_u02_declared_profiles_are_complete_exact_and_bounded(case):
    c = case
    mutations = []
    for change in ("duplicate", "unknown", "revision", "missing", "zero", "widen"):
        profiles = copy.deepcopy(c.profiles)
        if change == "duplicate":
            profiles[1] = copy.deepcopy(profiles[0])
        elif change == "unknown":
            profiles[0]["platform_claim"] = "live specification"
        elif change == "revision":
            profiles[0]["revision"] = 2
        elif change == "missing":
            del profiles[0]["limits"]["body"]
        elif change == "zero":
            profiles[0]["limits"]["hook"] = 0
        else:
            profiles[0]["limits"]["hook"] += 1
        mutations.append(profiles)
    for index, profiles in enumerate(mutations):
        provider = Provider()
        error(
            "INVALID_INPUT",
            lambda index=index, provider=provider, profiles=profiles: generate(
                c, f"profile-bad-{index}", provider, profiles=profiles
            ),
        )
        assert provider.prepares == provider.calls == 0
    narrow = copy.deepcopy(c.profiles)
    narrow[0]["limits"]["hook"] = 100
    receipt = generate(c, "profile-narrow", profiles=narrow)
    assert receipt["profiles_sha256"] == support.sha(support.canonical(narrow))
    assert len(results(c)) == 1


def test_u03_one_whole_exchange_persists_raw_and_enriched_meaning(case):
    c = case
    provider = Provider(
        action=lambda: (
            not c.store.transaction_active or pytest.fail("model called inside store transaction")
        )
    )
    receipt = generate(c, "whole", provider)
    assert provider.prepares == provider.calls == 1
    assert provider.inputs["selection"] == c.selection and provider.inputs["profiles"] == c.profiles
    assert receipt["status"] == "committed_draft" and receipt["replayed"] is False
    assert receipt["currentness"] == "current" and receipt["projection_status"] == "not_requested"
    graph = support.graph_check(c.store, receipt)
    assert graph["wire"] == provider.output
    assert receipt["generation_provenance"]["kind"] == "fixture_unverified"
    assert len(receipt["adaptations"]) == 3 and all(
        item["origin_ref"] == receipt["origin_ref"] for item in receipt["adaptations"]
    )
    assert all(item["uncertainty_notice"] == support.NOTICE for item in receipt["adaptations"])
    assert all(
        "uncertainty_notice" not in item and "origin_ref" not in item
        for item in graph["wire"]["adaptations"]
    )


def test_u04_mechanical_bad_outputs_never_partially_commit(case):
    c = case
    defects = []
    for kind in ("source", "format", "missing", "duplicate", "bytes", "extra", "assumption"):
        output = copy.deepcopy(Provider().output)
        if kind == "source":
            output["adaptations"][0]["source_ids"] = ["unselected-source"]
        elif kind == "format":
            output["adaptations"][0]["format_id"] = "short-note"
        elif kind == "missing":
            output["adaptations"].pop()
        elif kind == "duplicate":
            output["adaptations"][1]["hook"] = output["adaptations"][0]["hook"]
        elif kind == "bytes":
            output["adaptations"][1]["content"]["subject"] = "\U0001f680" * 31
        elif kind == "extra":
            output["adaptations"][0]["uncertainty_notice"] = "model-selected notice"
        else:
            output["adaptations"][0]["assumption_ids"] = ["missing-assumption"]
        defects.append((kind, output))
    for kind, output in defects:
        provider = Provider(output)
        provider.prepare = lambda input_bytes, schema, p=provider: raw_prepare(
            p, input_bytes, schema
        )
        error(
            "CONSTRAINT_VIOLATION"
            if kind in {"bytes", "duplicate"}
            else {"INVALID_RESPONSE", "CONSTRAINT_VIOLATION"},
            lambda kind=kind, provider=provider: generate(c, f"output-{kind}", provider),
        )
        assert provider.prepares == provider.calls == 1
    for index, raw in enumerate(
        (
            b'{"model":"i03-fixture","done":true,"done_reason":"stop","response":"{}","done":false}',
            support.canonical(
                {
                    "model": "different-model",
                    "done": True,
                    "done_reason": "stop",
                    "response": support.canonical(Provider().output).decode(),
                }
            ),
        )
    ):
        provider = Provider(raw=raw)
        error(
            "INVALID_RESPONSE",
            lambda index=index, provider=provider: generate(c, f"envelope-{index}", provider),
        )
        assert provider.calls == 1
    assert not results(c)


def raw_prepare(provider, input_bytes, schema):
    provider.prepares += 1
    provider.inputs = support.load(input_bytes)
    provider.requests = support.canonical(
        {
            "model": provider.identity["model_id"],
            "stream": False,
            "prompt": support.PREFIX + input_bytes.decode(),
            "format": schema,
            "options": {"num_predict": 3072, "num_ctx": 8192, "temperature": 0},
        }
    )
    return provider.requests


def test_u05_full_readonly_reopen_and_corrupt_origin_refusal(case):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore

    c = case
    receipt = generate(c, "durable")
    before = state(c.db)
    with DrawerStore(c.db, HashEmbeddingProvider(dimension=32), read_only=True) as readonly:
        opened = api().get_channel_set(
            readonly, receipt["ref"], source_root=c.root, current_profiles=c.profiles
        )
        assert (
            opened["adaptations"] == receipt["adaptations"]
            and opened["assumptions"] == receipt["assumptions"]
        )
        assert opened["generation_provenance"] == receipt["generation_provenance"]
        support.graph_check(readonly, opened)
    assert state(c.db) == before
    for field, value in (
        ("portable_identity", "00000000-0000-0000-0000-000000000000"),
        ("content_sha256", "0" * 64),
        ("wing", "foreign-wing"),
    ):
        ref = dict(receipt["ref"], **{field: value})
        error("CORRUPT_ARTIFACT", lambda ref=ref: api().get_channel_set(c.store, ref))
    with sqlite3.connect(c.db) as conn:
        conn.execute(
            "UPDATE drawers SET content=? WHERE id=?", ("{}", receipt["origin_ref"]["drawer_id"])
        )
    damaged = state(c.db)
    error("CORRUPT_ARTIFACT", lambda: api().get_channel_set(c.store, receipt["ref"]))
    assert state(c.db) == damaged


def test_u06_replay_conflict_discarded_ack_and_prepared_never_redispatch(case):
    c = case
    first = generate(c, "ack-discarded")
    before = state(c.db)
    again = Provider()
    replay = generate(c, "ack-discarded", again)
    assert replay["replayed"] is True and replay["ref"] == first["ref"]
    assert again.prepares == again.calls == 0 and state(c.db) == before
    changed = copy.deepcopy(c.selection)
    changed["selection_reason"] += " Changed decision."
    error("CONFLICT", lambda: generate(c, "ack-discarded", again, selection=changed))
    assert again.prepares == again.calls == 0
    abandoned = Provider(action=lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        generate(c, "abandoned-dispatch", abandoned)
    assert abandoned.prepares == abandoned.calls == 1
    fresh = Provider()
    error("INDETERMINATE", lambda: generate(c, "abandoned-dispatch", fresh))
    assert fresh.prepares == fresh.calls == 0
    failed = Provider(action=lambda: (_ for _ in ()).throw(TimeoutError("fixture timeout")))
    error("PROVIDER_UNAVAILABLE", lambda: generate(c, "terminal-failure", failed))
    retry = Provider()
    error("PROVIDER_UNAVAILABLE", lambda: generate(c, "terminal-failure", retry))
    assert retry.prepares == retry.calls == 0 and len(results(c)) == 1


def test_u07_live_public_capabilities_and_readonly_export(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore

    c = case
    scope = [{"wing": "i03-fixture", "rooms": ["ideation-channels"]}]
    receipt = generate(c, "authority")
    for capabilities in (["read"], ["write"], ["read", "export"]):
        token = issue_grant(c.store, scopes=scope, capabilities=capabilities)
        limited = bind_grant(c.store, token)
        provider = Provider()
        with pytest.raises(AccessDenied):
            generate(c, "missing-" + "-".join(capabilities), provider, store=limited)
        assert provider.prepares == provider.calls == 0
    token = issue_grant(c.store, scopes=scope, capabilities=["read", "write"])
    provider = Provider()
    with pytest.raises(AccessDenied):
        generate(c, "foreign-wing", provider, store=bind_grant(c.store, token), wing="foreign-wing")
    assert provider.prepares == provider.calls == 0
    hidden = issue_grant(
        c.store,
        scopes=[{"wing": "i03-fixture", "drawer_ids": [receipt["ref"]["drawer_id"]]}],
        capabilities=["read"],
    )
    with pytest.raises(AccessDenied) as denied:
        api().get_channel_set(bind_grant(c.store, hidden), receipt["ref"])
    assert c.selection["title"] not in str(denied.value)
    read_token = issue_grant(c.store, scopes=scope, capabilities=["read"])
    export_token = issue_grant(c.store, scopes=scope, capabilities=["read", "export"])
    before = state(c.db)
    vault = c.tmp / "explicit-export-vault"
    vault.mkdir()
    with DrawerStore(c.db, HashEmbeddingProvider(dimension=32), read_only=True) as readonly:
        reader = bind_grant(readonly, read_token)
        opened = api().get_channel_set(reader, receipt["ref"])
        assert (
            opened["adaptations"] == receipt["adaptations"]
            and opened["currentness"] == "unverified"
        )
        with pytest.raises(AccessDenied):
            api().project_channel_set(reader, receipt["ref"], vault_path=vault)
        assert not list(vault.rglob("*"))
        exported = api().project_channel_set(
            bind_grant(readonly, export_token),
            receipt["ref"],
            vault_path=vault,
            source_root=c.root,
            current_profiles=c.profiles,
        )
        graph = support.graph_check(readonly, opened)
        support.vault_check(exported, graph, vault)
    assert state(c.db) == before and len(results(c)) == 1


def test_u08_source_and_live_grant_changes_cannot_commit(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant

    c = case
    source = c.root / c.selection["sources"][0]["path"]
    original = source.read_bytes()
    provider = Provider(
        action=lambda: source.write_bytes(original + b"\r\nChanged during generation.\r\n")
    )
    error("CONFLICT", lambda: generate(c, "source-race", provider))
    assert provider.calls == 1 and not results(c)
    source.write_bytes(original)
    token = issue_grant(
        c.store,
        scopes=[{"wing": "i03-fixture", "rooms": ["ideation-channels"]}],
        capabilities=["read", "write", "export"],
    )
    provider = Provider(action=lambda: revoke_grant(c.store, token))
    with pytest.raises(AccessDenied):
        generate(c, "grant-race", provider, store=bind_grant(c.store, token))
    assert provider.calls == 1 and not results(c)


def test_u09_currentness_real_origin_links_human_bytes_and_conflicts(case):
    c = case
    receipt = generate(c, "vault")
    graph = support.graph_check(c.store, receipt)
    assert api().get_channel_set(c.store, receipt["ref"])["currentness"] == "unverified"
    assert (
        api().get_channel_set(
            c.store, receipt["ref"], source_root=c.tmp / "absent", current_profiles=c.profiles
        )["currentness"]
        == "unverified"
    )
    future = copy.deepcopy(c.profiles)
    future[0]["revision"] = 2
    assert (
        api().get_channel_set(c.store, receipt["ref"], source_root=c.root, current_profiles=future)[
            "currentness"
        ]
        == "historical"
    )
    vault = c.tmp / "vault"
    vault.mkdir()
    projected = api().project_channel_set(
        c.store, receipt["ref"], vault_path=vault, source_root=c.root, current_profiles=c.profiles
    )
    original_notes = support.vault_check(projected, graph, vault)
    current = Path(projected["projection"]["current_note"])
    human_prefix, human_suffix = b"Human preface \xe2\x98\x98\r\n", b"\r\nHuman footer stays.\r\n"
    current.write_bytes(human_prefix + current.read_bytes() + human_suffix)
    stale = api().project_channel_set(
        c.store, receipt["ref"], vault_path=vault, source_root=c.root, current_profiles=future
    )
    assert stale["projection_status"] == "ready" and stale["currentness"] == "historical"
    assert current.read_bytes().startswith(human_prefix) and current.read_bytes().endswith(
        human_suffix
    )
    assert b"historical" in current.read_bytes()
    assert (
        Path(projected["projection"]["selection_note"]).read_bytes()
        == original_notes["selection_note"]
    )
    assert (
        Path(projected["projection"]["version_note"]).read_bytes() == original_notes["version_note"]
    )
    version = Path(projected["projection"]["version_note"])
    version.write_bytes(version.read_bytes() + b"Human changed immutable generated bytes.")
    damaged = version.read_bytes()
    conflict = api().project_channel_set(c.store, receipt["ref"], vault_path=vault)
    assert conflict["projection_status"] == "conflict" and conflict["projection_error"]
    assert version.read_bytes() == damaged
    untouched = {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    reopened = api().get_channel_set(c.store, receipt["ref"])
    assert reopened["adaptations"] == receipt["adaptations"]
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == untouched
    unowned = c.tmp / "unowned-vault"
    target = unowned / "cairntir-sync/i03-fixture/channels/current.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"Human-owned file with no markers.\r\n")
    conflict = api().project_channel_set(c.store, receipt["ref"], vault_path=unowned)
    assert (
        conflict["projection_status"] == "conflict"
        and target.read_bytes() == b"Human-owned file with no markers.\r\n"
    )
    source = c.root / c.selection["sources"][0]["path"]
    source.write_bytes(source.read_bytes() + b"\r\nNew historical source revision.\r\n")
    historical = api().get_channel_set(
        c.store, receipt["ref"], source_root=c.root, current_profiles=c.profiles
    )
    assert (
        historical["currentness"] == "historical"
        and historical["adaptations"] == receipt["adaptations"]
    )


def test_u10_bounded_local_transport_failures_and_cooperative_cancel(case, monkeypatch):
    c = case
    stop = threading.Event()
    stop.set()
    provider = Provider()
    error("CANCELLED", lambda: generate(c, "pre-cancel", provider, cancel=stop))
    assert provider.calls == 0
    stop.clear()
    provider = Provider(action=stop.set)
    error("CANCELLED", lambda: generate(c, "post-cancel", provider, cancel=stop))
    assert provider.calls == 1 and not results(c)
    malformed = Provider(raw=b"not JSON")
    error("INVALID_RESPONSE", lambda: generate(c, "malformed", malformed))
    unavailable = Provider(action=lambda: (_ for _ in ()).throw(OSError("unavailable fixture")))
    error("PROVIDER_UNAVAILABLE", lambda: generate(c, "unavailable", unavailable))
    calls = []
    raw = support.canonical(
        {
            "model": "local-fixture",
            "done": True,
            "done_reason": "stop",
            "response": support.canonical(Provider().output).decode(),
            "eval_count": 0,
            "total_duration": 0,
        }
    )
    transport = {"status": 200, "raw": raw, "dribble": False}

    class Socket:
        def settimeout(self, value):
            assert value > 0

    class Response:
        def __init__(self):
            self.status = transport["status"]
            self.data = transport["raw"]
            self.offset = 0

        def read1(self, amount=65536):
            if transport["dribble"]:
                time.sleep(0.015)
                amount = min(amount, max(1, len(self.data) // 5))
            part = self.data[self.offset : self.offset + amount]
            self.offset += len(part)
            return part

        read = read1

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    class Connection:
        def __init__(self, host, port, timeout=None, **kwargs):
            self.host, self.port, self.timeout = host, port, timeout
            self.sock = Socket()
            self.closed = False

        def connect(self):
            self.sock = Socket()

        def request(self, method, path, body=None, headers=None, **kwargs):
            self.sock = Socket()
            assert (self.host, self.port) == ("127.0.0.1", 11434)
            assert (method, path) == ("POST", "/api/generate")
            assert headers["Content-Type"] == "application/json"
            request = support.load(body)
            assert request["stream"] is False and request["options"] == {
                "num_predict": 3072,
                "num_ctx": 8192,
                "temperature": 0,
            }
            calls.append(body)

        def getresponse(self):
            return Response()

        def close(self):
            self.closed = True

    for name in ("connect", "request", "getresponse", "close"):
        monkeypatch.setattr(http.client.HTTPConnection, name, getattr(Connection, name))
    monkeypatch.setattr(
        socket.socket, "connect", lambda *args: pytest.fail("unit control attempted actual network")
    )
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.1:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://192.0.2.1:9999")
    for endpoint in (
        "http://192.0.2.1:11434",
        "http://localhost:11434",
        "http://127.0.0.1:11434/other",
    ):
        error(
            "INVALID_INPUT",
            lambda endpoint=endpoint: api().OllamaChannelsAdapter(
                endpoint=endpoint, model="local-fixture"
            ),
        )
    assert not calls
    builtin = api().OllamaChannelsAdapter(
        endpoint="http://127.0.0.1:11434", model="local-fixture", timeout_seconds=1
    )
    receipt = generate(c, "transport-valid", builtin)
    assert (
        receipt["generation_provenance"]["kind"] == "builtin_ollama_transport" and len(calls) == 1
    )
    support.graph_check(c.store, receipt)
    transport["status"] = 302
    error("PROVIDER_UNAVAILABLE", lambda: generate(c, "redirect", builtin))
    assert len(calls) == 2
    transport["status"] = 200
    transport["raw"] = b"x" * 131073
    error(
        {"INVALID_RESPONSE", "CONSTRAINT_VIOLATION"}, lambda: generate(c, "oversize-raw", builtin)
    )
    assert len(calls) == 3
    transport["raw"], transport["dribble"] = raw, True
    deadline = api().OllamaChannelsAdapter(
        endpoint="http://127.0.0.1:11434", model="local-fixture", timeout_seconds=0.025
    )
    error("PROVIDER_UNAVAILABLE", lambda: generate(c, "dribble-deadline", deadline))
    assert len(calls) == 4 and len(results(c)) == 1


def test_u11_independent_mechanical_oracle_catches_seeded_wrong_records(case):
    c = case
    good = Provider().output
    support.output_check(good, c.selection, c.profiles)
    for kind in ("duplicate", "source", "policy", "unknown"):
        bad = copy.deepcopy(good)
        if kind == "duplicate":
            for item in bad["adaptations"]:
                item["hook"] = "Work smarter with AI."
        elif kind == "source":
            bad["adaptations"][0]["source_ids"] = ["wrong-origin"]
        elif kind == "policy":
            bad["adaptations"][1]["content"]["subject"] = "\U0001f680" * 31
        else:
            bad["human_confirmation"] = True
        with pytest.raises(AssertionError):
            support.output_check(bad, c.selection, c.profiles)
    receipt = generate(c, "oracle-binding")
    support.graph_check(c.store, receipt)
    wrong = copy.deepcopy(receipt)
    wrong["origin_ref"]["content_sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        support.graph_check(c.store, wrong)
    bad_semantics = copy.deepcopy(good)
    bad_semantics["adaptations"][0]["content"]["body"] = (
        "Install Cairntir and every commit automatically reads your code, "
        "installs trusted rules and improves your results."
    )
    support.output_check(bad_semantics, c.selection, c.profiles)
    assert "every commit automatically" in bad_semantics["adaptations"][0]["content"]["body"]
    assert (HERE / "SEMANTIC-RUBRIC.md").is_file() and (HERE / "BAD-CONTRASTS.md").is_file()
