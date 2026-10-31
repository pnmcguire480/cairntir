from __future__ import annotations

import ast
import base64
import copy
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from ideation_outlines_unit import i03_factory as factory
from ideation_outlines_unit import test_i05 as legacy

from cairntir import ideation_outline_assembler as assembler
from cairntir import ideation_outlines as outlines

from . import fixtures, oracles
from .ast_contract import dump_contract

HERE = Path(__file__).resolve().parent
V1_HERE = HERE.parent / "ideation_outlines_unit"


def api():
    return outlines


def snapshot(db):
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
        return fixtures.sha(connection.serialize())


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def case(tmp_path, monkeypatch):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer

    data = fixtures.prepare_inputs(tmp_path / "input")
    embeddings = HashEmbeddingProvider(dimension=32)
    db = tmp_path / "staged.db"
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
        root=data["source_root"],
        db=db,
        embeddings=embeddings,
        store=store,
        wing="i05-staged-synthetic",
        context=data["context"],
        requests=data["requests"],
        plan=data["assembly_plan"],
        planned=data["planned"],
        allowed_ports=set(),
        unauthorized_network=[],
        unauthorized_processes=[],
        snapshot_helpers=[],
    )
    connect, connect_ex, popen = socket.socket.connect, socket.socket.connect_ex, subprocess.Popen

    def network(original, sock, address):
        if (
            isinstance(address, tuple)
            and address[0] == "127.0.0.1"
            and address[1] in c.allowed_ports
        ):
            return original(sock, address)
        c.unauthorized_network.append(repr(address))
        pytest.fail("Undeclared network call")

    def process(*args, **kwargs):
        command = args[0] if len(args) == 1 and isinstance(args[0], list) else []
        helper = (
            "from pathlib import Path; import sys; from cairntir.memory.store"
            " import _copy_locked_database; _copy_locked_database(Path(sys.ar"
            "gv[1]), Path(sys.argv[2]))"
        )
        expected = {
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if len(command) == 5 and all(isinstance(v, str) for v in command):
            target = Path(command[4]).resolve()
            if (
                command[:4] == [sys.executable, "-c", helper, str(db.resolve())]
                and target.parent.parent == Path(tempfile.gettempdir()).resolve()
                and target.parent.name.startswith(("cairntir-context-", "cairntir-grant-"))
                and target.name in {db.name, "grant.db"}
                and not target.exists()
                and kwargs in (expected, dict(expected, text=True))
            ):
                c.snapshot_helpers.append(command)
                return popen(*args, **kwargs)
        c.unauthorized_processes.append("Undeclared process; arguments/environment withheld")
        pytest.fail("Undeclared subprocess")

    monkeypatch.setattr(
        socket.socket, "connect", lambda sock, address: network(connect, sock, address)
    )
    monkeypatch.setattr(
        socket.socket, "connect_ex", lambda sock, address: network(connect_ex, sock, address)
    )
    monkeypatch.setattr(subprocess, "Popen", process)
    yield c
    store.close()
    assert not c.unauthorized_network and not c.unauthorized_processes


def generate(c, adapter=None, key="initial", **changes):
    adapter = adapter or fixtures.FixtureAdapter(c.planned)
    args = dict(  # noqa: C408
        wing=c.wing,
        context=c.context,
        requests=c.requests,
        source_root=c.root,
        adapter=adapter,
        idempotency_key=key,
        strategy="staged_v2",
        assembly_plan=c.plan,
    )
    store = changes.pop("store", c.store)
    args.update(changes)
    return api().generate_outline_set(store, **args)


def reopen(c, ref, **changes):
    store = changes.pop("store", c.store)
    return api().get_outline_set(store, ref, source_root=c.root, **changes)


def assert_no_partial(c):
    assert not oracles.accepted(c.store, c.wing)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def test_s01_complete_host_assembly(case):
    from cairntir.memory.store import DrawerStore

    c = case
    adapter = fixtures.FixtureAdapter(c.planned)

    def before_dispatch(index, raw, cancel):
        assert not c.store.transaction_active

        def bound(record):
            stored = list(strings(record))
            return (
                record.get("schema") == "cairntir.outline-node-prepared.v2"
                and adapter.jobs[index]["node_id"] in stored
                and fixtures.sha(raw) in stored
                and (raw.decode() in stored or base64.b64encode(raw).decode() in stored)
            )

        assert any(bound(record) for record in oracles.records(c.store, c.wing).values())

    adapter.callback = before_dispatch
    result = generate(c, adapter)
    assert adapter.calls == 14
    oracles.check_receipt(result, c.planned, adapter.raw_nodes, c.root)
    oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
    assert len(oracles.accepted(c.store, c.wing)) == 9
    before = snapshot(c.db)
    with DrawerStore(c.db, c.embeddings, read_only=True) as reader:
        assert reopen(c, result["ref"], store=reader) == result
    assert snapshot(c.db) == before
    assert (
        c.store.list_by(wing="untouched-project", limit=None)[0].content
        == "Independent unrelated project memory."
    )
    source_root = c.tmp / "canonical-input"
    shutil.copytree(V1_HERE / "i03-fixture/sources", source_root)
    channel = factory.create_channel_graph(c.store, c.wing, source_root)
    selection = json.loads((V1_HERE / "i03-fixture/selection.json").read_bytes())
    request = dict(
        c.requests[0],
        request_id="canonical-four",
        idea_id="SYN-SELECT-item-1",
        hook_id="community-discussion",
        format_id="operator-four-point",
    )
    request["production_constraints"] = [
        (
            "Use exactly4 points,5 bridges,3 production notes and2 planned ac"
            "tions; preserve all other source/uncertainty constraints."
        )
    ]
    row = fixtures.canonical_plan(request, selection, source_root)
    generic = fixtures.FixtureAdapter([row])
    compiled = generate(
        c,
        generic,
        "generic-four",
        context={"kind": "i03", "ref": channel["ref"]},
        requests=[request],
        source_root=source_root,
        assembly_plan={"schema": c.plan["schema"], "requests": [row["assembly_plan_entry"]]},
    )
    assert generic.calls == 8
    oracles.check_receipt(compiled, [row], generic.raw_nodes, source_root)


def test_s02_owned_quote_span_corruption(case):
    c = case
    for i, fault in enumerate(("owner", "anchor", "digest", "range", "utf8", "confirmation")):
        plan, context = copy.deepcopy(c.plan), copy.deepcopy(c.context)
        span = plan["requests"][0]["spans"][0]
        if fault == "owner":
            span["source_id"] = "SYN-HOOKS"
        elif fault == "anchor":
            span["anchor_id"] = "angle-founder"
        elif fault == "digest":
            span["excerpt_sha256"] = "0" * 64
        elif fault == "range":
            span["excerpt_byte_end"] += 1
        elif fault == "utf8":
            span = plan["requests"][1]["spans"][0]
            excerpt = c.context["sources"][0]["anchors"][1]["excerpt"].encode()
            span["excerpt_byte_start"] = excerpt.index("—".encode()) + 1
            span["span_sha256"] = fixtures.sha(
                excerpt[span["excerpt_byte_start"] : span["excerpt_byte_end"]]
            )
        else:
            context["human_confirmation"] = True
        adapter = fixtures.FixtureAdapter(c.planned)
        with pytest.raises(api().OutlineError):
            generate(c, adapter, f"bad-span-{i}", context=context, assembly_plan=plan)
        assert adapter.calls == 0
        assert_no_partial(c)
    path = c.root / c.context["sources"][0]["path"]
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"\r\n", b"\n"))
    try:
        adapter = fixtures.FixtureAdapter(c.planned)
        with pytest.raises(api().OutlineError):
            generate(c, adapter, "normalization-refused")
        assert adapter.calls == 0
    finally:
        path.write_bytes(raw)


def test_s03_graph_identity_and_unknown_fields(case):
    c = case
    for i, fault in enumerate(
        ("missing-slot", "foreign-action-ref", "future-dependency", "duplicate-span")
    ):
        plan = copy.deepcopy(c.plan)
        item = plan["requests"][0]
        if fault == "missing-slot":
            item["component_bindings"].pop()
        elif fault == "foreign-action-ref":
            item["actions"][0]["component_slots"] = ["unowned-component"]
        elif fault == "future-dependency":
            item["actions"][0]["depends_on"] = ["review"]
        else:
            item["spans"].append(copy.deepcopy(item["spans"][0]))
        adapter = fixtures.FixtureAdapter(c.planned)
        with pytest.raises(api().OutlineError):
            generate(c, adapter, f"bad-plan-{i}", assembly_plan=plan)
        assert adapter.calls == 0
    for i, extra in enumerate(("id", "source_ids", "human_confirmation", "depends_on")):
        adapter = fixtures.FixtureAdapter(c.planned)
        adapter.outputs[0][extra] = True
        with pytest.raises(api().OutlineError) as error:
            generate(c, adapter, f"unknown-{i}")
        assert error.value.code == "INVALID_RESPONSE" and adapter.calls == 1
        oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
        assert_no_partial(c)
    result = generate(c)
    for key, value in (
        ("content_sha256", "0" * 64),
        ("portable_identity", "00000000-0000-0000-0000-000000000000"),
        ("wing", "untouched-project"),
    ):
        before = snapshot(c.db)
        with pytest.raises(api().OutlineError):
            reopen(c, dict(result["ref"], **{key: value}))
        assert snapshot(c.db) == before
    target = result["outlines"][0]["actions"][0]["ref"]["drawer_id"]
    with sqlite3.connect(c.db) as sql:
        sql.execute("UPDATE drawers SET content='{}' WHERE id=?", (target,))
    before = snapshot(c.db)
    with pytest.raises(api().OutlineError):
        reopen(c, result["ref"])
    assert snapshot(c.db) == before


def test_s04_phase_failure_never_accepts_partial(case):
    c = case
    for i in (2, 13):
        adapter = fixtures.FixtureAdapter(c.planned)
        adapter.outputs[i] = {"missing_promised_prose": True}
        with pytest.raises(api().OutlineError) as error:
            generate(c, adapter, f"invalid-node-{i}")
        assert error.value.code == "INVALID_RESPONSE" and adapter.calls == i + 1
        oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
        assert_no_partial(c)


def test_s05_replay_indeterminate_and_two_connection_race(case, monkeypatch):
    from cairntir.memory.store import DrawerStore

    c = case
    adapter = fixtures.FixtureAdapter(c.planned)
    first = generate(c, adapter)
    before = snapshot(c.db)
    again = generate(c, adapter)
    assert again["ref"] == first["ref"] and again["replayed"] is True and adapter.calls == 14
    assert snapshot(c.db) == before
    changed = copy.deepcopy(c.plan)
    changed["requests"][0]["actions"][0]["purpose"] += " Revised."
    with pytest.raises(api().OutlineError) as error:
        generate(c, adapter, assembly_plan=changed)
    assert error.value.code == "CONFLICT" and adapter.calls == 14

    class Interrupted(BaseException):
        pass

    lost = fixtures.FixtureAdapter(
        c.planned, changes={0: Interrupted("Synthetic acknowledgement lost after preparation")}
    )
    with pytest.raises((Interrupted, api().OutlineError)):
        generate(c, lost, "interrupted")
    with pytest.raises(api().OutlineError) as error:
        generate(c, lost, "interrupted")
    assert error.value.code == "INDETERMINATE" and lost.calls == 1
    clean = fixtures.FixtureAdapter(c.planned)
    clean.outputs[0]["title"] += " clean boundary"
    original_once, stopped = c.store.execute_once, []

    def interrupt_between(**kwargs):
        persisted = list(strings(oracles.records(c.store, c.wing)))
        if (
            clean.calls == 1
            and clean.raws
            and fixtures.sha(clean.raws[0]) in persisted
            and not stopped
        ):
            stopped.append(True)
            raise Interrupted("Synthetic interruption before any next-node preparation")
        return original_once(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(c.store, "execute_once", interrupt_between)
        with pytest.raises((Interrupted, api().OutlineError)):
            generate(c, clean, "clean-node-boundary")
    assert stopped and clean.calls == 1
    resumed = generate(c, clean, "clean-node-boundary")
    assert resumed["status"] == "committed_draft" and clean.calls == 14
    barrier, entered, release = threading.Barrier(3), threading.Event(), threading.Event()
    outcomes, adapters = [], []
    mutex = threading.Lock()

    def run():
        with DrawerStore(c.db, c.embeddings) as connection:

            def wait(index, raw, cancel):
                if index == 0:
                    entered.set()
                    assert release.wait(10)

            candidate = fixtures.FixtureAdapter(c.planned, callback=wait)
            with mutex:
                adapters.append(candidate)
            barrier.wait(timeout=10)
            try:
                outcome = generate(c, candidate, "two-connections", store=connection)
            except BaseException as error:  # noqa: BLE001
                outcome = error
            with mutex:
                outcomes.append(outcome)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    try:
        barrier.wait(timeout=10)
        assert entered.wait(10)
        for _ in range(100):
            if outcomes:
                break
            threading.Event().wait(0.02)
        assert len(outcomes) == 1 and isinstance(outcomes[0], api().OutlineError)
        assert outcomes[0].code == "INDETERMINATE"
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert sum(item.calls for item in adapters) == 14
    assert sum(isinstance(item, dict) for item in outcomes) == 1


def test_s06_cancel_and_returned_raw_custody(case, monkeypatch):
    c = case
    cancel = threading.Event()
    cancel.set()
    adapter = fixtures.FixtureAdapter(c.planned)
    with pytest.raises(api().OutlineError) as error:
        generate(c, adapter, "cancel-before", cancel=cancel)
    assert error.value.code == "CANCELLED" and adapter.calls == 0
    cancel.clear()
    adapter = fixtures.FixtureAdapter(c.planned, callback=lambda index, raw, event: event.set())
    with pytest.raises(api().OutlineError) as error:
        generate(c, adapter, "cancel-after", cancel=cancel)
    assert error.value.code == "CANCELLED" and adapter.calls == 1
    oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
    with pytest.raises(api().OutlineError):
        generate(c, adapter, "cancel-after", cancel=threading.Event())
    assert adapter.calls == 1
    assert_no_partial(c)
    from cairntir.ideation_channels import ChannelError

    unavailable = fixtures.FixtureAdapter(
        c.planned,
        changes={
            0: ChannelError("CANCELLED", "Synthetic in-flight cancellation before raw return")
        },
    )
    with pytest.raises(api().OutlineError) as error:
        generate(c, unavailable, "cancel-inflight")
    assert error.value.code == "CANCELLED" and unavailable.calls == 1 and not unavailable.raws
    final_cancel = threading.Event()
    adapter = fixtures.FixtureAdapter(c.planned)
    once = c.store.execute_once

    def stop_at_commit(**kwargs):
        persisted = list(strings(oracles.records(c.store, c.wing)))
        if adapter.calls == 14 and all(fixtures.sha(raw) in persisted for raw in adapter.raws):
            final_cancel.set()
        return once(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(c.store, "execute_once", stop_at_commit)
        with pytest.raises(api().OutlineError) as error:
            generate(c, adapter, "cancel-at-commit", cancel=final_cancel)
    assert final_cancel.is_set() and error.value.code == "CANCELLED" and adapter.calls == 14
    oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
    assert_no_partial(c)
    original_add, refused = c.store.add, []

    def refuse_evidence(*args, **kwargs):
        drawer = args[0] if args else kwargs["drawer"]
        kind = json.loads(drawer.content).get("schema", "")
        if kind in {"cairntir.outline-node-exchange.v2", "cairntir.outline-failure.v2"}:
            refused.append(kind)
            raise OSError("Synthetic evidence persistence unavailable")
        return original_add(*args, **kwargs)

    unsaved = fixtures.FixtureAdapter(c.planned)
    unsaved.outputs[0]["title"] += " unsaved evidence case"
    with monkeypatch.context() as patch:
        patch.setattr(c.store, "add", refuse_evidence)
        with pytest.raises((OSError, api().OutlineError)):
            generate(c, unsaved, "evidence-unsaved")
    assert refused and unsaved.calls == 1
    assert fixtures.sha(unsaved.raws[0]) not in list(strings(oracles.records(c.store, c.wing)))
    assert_no_partial(c)


def test_s07_live_access_and_source_revalidation(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant, revoke_grant

    c = case
    path = c.root / c.context["sources"][0]["path"]
    original = path.read_bytes()
    for target in (0, 13):

        def drift(index, raw, cancel):
            if index == target:  # noqa: B023
                path.write_bytes(original + b"\r\nChanged during declared generation.\r\n")

        adapter = fixtures.FixtureAdapter(c.planned, callback=drift)
        try:
            with pytest.raises(api().OutlineError):
                generate(c, adapter, f"source-drift-{target}")
            assert adapter.calls == target + 1
            oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
        finally:
            path.write_bytes(original)
        token = issue_grant(
            c.store,
            scopes=[{"wing": c.wing, "rooms": ["ideation-outlines"]}],
            capabilities=["read", "write"],
        )

        def revoke_after(index, raw, cancel):
            if index == target:  # noqa: B023
                revoke_grant(c.store, token)  # noqa: B023

        adapter = fixtures.FixtureAdapter(c.planned, callback=revoke_after)
        with pytest.raises(AccessDenied):
            generate(c, adapter, f"live-revoke-{target}", store=bind_grant(c.store, token))
        assert adapter.calls == target + 1
    assert_no_partial(c)


def test_s08_atomic_commit_rollback(case, monkeypatch):
    c = case
    original, writes = c.store.add, []

    def fail(*args, **kwargs):
        drawer = args[0] if args else kwargs["drawer"]
        value = json.loads(drawer.content)
        if value.get("schema") == "cairntir.outline-action.v2":
            writes.append(value)
            if len(writes) == 2:
                raise OSError("Synthetic storage failure inside accepted transaction")
        return original(*args, **kwargs)

    monkeypatch.setattr(c.store, "add", fail)
    adapter = fixtures.FixtureAdapter(c.planned)
    with pytest.raises((OSError, api().OutlineError)):
        generate(c, adapter)
    assert len(writes) == 2 and adapter.calls == 14
    assert_no_partial(c)
    oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
    with c.store.transaction():
        untouched = fixtures.FixtureAdapter(c.planned)
        with pytest.raises(api().OutlineError):
            generate(c, untouched, "caller-transaction")
        assert untouched.calls == 0


def test_s09_v1_exact_wire_read_replay_projection(case):
    c = case
    baseline = json.loads((HERE / "V1-CONTRACT.json").read_bytes())
    tree = ast.parse(Path(api().__file__).read_bytes())
    definitions = {
        node.name: dump_contract(node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert all(
        definitions[name] == expected for name, expected in baseline["protected_v1_ast"].items()
    )
    constants = json.loads((HERE / "V1-CONTRACT.json").read_bytes())["constants"]
    assert (
        api()._OPTIONS == constants["options"]  # noqa: SIM300
        and fixtures.sha(api()._PREFIX.encode()) == constants["prefix_sha256"]
    )
    for suffix, function in (
        ("complete", legacy.test_b01_complete_graph_raw_wire_and_no_touch_reopen),
        ("replay", legacy.test_b06_replay_conflict_and_interrupted_attempt_never_redispatch),
        ("projection", legacy.test_b12_owned_projection_links_human_bytes_and_conflicts),
    ):
        separate = SimpleNamespace(**dict(vars(c), wing=f"{c.wing}-v1-{suffix}"))
        function(separate)
    adapter = fixtures.FixtureAdapter(c.planned)
    with pytest.raises(api().OutlineError):
        generate(c, adapter, "unknown-mode", strategy="future_unknown")
    assert adapter.calls == 0
    with pytest.raises(api().OutlineError):
        generate(c, adapter, "plan-on-v1", strategy="monolithic_v1")
    assert adapter.calls == 0


def test_s10_installed_reopen_vault_and_live_export(case, monkeypatch):
    from cairntir.access import AccessDenied, ScopedStore, bind_grant, issue_grant, revoke_grant
    from cairntir.memory.store import DrawerStore

    c = case
    adapter = fixtures.FixtureAdapter(c.planned)
    receipt = generate(c, adapter)
    positive_token = issue_grant(
        c.store,
        scopes=[{"wing": c.wing, "rooms": ["ideation-outlines"]}],
        capabilities=["read", "export"],
    )
    vault = c.tmp / "vault"
    vault.mkdir()
    human = b"# Human note\r\nExact trailing spaces.  \r\n"
    (vault / "human.md").write_bytes(human)
    before = snapshot(c.db)
    with DrawerStore(c.db, c.embeddings, read_only=True) as reader:
        scoped = bind_grant(reader, positive_token)
        assert reopen(c, receipt["ref"], store=scoped) == receipt
        projected = api().project_outline_set(
            scoped, receipt["ref"], vault_path=vault, source_root=c.root
        )
    assert snapshot(c.db) == before and projected["projection_status"] == "ready"
    projection = projected["projection"]
    path = vault / projection["outline_paths"][0]
    raw = path.read_bytes()
    prefix, suffix = "Human prefix — CRLF.\r\n".encode(), b"\r\nHuman suffix.  \r\n"
    path.write_bytes(prefix + raw + suffix)
    again = api().project_outline_set(c.store, receipt["ref"], vault_path=vault, source_root=c.root)
    oracles.check_vault(
        again["projection"],
        vault,
        {
            "human.md": human,
            path.relative_to(vault).as_posix(): {"prefix": prefix, "suffix": suffix},
        },
    )
    assert path.read_bytes() == prefix + raw + suffix
    source = vault / projection["source_paths"][0]
    source.write_bytes(source.read_bytes() + b"\nChanged immutable source note.\n")
    before_files = files(vault)
    with pytest.raises(api().OutlineError):
        api().project_outline_set(c.store, receipt["ref"], vault_path=vault, source_root=c.root)
    assert files(vault) == before_files
    scope = [{"wing": c.wing, "rooms": ["ideation-outlines"]}]
    readonly = issue_grant(c.store, scopes=scope, capabilities=["read"])
    fresh = c.tmp / "no-export"
    fresh.mkdir()
    with pytest.raises(AccessDenied):
        api().project_outline_set(
            bind_grant(c.store, readonly), receipt["ref"], vault_path=fresh, source_root=c.root
        )
    assert not list(fresh.rglob("*"))
    token = issue_grant(c.store, scopes=scope, capabilities=["read", "export"])
    original_export = ScopedStore.list_for_export
    called, revoked_snapshot = [], []

    def revoke(self, *args, **kwargs):
        called.append(True)
        if files(fresh):
            revoked_snapshot.append(files(fresh))
            revoke_grant(c.store, token)
        return original_export(self, *args, **kwargs)

    monkeypatch.setattr(ScopedStore, "list_for_export", revoke)
    with pytest.raises(AccessDenied):
        api().project_outline_set(
            bind_grant(c.store, token), receipt["ref"], vault_path=fresh, source_root=c.root
        )
    assert len(called) >= 2 and revoked_snapshot and files(fresh) == revoked_snapshot[0]


def test_s11_bounded_exact_node_protocol(case, monkeypatch):
    from cairntir.ideation_channels import ChannelError, OllamaChannelsAdapter

    c = case
    valid = fixtures.outputs_for(c.planned[0])[0]
    valid_raw = fixtures.envelope(valid)
    duplicate = valid_raw.replace(b'"eval_count":0', b'"eval_count":0,"eval_count":0', 1)
    nonfinite = valid_raw.replace(b'"eval_count":0', b'"eval_count":NaN', 1)
    inner_duplicate = (
        fixtures.canonical(valid)
        .decode()
        .replace('"assumptions":[]', '"assumptions":[],"assumptions":[]', 1)
    )
    variants = [
        fixtures.envelope(valid, done_reason="length"),
        fixtures.envelope(valid, model="wrong-model"),
        duplicate,
        nonfinite,
        fixtures.envelope(valid, response=inner_duplicate),
        fixtures.envelope(valid, response=fixtures.canonical(valid).decode() + " " * 98305),
        fixtures.envelope(valid, eval_count=1.5),
        fixtures.envelope(valid, eval_count=True),
    ]
    for i, raw in enumerate(variants):
        adapter = fixtures.FixtureAdapter(c.planned, changes={0: raw})
        with pytest.raises(api().OutlineError) as error:
            generate(c, adapter, f"protocol-{i}")
        assert error.value.code == "INVALID_RESPONSE" and adapter.calls == 1
        oracles.check_raw_retained(c.store, c.wing, adapter.raw_nodes)
    bad_length = fixtures.FixtureAdapter(c.planned)
    bad_length.outputs[6]["finished_length_estimate"] = (
        c.requests[0]["finished_length"]["maximum"] + 1
    )
    with pytest.raises(api().OutlineError) as error:
        generate(c, bad_length, "invalid-finished-length")
    assert error.value.code == "INVALID_RESPONSE" and bad_length.calls == 7
    oracles.check_raw_retained(c.store, c.wing, bad_length.raw_nodes)
    lost = fixtures.FixtureAdapter(
        c.planned, changes={1: ChannelError("PROVIDER_UNAVAILABLE", "Synthetic unavailable raw")}
    )
    with pytest.raises(api().OutlineError) as error:
        generate(c, lost, "unavailable")
    assert (
        error.value.code == "PROVIDER_UNAVAILABLE" and lost.calls == 2 and len(lost.raw_nodes) == 1
    )
    oracles.check_raw_retained(c.store, c.wing, lost.raw_nodes)
    text = json.dumps(oracles.records(c.store, c.wing))
    assert '"raw_availability": "unavailable"' in text and '"raw_response_base64": null' in text
    captured = []

    def delegate(self, raw, *, cancel=None):
        captured.append(raw)
        return b"public bounded delegate envelope"

    monkeypatch.setattr(OllamaChannelsAdapter, "generate", delegate)
    adapter = assembler.OllamaStagedOutlinesAdapter(
        endpoint="http://127.0.0.1:49321", model="public-test", timeout_seconds=180
    )
    assert adapter.identity["prompt_version"] == "i05.staged.v2"
    assert adapter.generate(b"public exact prepared bytes") == b"public bounded delegate envelope"
    assert captured == [b"public exact prepared bytes"]
    with pytest.raises(api().OutlineError):
        assembler.OllamaStagedOutlinesAdapter(
            endpoint="http://127.0.0.1:49321", model="public-test", timeout_seconds=181
        )
    assert_no_partial(c)


def test_s12_compiler_oracle_detects_missing_bridge(case):
    c = case
    adapter = fixtures.FixtureAdapter(c.planned)
    receipt = generate(c, adapter)
    broken = copy.deepcopy(receipt["outlines"][0])
    broken["outline"]["bridges"].pop()
    with pytest.raises(AssertionError):
        oracles.check_compiled_topology(broken, c.planned[0])
    edited = copy.deepcopy(receipt["outlines"][0])
    edited["outline"]["opening"]["text"] += " Invented compiler rewrite."
    with pytest.raises(AssertionError):
        oracles.check_raw_prose(edited, c.planned[0], adapter.raw_nodes)
