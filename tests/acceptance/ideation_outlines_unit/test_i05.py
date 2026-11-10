from __future__ import annotations

import copy
import hashlib
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import ideation_outlines as outlines

from . import i03_factory as i03
from . import oracles
from . import provider_fixture as provider

HERE = Path(__file__).resolve().parent


def api():
    return outlines


def snapshot(db):
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
        return hashlib.sha256(connection.serialize()).hexdigest()


def filesystem(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def case(tmp_path, monkeypatch):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer

    source_root = tmp_path / "input"
    shutil.copytree(HERE / "sources", source_root / "sources")
    embeddings = HashEmbeddingProvider(dimension=32)
    db = tmp_path / "outlines.db"
    store = DrawerStore(db, embeddings)
    store.add(
        Drawer(
            wing="untouched-project",
            room="private",
            content="Independent unrelated project memory.",
        )
    )
    c = SimpleNamespace(
        tmp=tmp_path,
        root=source_root,
        db=db,
        store=store,
        embeddings=embeddings,
        wing="synthetic-i05",
        context=json.loads((HERE / "historical-context.json").read_bytes()),
        requests=json.loads((HERE / "requests.protocol-draft.json").read_bytes()),
        allowed_ports=set(),
        unauthorized_network=[],
        unauthorized_processes=[],
        snapshot_helpers=[],
    )
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_popen = subprocess.Popen

    def network(original, sock, address):
        if (
            isinstance(address, tuple)
            and address[0] == "127.0.0.1"
            and address[1] in c.allowed_ports
        ):
            return original(sock, address)
        c.unauthorized_network.append(repr(address))
        pytest.fail("Outline preparation attempted an undeclared network transport")

    def guarded_popen(*args, **kwargs):
        command = args[0] if len(args) == 1 and isinstance(args[0], list) else []
        helper = (
            "from pathlib import Path; import sys; from cairntir.memory.store "
            "import _copy_locked_database; _copy_locked_database(Path(sys.argv"
            "[1]), Path(sys.argv[2]))"
        )
        if len(command) == 5 and all(isinstance(value, str) for value in command):
            destination = Path(command[4]).resolve()
            expected = {
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
            }
            valid_kwargs = kwargs == expected or kwargs == dict(expected, text=True)
            if (
                command[:4] == [sys.executable, "-c", helper, str(db.resolve())]
                and destination.parent.parent == Path(tempfile.gettempdir()).resolve()
                and destination.parent.name.startswith(("cairntir-context-", "cairntir-grant-"))
                and destination.name in {db.name, "grant.db"}
                and not destination.exists()
                and valid_kwargs
            ):
                c.snapshot_helpers.append(command)
                return original_popen(*args, **kwargs)
        c.unauthorized_processes.append(repr((args, kwargs)))
        pytest.fail("Outline preparation attempted an undeclared subprocess transport")

    monkeypatch.setattr(
        socket.socket, "connect", lambda sock, address: network(original_connect, sock, address)
    )
    monkeypatch.setattr(
        socket.socket,
        "connect_ex",
        lambda sock, address: network(original_connect_ex, sock, address),
    )
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    yield c
    c.store.close()
    assert not c.unauthorized_network and not c.unauthorized_processes


def adapter_for(c, requests=None, **kwargs):
    return provider.FixtureAdapter(
        [provider.output_for(r) for r in (c.requests if requests is None else requests)], **kwargs
    )


def generate(c, adapter, key="initial", **overrides):
    arguments = {
        "wing": c.wing,
        "context": c.context,
        "requests": c.requests,
        "source_root": c.root,
        "adapter": adapter,
        "idempotency_key": key,
    }
    store = overrides.pop("store", c.store)
    arguments.update(overrides)
    return api().generate_outline_set(store, **arguments)


def get(c, ref, **overrides):
    arguments = {"source_root": c.root}
    store = overrides.pop("store", c.store)
    arguments.update(overrides)
    return api().get_outline_set(store, ref, **arguments)


def test_b01_complete_graph_raw_wire_and_no_touch_reopen(case):
    from cairntir.memory.store import DrawerStore

    c = case

    def inspect(index, raw, cancel):
        assert not c.store.transaction_active
        oracles.check_wire(raw, c.requests[index], c.context, "i05-synthetic-fixture")
        oracles.check_prepared(c.store, c.wing, adapter)

    adapter = adapter_for(c, callback=inspect)
    first = generate(c, adapter)
    assert adapter.calls == 2
    oracles.check_receipt(first, c.store, c.wing, c.context, c.requests, adapter.outputs, adapter)
    assert len(oracles.accepted(c.store, c.wing)) == 9
    oracles.check_prepared(c.store, c.wing, adapter)
    oracles.check_raw_retained(c.store, c.wing, adapter.raws)
    before = snapshot(c.db)
    with DrawerStore(c.db, c.embeddings, read_only=True) as reader:
        assert get(c, first["ref"], store=reader) == first
    assert snapshot(c.db) == before
    assert (
        c.store.list_by(wing="untouched-project", limit=None)[0].content
        == "Independent unrelated project memory."
    )


def test_b02_independent_oracles_detect_broken_promised_components(case):
    c = case
    request = c.requests[0]
    output = provider.output_for(request)
    oracles.check_output(output["outline"], request, {"SYN-ANGLES", "SYN-HOOKS"}, enriched=False)
    faults = []
    wrong = copy.deepcopy(output["outline"])
    wrong["bridges"].pop(1)
    faults.append(wrong)
    wrong = copy.deepcopy(output["outline"])
    wrong["key_points"][1]["point"]["text"] = wrong["key_points"][0]["point"]["text"]
    faults.append(wrong)
    wrong = copy.deepcopy(output["outline"])
    wrong["finished_length"]["estimate"] = 901
    faults.append(wrong)
    wrong = copy.deepcopy(output["outline"])
    wrong["opening"]["source_ids"] = ["invented-source"]
    faults.append(wrong)
    wrong = copy.deepcopy(output["outline"])
    wrong["actions"][1]["depends_on"] = ["missing-action"]
    faults.append(wrong)
    wrong = copy.deepcopy(output["outline"])
    wrong["opening"]["human_confirmation"] = True
    faults.append(wrong)
    for wrong in faults:
        with pytest.raises((AssertionError, KeyError)):
            oracles.check_output(wrong, request, {"SYN-ANGLES", "SYN-HOOKS"}, enriched=False)
    human = c.tmp / "human.md"
    human.write_bytes(b"Original human bytes\r\n")
    oracles.check_human_bytes(human, b"Original human bytes\r\n")
    human.write_bytes(b"Unexpected rewrite\n")
    with pytest.raises(AssertionError):
        oracles.check_human_bytes(human, b"Original human bytes\r\n")


def test_b03_invalid_complete_outputs_collect_both_and_never_accept_partial(case):
    c = case
    for index, fault in enumerate(("bridge", "repeated-point", "length", "action")):
        adapter = adapter_for(c)
        bad = adapter.outputs[0]["outline"]
        if fault == "bridge":
            bad["bridges"].pop()
        elif fault == "repeated-point":
            bad["key_points"][1]["point"]["text"] = bad["key_points"][0]["point"]["text"]
        elif fault == "length":
            bad["finished_length"]["unit"] = "seconds"
        else:
            bad["actions"][1]["depends_on"] = ["missing-action"]
        with pytest.raises(api().OutlineError) as caught:
            generate(c, adapter, f"bad-complete-{index}")
        assert adapter.calls == 2
        oracles.check_failure(caught.value, c.store, c.wing, code="INVALID_RESPONSE")
        oracles.check_raw_retained(c.store, c.wing, adapter.raws)
        before = adapter.calls
        with pytest.raises(api().OutlineError):
            generate(c, adapter, f"bad-complete-{index}")
        assert adapter.calls == before


def test_b04_input_source_and_confirmation_refusal_without_dispatch(case):
    c = case
    inputs = []
    requests = copy.deepcopy(c.requests)
    requests[0]["finished_length"]["minimum"] = True
    inputs.append({"requests": requests})
    requests = copy.deepcopy(c.requests)
    requests[0]["format_id"] = "bad format / escape"
    inputs.append({"requests": requests})
    context = copy.deepcopy(c.context)
    context["human_confirmation"] = True
    inputs.append({"context": context})
    context = copy.deepcopy(c.context)
    context["sources"][0]["path"] = "../outside.md"
    inputs.append({"context": context})
    context = copy.deepcopy(c.context)
    context["sources"][0]["anchors"][0]["excerpt_sha256"] = "0" * 64
    inputs.append({"context": context})
    for index, overrides in enumerate(inputs):
        adapter = adapter_for(c)
        with pytest.raises(api().OutlineError) as caught:
            generate(c, adapter, f"invalid-input-{index}", **overrides)
        assert caught.value.code in {"INVALID_INPUT", "CONSTRAINT_VIOLATION", "CORRUPT_ARTIFACT"}
        assert adapter.calls == 0 and not oracles.accepted(c.store, c.wing)


def test_b05_generic_selection_format_and_exact_historical_quote(case):
    c = case
    context = copy.deepcopy(c.context)
    context["ideas"][0]["id"] = "renamed-comparison"
    context["ideas"][0]["hooks"][1]["id"] = "renamed-discussion"
    request = dict(
        c.requests[0],
        request_id="alternate-request",
        idea_id="renamed-comparison",
        hook_id="renamed-discussion",
        format_id="operator-custom-outline",
    )
    output = provider.output_for(request)
    quote = context["sources"][0]["anchors"][0]["excerpt"]
    exact = quote[quote.index("**Frame:**") : quote.index("**Best for:**")]
    example = output["outline"]["key_points"][0]["example"]
    example.update(text=exact, attribution="quoted_historical", source_ids=["SYN-ANGLES"])
    adapter = provider.FixtureAdapter([output])
    first = generate(c, adapter, "generic-valid", context=context, requests=[request])
    oracles.check_receipt(first, c.store, c.wing, context, [request], adapter.outputs, adapter)
    for index, mutation in enumerate(("wrong-owner", "changed-quote")):
        bad = copy.deepcopy(output)
        example = bad["outline"]["key_points"][0]["example"]
        if mutation == "wrong-owner":
            example["source_ids"] = ["SYN-HOOKS"]
        else:
            example["text"] = example["text"].replace("signal", "proof")
        invalid = provider.FixtureAdapter([bad])
        before = len(oracles.accepted(c.store, c.wing))
        with pytest.raises(api().OutlineError) as caught:
            generate(c, invalid, f"invalid-quote-{index}", context=context, requests=[request])
        assert caught.value.code == "INVALID_RESPONSE" and invalid.calls == 1
        assert len(oracles.accepted(c.store, c.wing)) == before


def test_b06_replay_conflict_and_interrupted_attempt_never_redispatch(case):
    c = case
    adapter = adapter_for(c)
    first = generate(c, adapter)
    before = snapshot(c.db)
    replay = generate(c, adapter)
    assert replay["ref"] == first["ref"] and replay["replayed"] is True and adapter.calls == 2
    assert snapshot(c.db) == before
    changed = copy.deepcopy(c.requests)
    changed[0]["audience"] = "A different operator audience."
    with pytest.raises(api().OutlineError) as caught:
        generate(c, adapter, requests=changed)
    assert caught.value.code == "CONFLICT" and adapter.calls == 2

    class InterruptedAcknowledgement(BaseException):
        pass

    def interrupted(index, raw, cancel):
        raise InterruptedAcknowledgement(
            "Simulated host interruption after prepared evidence, before a returned response."
        )

    lost = adapter_for(c, callback=interrupted)
    with pytest.raises((InterruptedAcknowledgement, api().OutlineError)):
        generate(c, lost, "interrupted-host")
    assert lost.calls == 1
    with pytest.raises(api().OutlineError) as caught:
        generate(c, lost, "interrupted-host")
    assert (
        caught.value.code in {"INDETERMINATE", "PROVIDER_UNAVAILABLE", "CANCELLED"}
        and lost.calls == 1
    )


def test_b07_available_raw_failure_unavailable_transport_and_response_bounds(case):
    from cairntir.ideation_channels import ChannelError

    c = case
    unavailable = adapter_for(
        c,
        changes={
            1: ChannelError(
                "PROVIDER_UNAVAILABLE", "Synthetic delegate failed before returning a response."
            )
        },
    )
    with pytest.raises(api().OutlineError) as caught:
        generate(c, unavailable, "second-unavailable")
    assert unavailable.calls == 2 and len(unavailable.raws) == 1
    oracles.check_failure(
        caught.value, c.store, c.wing, code="PROVIDER_UNAVAILABLE", unavailable=True
    )
    oracles.check_raw_retained(c.store, c.wing, unavailable.raws)
    unavailable_first = adapter_for(
        c,
        changes={
            0: ChannelError(
                "PROVIDER_UNAVAILABLE", "No response is available from this declared delegate call."
            )
        },
    )
    with pytest.raises(api().OutlineError) as caught:
        generate(c, unavailable_first, "first-unavailable")
    assert unavailable_first.calls == 1 and not unavailable_first.raws
    oracles.check_failure(
        caught.value, c.store, c.wing, code="PROVIDER_UNAVAILABLE", unavailable=True
    )
    raw = provider.envelope(provider.output_for(c.requests[0]), response="x" * 98305)
    oversized = adapter_for(c, changes={0: raw})
    with pytest.raises(api().OutlineError) as caught:
        generate(c, oversized, "oversized-response")
    assert oversized.calls == 2 and caught.value.code == "INVALID_RESPONSE"
    oracles.check_raw_retained(c.store, c.wing, oversized.raws)
    assert not oracles.accepted(c.store, c.wing)


def test_b08_cancellation_before_dispatch_and_after_raw_retains_honest_evidence(case):
    c = case
    cancel = threading.Event()
    cancel.set()
    before = adapter_for(c)
    with pytest.raises(api().OutlineError) as caught:
        generate(c, before, "cancel-before", cancel=cancel)
    assert caught.value.code == "CANCELLED" and before.calls == 0
    cancel.clear()

    def stop(index, raw, event):
        event.set()

    after = adapter_for(c, callback=stop)
    with pytest.raises(api().OutlineError) as caught:
        generate(c, after, "cancel-after-return", cancel=cancel)
    assert after.calls == 1 and len(after.raws) == 1
    oracles.check_failure(caught.value, c.store, c.wing, code="CANCELLED")
    oracles.check_raw_retained(c.store, c.wing, after.raws)
    with pytest.raises(api().OutlineError) as caught:
        generate(c, after, "cancel-after-return", cancel=threading.Event())
    assert caught.value.code == "CANCELLED" and after.calls == 1
    assert not oracles.accepted(c.store, c.wing)


def test_b09_source_drift_and_live_write_revocation_stop_remaining_dispatch(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant

    c = case
    source = c.root / c.context["sources"][0]["path"]
    original = source.read_bytes()

    def change_source(index, raw, cancel):
        source.write_bytes(original + b"\r\nChanged after preparation.\r\n")

    drift = adapter_for(c, callback=change_source)
    try:
        with pytest.raises(api().OutlineError):
            generate(c, drift, "drift-after-first")
        assert drift.calls == 1 and not oracles.accepted(c.store, c.wing)
    finally:
        source.write_bytes(original)
    token = issue_grant(
        c.store,
        scopes=[{"wing": c.wing, "rooms": ["ideation-outlines"]}],
        capabilities=["read", "write"],
    )
    scoped = bind_grant(c.store, token)

    def revoke(index, raw, cancel):
        revoke_grant(c.store, token)

    adapter = adapter_for(c, callback=revoke)
    with pytest.raises(AccessDenied):
        generate(c, adapter, "revoke-after-first", store=scoped)
    assert adapter.calls == 1 and not oracles.accepted(c.store, c.wing)


def test_b10_scoped_positive_readonly_export_and_fresh_export_revocation(case, monkeypatch):
    from cairntir.access import AccessDenied, ScopedStore, bind_grant, issue_grant, revoke_grant
    from cairntir.memory.store import DrawerStore

    c = case
    request = c.requests[:1]
    scope = [{"wing": c.wing, "rooms": ["ideation-outlines"]}]
    for index, capabilities in enumerate((["read"], ["write"])):
        token = issue_grant(c.store, scopes=scope, capabilities=capabilities)
        adapter = adapter_for(c, request)
        with pytest.raises(AccessDenied):
            generate(
                c,
                adapter,
                f"denied-scope-{index}",
                requests=request,
                store=bind_grant(c.store, token),
            )
        assert adapter.calls == 0 and not oracles.accepted(c.store, c.wing)
    token = issue_grant(c.store, scopes=scope, capabilities=["read", "write"])
    adapter = adapter_for(c, request)
    first = generate(
        c, adapter, "scoped-positive", requests=request, store=bind_grant(c.store, token)
    )
    oracles.check_receipt(first, c.store, c.wing, c.context, request, adapter.outputs, adapter)
    read = issue_grant(c.store, scopes=scope, capabilities=["read"])
    export = issue_grant(c.store, scopes=scope, capabilities=["read", "export"])
    vault = c.tmp / "scoped-vault"
    vault.mkdir()
    before = snapshot(c.db)
    with DrawerStore(c.db, c.embeddings, read_only=True) as reader:
        assert get(c, first["ref"], store=bind_grant(reader, read)) == first
        with pytest.raises(AccessDenied):
            api().project_outline_set(
                bind_grant(reader, read), first["ref"], vault_path=vault, source_root=c.root
            )
        assert not list(vault.rglob("*"))
        projected = api().project_outline_set(
            bind_grant(reader, export), first["ref"], vault_path=vault, source_root=c.root
        )
        assert projected["projection_status"] == "ready"
        oracles.check_projection(projected["projection"], vault)
    assert snapshot(c.db) == before
    token = issue_grant(c.store, scopes=scope, capabilities=["read", "export"])
    fresh_vault = c.tmp / "revoked-export-vault"
    fresh_vault.mkdir()
    original_export = ScopedStore.list_for_export
    observed = []

    def revoke_at_inventory(self, *args, **kwargs):
        observed.append((args, kwargs))
        revoke_grant(c.store, token)
        return original_export(self, *args, **kwargs)

    monkeypatch.setattr(ScopedStore, "list_for_export", revoke_at_inventory)
    with pytest.raises(AccessDenied):
        api().project_outline_set(
            bind_grant(c.store, token), first["ref"], vault_path=fresh_vault, source_root=c.root
        )
    assert observed and not list(fresh_vault.rglob("*"))


def test_b11_corrupt_missing_and_foreign_dependency_get_is_no_touch(case):
    c = case
    adapter = adapter_for(c)
    first = generate(c, adapter)
    for field, value in (
        ("content_sha256", "0" * 64),
        ("portable_identity", "00000000-0000-0000-0000-000000000000"),
        ("wing", "untouched-project"),
    ):
        before = snapshot(c.db)
        with pytest.raises(api().OutlineError):
            get(c, dict(first["ref"], **{field: value}))
        assert snapshot(c.db) == before
    target = first["outlines"][0]["actions"][0]["ref"]["drawer_id"]
    with sqlite3.connect(c.db) as connection:
        original = connection.execute(
            "SELECT content FROM drawers WHERE id=?", (target,)
        ).fetchone()[0]
        connection.execute("UPDATE drawers SET content=? WHERE id=?", ("{}", target))
    before = snapshot(c.db)
    with pytest.raises(api().OutlineError) as caught:
        get(c, first["ref"])
    assert caught.value.code == "CORRUPT_ARTIFACT" and snapshot(c.db) == before
    with sqlite3.connect(c.db) as connection:
        connection.execute("UPDATE drawers SET content=? WHERE id=?", (original, target))
        connection.execute("DELETE FROM drawers WHERE id=?", (target,))
    before = snapshot(c.db)
    with pytest.raises(api().OutlineError):
        get(c, first["ref"])
    assert snapshot(c.db) == before


def test_b12_owned_projection_links_human_bytes_and_conflicts(case):
    c = case
    first = generate(c, adapter_for(c))
    vault = c.tmp / "vault"
    vault.mkdir()
    human = vault / "human.md"
    human_bytes = b"# Human note\r\nKeep exact trailing spaces.  \r\n"
    human.write_bytes(human_bytes)
    projected = api().project_outline_set(
        c.store, first["ref"], vault_path=vault, source_root=c.root
    )
    assert projected["projection_status"] == "ready"
    oracles.check_projection(projected["projection"], vault)
    path = vault / projected["projection"]["outline_paths"][0]
    note = path.read_bytes()
    assert (
        note.count(b"<!-- cairntir:outline:begin -->")
        == note.count(b"<!-- cairntir:outline:end -->")
        == 1
    )
    prefix = "Human introduction — exact CRLF.\r\n\r\n".encode()
    suffix = b"\r\n\r\nHuman trailing notes.  \r\n"
    path.write_bytes(prefix + note + suffix)
    immutable = {
        name: (vault / name).read_bytes()
        for name in projected["projection"]["paths"]
        if name not in projected["projection"]["outline_paths"]
    }
    again = api().project_outline_set(c.store, first["ref"], vault_path=vault, source_root=c.root)
    assert again["projection_status"] == "ready"
    oracles.check_projection(again["projection"], vault)
    assert path.read_bytes() == prefix + note + suffix
    oracles.check_human_bytes(human, human_bytes)
    assert all((vault / name).read_bytes() == raw for name, raw in immutable.items())
    source = vault / projected["projection"]["source_paths"][0]
    raw = source.read_bytes()
    source.write_bytes(raw + b"\n[[MissingGeneratedTarget]]\n")
    with pytest.raises(AssertionError):
        oracles.check_projection(projected["projection"], vault)
    source.write_bytes(raw)
    path.write_bytes(
        path.read_bytes().replace(
            b"<!-- cairntir:outline:begin -->",
            b"<!-- cairntir:outline:begin -->\nUnexpected generated edit.",
            1,
        )
    )
    before = filesystem(vault)
    with pytest.raises(api().OutlineError) as caught:
        api().project_outline_set(c.store, first["ref"], vault_path=vault, source_root=c.root)
    assert caught.value.code == "CONFLICT" and filesystem(vault) == before


def test_b13_public_canonical_i03_graph_stays_provisional_and_source_bound(case):
    c = case
    source_root = c.tmp / "canonical-input"
    shutil.copytree(HERE / "i03-fixture" / "sources", source_root)
    channel_set = i03.create_channel_graph(c.store, c.wing, source_root)
    request = dict(
        c.requests[0],
        request_id="canonical-discussion",
        idea_id="SYN-SELECT-item-1",
        hook_id="community-discussion",
        format_id="operator-canonical-format",
    )
    output = provider.output_for(request, source_ids=("SYN-SELECT", "SYN-DETAIL"))
    adapter = provider.FixtureAdapter([output])
    first = generate(
        c,
        adapter,
        "canonical-context",
        context={"kind": "i03", "ref": channel_set["ref"]},
        requests=[request],
        source_root=source_root,
    )
    assert first["context"]["kind"] == "i03" and first["context"]["ref"] == channel_set["ref"]
    assert (
        first["context"]["human_confirmation"] is False
        and first["context"]["attribution"] == "historical_record_unverified"
    )
    oracles.check_receipt(
        first,
        c.store,
        c.wing,
        first["context"],
        [request],
        adapter.outputs,
        adapter,
        source_ids={"SYN-SELECT", "SYN-DETAIL"},
    )
    before = snapshot(c.db)
    assert get(c, first["ref"], source_root=source_root) == first and snapshot(c.db) == before
    bad = {"kind": "i03", "ref": dict(channel_set["ref"], content_sha256="0" * 64)}
    untouched = provider.FixtureAdapter([output])
    with pytest.raises(api().OutlineError):
        generate(
            c,
            untouched,
            "forged-canonical-ref",
            context=bad,
            requests=[request],
            source_root=source_root,
        )
    assert untouched.calls == 0


def test_b14_bounded_raw_transport_wrapper_and_caller_owned_transaction(case, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from cairntir.ideation_channels import OllamaChannelsAdapter

    c = case
    request = c.requests[:1]
    output = provider.output_for(request[0])
    state = {"mode": "valid", "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/api/generate"
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state["requests"].append(raw)
            mode = state["mode"]
            if mode == "stall":
                time.sleep(0.5)
            body = b"x" * 131073 if mode == "oversize" else provider.envelope(output)
            if mode == "status":
                body = b"Synthetic inaccessible HTTP error body."
            self.send_response(503 if mode == "status" else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionResetError, OSError):
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    def forbidden_prepare(*args, **kwargs):
        raise AssertionError("The I05 adapter must not use I03 preparation.")

    monkeypatch.setattr(OllamaChannelsAdapter, "prepare", forbidden_prepare)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    c.allowed_ports.add(server.server_port)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        adapter = api().OllamaOutlinesAdapter(
            endpoint=endpoint, model="i05-synthetic-fixture", timeout_seconds=2
        )
        assert (
            adapter.identity["prompt_version"] == "i05.v1"
            and adapter.identity["schema_version"] == "cairntir.outline-output.v1"
        )
        first = generate(c, adapter, "local-http-valid", requests=request)
        assert first["status"] == "committed_draft" and len(state["requests"]) == 1
        oracles.check_wire(state["requests"][0], request[0], c.context, "i05-synthetic-fixture")
        for mode in ("status", "oversize", "stall"):
            state["mode"] = mode
            scoped_case = SimpleNamespace(**dict(vars(c), wing=f"synthetic-i05-http-{mode}"))
            adapter = api().OllamaOutlinesAdapter(
                endpoint=endpoint,
                model="i05-synthetic-fixture",
                timeout_seconds=0.08 if mode == "stall" else 2,
            )
            started = time.monotonic()
            with pytest.raises(api().OutlineError) as caught:
                generate(scoped_case, adapter, f"local-http-{mode}", requests=request)
            assert time.monotonic() - started < 3
            expected_code = "CONSTRAINT_VIOLATION" if mode == "oversize" else "PROVIDER_UNAVAILABLE"
            assert caught.value.code == expected_code
            oracles.check_failure(
                caught.value, c.store, scoped_case.wing, code=expected_code, unavailable=True
            )
        assert len(state["requests"]) == 4
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()
    adapter = adapter_for(c)
    with c.store.transaction():
        before = snapshot(c.db)
        with pytest.raises(api().OutlineError):
            generate(c, adapter, "caller-transaction")
        assert adapter.calls == 0 and snapshot(c.db) == before
        with pytest.raises(api().OutlineError):
            api().project_outline_set(c.store, first["ref"], vault_path=c.tmp, source_root=c.root)
