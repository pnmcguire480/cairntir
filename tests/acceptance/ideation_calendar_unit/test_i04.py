from __future__ import annotations

import copy
import hashlib
import json
import queue
import shutil
import socket
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from cairntir import ideation_calendar

from . import i03_factory as factory
from . import oracles as oracle

HERE = Path(__file__).resolve().parent


def api():
    return ideation_calendar


def snapshot(db):
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
        return hashlib.sha256(conn.serialize()).hexdigest()


@pytest.fixture
def case(tmp_path, monkeypatch):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore
    from cairntir.memory.taxonomy import Drawer

    def no_network(*args, **kwargs):
        pytest.fail("Calendar planning attempted network/publication transport")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    root = tmp_path / "input"
    shutil.copytree(HERE / "sources", root / "sources")
    db = tmp_path / "calendar.db"
    store = DrawerStore(db, HashEmbeddingProvider(dimension=32))
    store.add(
        Drawer(
            wing="untouched-project",
            room="private",
            content="An unrelated project must remain untouched.",
        )
    )
    c = SimpleNamespace(
        root=root,
        db=db,
        store=store,
        tmp=tmp_path,
        wing="reversal-test-i04",
        context=json.loads((HERE / "synthetic-context.json").read_bytes()),
        policy=json.loads((HERE / "policy.json").read_bytes()),
        embeddings=HashEmbeddingProvider(dimension=32),
    )
    yield c
    c.store.close()


def generate(c, key="calendar-initial", **overrides):
    arguments = {
        "wing": c.wing,
        "context": c.context,
        "policy": c.policy,
        "source_root": c.root,
        "idempotency_key": key,
    }
    store = overrides.pop("store", c.store)
    arguments.update(overrides)
    return api().generate_calendar(store, **arguments)


def refuse(c, action):
    before = snapshot(c.db)
    with pytest.raises(api().CalendarError) as caught:
        action()
    assert isinstance(caught.value.code, str) and caught.value.code
    assert snapshot(c.db) == before


def get(c, ref):
    return api().get_calendar(c.store, ref, source_root=c.root)


def revise(c, prior, changes, key="calendar-edit", *, store=None):
    return api().revise_calendar(
        store or c.store,
        prior["ref"],
        expected_revision=prior["revision"],
        changes=changes,
        idempotency_key=key,
        source_root=c.root,
    )


def test_a01_synthetic_thirty_day_generation_reopen_no_network(case):
    from cairntir.memory.store import DrawerStore

    c = case
    first = generate(c)
    assert first["revision"] == 1 and first["previous_ref"] is None
    assert first["ref"]["wing"] == c.wing and first["replayed"] is False
    oracle.check_view(first, c.context, c.policy)
    oracle.check_base_collision(first)
    saved = next(
        row
        for row in c.store.list_by(wing=c.wing, room="ideation-calendars", limit=None)
        if row.id == first["ref"]["drawer_id"]
    )
    assert hashlib.sha256(saved.content.encode()).hexdigest() == first["ref"]["content_sha256"]
    assert c.store.portable_identity(saved.id) == first["ref"]["portable_identity"]
    before = snapshot(c.db)
    with DrawerStore(c.db, c.embeddings, read_only=True) as reopened:
        loaded = api().get_calendar(reopened, first["ref"], source_root=c.root)
        assert loaded == first
    assert snapshot(c.db) == before
    replay = generate(c)
    assert replay["ref"] == first["ref"] and replay["replayed"] is True
    assert snapshot(c.db) == before
    assert (
        c.store.list_by(wing="untouched-project", limit=None)[0].content
        == "An unrelated project must remain untouched."
    )


def test_a02_oracles_detect_missing_dates_collision_lineage_and_attribution(case):
    c = case
    first = generate(c)
    for _label, broken in oracle.broken_views(first):
        with pytest.raises((AssertionError, KeyError), match=r".*"):
            oracle.check_view(broken, c.context, c.policy)
            oracle.check_base_collision(broken)
    second = copy.deepcopy(first)
    second["revision"] += 1
    second["previous_ref"] = None
    second["ref"] = dict(second["ref"], drawer_id=second["ref"]["drawer_id"] + 999)
    with pytest.raises(AssertionError):
        oracle.check_lineage(first, second)


def test_a03_date_cta_notes_edit_survives_reopen_and_exposes_blackout(case):
    from cairntir.memory.store import DrawerStore

    c = case
    first = generate(c)
    friday = next(item for date, item in oracle.entries(first) if date == "2026-11-06")
    changes = [
        {
            "entry_id": friday["entry_id"],
            "date": "2026-11-26",
            "cta": "Reply with one disagreement you would investigate before making a claim.",
            "notes": "Human editor moved this planning item; blackout must stay visible.",
        }
    ]
    second = revise(c, first, changes)
    oracle.check_lineage(first, second)
    oracle.check_view(
        second,
        c.context,
        c.policy,
        scheduled=tuple(
            "2026-11-26" if date == "2026-11-06" else date for date in oracle.SCHEDULED
        ),
    )
    changed = next(
        item for date, item in oracle.entries(second) if item["entry_id"] == friday["entry_id"]
    )
    assert changed["cta"] == changes[0]["cta"] and changed["notes"] == changes[0]["notes"]
    blackout = [
        row
        for row in second["collisions"]
        if row["kind"] == "blackout" and row["date"] == "2026-11-26"
    ]
    assert len(blackout) == 1 and friday["entry_id"] in blackout[0]["entry_ids"]
    with DrawerStore(c.db, c.embeddings, read_only=True) as reopened:
        assert api().get_calendar(reopened, first["ref"], source_root=c.root) == first
        assert api().get_calendar(reopened, second["ref"], source_root=c.root) == second
    before = snapshot(c.db)
    replay = revise(c, first, changes)
    assert replay["ref"] == second["ref"] and replay["replayed"] is True
    assert snapshot(c.db) == before
    refuse(c, lambda: revise(c, first, [dict(changes[0], notes="Conflicting reuse of edit key.")]))
    refuse(c, lambda: revise(c, first, changes, key="another-stale-edit"))


def test_a04_invalid_editor_and_repurpose_chronology_refuse_without_writes(case):
    c = case
    first = generate(c)
    monday = next(item for date, item in oracle.entries(first) if date == "2026-11-02")
    invalid = [
        [{"entry_id": "missing", "date": "2026-11-03"}],
        [{"entry_id": monday["entry_id"], "date": "2026-12-01"}],
        [{"entry_id": monday["entry_id"], "date": "2026-11-05"}],
        [{"entry_id": monday["entry_id"], "cta": " "}],
        [{"entry_id": monday["entry_id"], "hook_id": "journal-short"}],
        [{"entry_id": monday["entry_id"], "surprise": "ignored?"}],
        [{"entry_id": monday["entry_id"], "notes": 7}],
        [
            {"entry_id": monday["entry_id"], "notes": "one"},
            {"entry_id": monday["entry_id"], "notes": "two"},
        ],
    ]
    for index, changes in enumerate(invalid):
        refuse(
            c,
            lambda changes=changes, index=index: revise(
                c, first, changes, key=f"invalid-edit-{index}"
            ),
        )


def test_a05_policy_and_timezone_refusal_are_typed_and_atomic(case):
    c = case
    invalid = []
    for field, value in (
        ("start_date", "2026-02-30"),
        ("days", 29),
        ("timezone", "Not/AZone"),
        ("daily_capacity", 0),
    ):
        invalid.append(dict(c.policy, **{field: value}))
    wrong = copy.deepcopy(c.policy)
    wrong["weekly_slots"][0]["hook_cycle"] = ["missing-hook"]
    invalid.append(wrong)
    wrong = copy.deepcopy(c.policy)
    wrong["blackouts"][0]["date"] = "2026-13-01"
    invalid.append(wrong)
    for index, policy in enumerate(invalid):
        refuse(
            c,
            lambda index=index, policy=policy: generate(
                c, f"invalid-policy-{index}", policy=policy
            ),
        )
    named = dict(c.policy, timezone="America/New_York")
    try:
        ZoneInfo(named["timezone"])
    except ZoneInfoNotFoundError:
        refuse(c, lambda: generate(c, "unavailable-named-zone", policy=named))
    else:
        result = generate(c, "available-named-zone", policy=named)
        assert result["policy"]["timezone"] == "America/New_York"
        assert [day["date"] for day in result["days"]] == list(oracle.DATES)


def test_a06_source_bytes_anchors_paths_and_relations_refuse_before_write(case):
    c = case
    invalid = []
    for field, value in (
        ("sha256", "0" * 64),
        ("path", "../outside.md"),
        ("path", "C:/outside.md"),
    ):
        context = copy.deepcopy(c.context)
        context["sources"][0][field] = value
        invalid.append(context)
    for field, value in (
        ("anchor", "### Missing"),
        ("excerpt", "A substituted source excerpt"),
        ("excerpt_sha256", "0" * 64),
    ):
        context = copy.deepcopy(c.context)
        context["sources"][0]["anchors"][0][field] = value
        invalid.append(context)
    context = copy.deepcopy(c.context)
    context["sources"][0]["anchors"].append(copy.deepcopy(context["sources"][0]["anchors"][0]))
    invalid.append(context)
    context = copy.deepcopy(c.context)
    context["ideas"][0]["hooks"][0]["source_ref"] = {
        "source_id": "synthetic-i04-ideas",
        "anchor_id": "angle-journal",
    }
    invalid.append(context)
    context = copy.deepcopy(c.context)
    context["human_confirmation"] = True
    invalid.append(context)
    for index, context in enumerate(invalid):
        refuse(
            c,
            lambda index=index, context=context: generate(
                c, f"invalid-context-{index}", context=context
            ),
        )
    source = c.root / c.context["sources"][0]["path"]
    raw = source.read_bytes()
    source.write_bytes(raw + b"\r\nA changed source byte.")
    refuse(c, lambda: generate(c, "changed-source-file"))
    source.write_bytes(raw)
    assert not c.store.list_by(wing=c.wing, room="ideation-calendars", limit=None)


def test_a07_scoped_capabilities_foreign_refs_and_readonly_export(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant
    from cairntir.memory.store import DrawerStore

    c = case
    first = generate(c)
    scope = [{"wing": c.wing, "rooms": ["ideation-calendars"]}]
    entry = oracle.entries(first)[0][1]
    for capabilities in (["read"], ["write"], ["read", "export"]):
        token = issue_grant(c.store, scopes=scope, capabilities=capabilities)
        before = snapshot(c.db)
        with pytest.raises(AccessDenied):
            generate(c, "scope-" + "-".join(capabilities), store=bind_grant(c.store, token))
        assert snapshot(c.db) == before
    token = issue_grant(c.store, scopes=scope, capabilities=["read", "write"])
    scoped = bind_grant(c.store, token)
    scoped_generated = generate(c, "positive-scoped-generation", store=scoped)
    oracle.check_view(scoped_generated, c.context, c.policy)
    oracle.check_base_collision(scoped_generated)
    assert get(c, scoped_generated["ref"]) == scoped_generated
    second = revise(
        c, first, [{"entry_id": entry["entry_id"], "notes": "A scoped human note."}], store=scoped
    )
    oracle.check_lineage(first, second)
    foreign = dict(second["ref"], wing="untouched-project")
    before = snapshot(c.db)
    with pytest.raises((AccessDenied, api().CalendarError)):
        api().get_calendar(scoped, foreign)
    assert snapshot(c.db) == before
    read = issue_grant(c.store, scopes=scope, capabilities=["read"])
    export = issue_grant(c.store, scopes=scope, capabilities=["read", "export"])
    before = snapshot(c.db)
    vault = c.tmp / "readonly-export"
    vault.mkdir()
    with DrawerStore(c.db, c.embeddings, read_only=True) as readonly:
        assert (
            api().get_calendar(bind_grant(readonly, read), second["ref"], source_root=c.root)["ref"]
            == second["ref"]
        )
        with pytest.raises(AccessDenied):
            api().project_calendar(
                bind_grant(readonly, read), second["ref"], vault_path=vault, source_root=c.root
            )
        assert not list(vault.rglob("*"))
        result = api().project_calendar(
            bind_grant(readonly, export), second["ref"], vault_path=vault, source_root=c.root
        )
        oracle.check_projection(result["projection"], vault)
    assert snapshot(c.db) == before


def test_a08_hidden_successor_prevents_owner_and_scoped_stale_branches(case):
    from cairntir.access import AccessDenied, bind_grant, issue_grant
    from cairntir.memory.taxonomy import Drawer
    from cairntir.provenance import WriteProvenance

    c = case
    first = generate(c)
    hidden_content = "Private successor text must not be disclosed."
    expired = WriteProvenance.create(
        host="i04-independent-fixture",
        capture_path="sdk",
        session_id="expired-hidden-successor",
        valid_from=datetime(2000, 1, 1, tzinfo=UTC),
        valid_until=datetime(2001, 1, 1, tzinfo=UTC),
    )
    c.store.add(
        Drawer(
            wing=c.wing,
            room="private-successor",
            content=hidden_content,
            supersedes_id=first["ref"]["drawer_id"],
        ),
        provenance=expired,
    )
    token = issue_grant(
        c.store,
        scopes=[{"wing": c.wing, "rooms": ["ideation-calendars"]}],
        capabilities=["read", "write"],
    )
    changes = [
        {
            "entry_id": oracle.entries(first)[0][1]["entry_id"],
            "notes": "A stale branch must not be committed.",
        }
    ]
    for index, store in enumerate((c.store, bind_grant(c.store, token))):
        before = snapshot(c.db)
        with pytest.raises((api().CalendarError, AccessDenied)) as caught:
            revise(c, first, changes, key=f"hidden-successor-{index}", store=store)
        assert hidden_content not in str(caught.value)
        assert snapshot(c.db) == before
    assert get(c, first["ref"]) == first


def test_a09_forged_refs_and_changed_saved_body_cannot_be_reopened(case):
    c = case
    first = generate(c)
    for field, value in (
        ("portable_identity", "00000000-0000-0000-0000-000000000000"),
        ("content_sha256", "0" * 64),
        ("room", "foreign-room"),
        ("wing", "untouched-project"),
    ):
        ref = dict(first["ref"], **{field: value})
        refuse(c, lambda ref=ref: get(c, ref))
    with sqlite3.connect(c.db) as conn:
        conn.execute("UPDATE drawers SET content=? WHERE id=?", ("{}", first["ref"]["drawer_id"]))
    refuse(c, lambda: get(c, first["ref"]))


def test_a10_projection_links_human_bytes_revisions_and_downgrade_refusal(case):
    c = case
    first = generate(c)
    vault = c.tmp / "vault"
    vault.mkdir()
    human = vault / "human.md"
    human_bytes = b"# Human note\r\nKeep spacing, CRLF and trailing bytes.  \r\n"
    human.write_bytes(human_bytes)
    projected = api().project_calendar(c.store, first["ref"], vault_path=vault, source_root=c.root)
    oracle.check_projection(projected["projection"], vault)
    calendar_path = vault / projected["projection"]["calendar_path"]
    existing = calendar_path.read_bytes()
    assert existing.count(b"<!-- cairntir:calendar:begin -->") == 1
    assert existing.count(b"<!-- cairntir:calendar:end -->") == 1
    prefix = "Human introduction — retain exact bytes.\r\n\r\n".encode()
    suffix = b"\r\n\r\nHuman trailing notes.  \r\n"
    calendar_path.write_bytes(prefix + existing + suffix)
    immutable_before = {
        p: (vault / p).read_bytes()
        for p in projected["projection"]["paths"]
        if p != projected["projection"]["calendar_path"]
    }
    second = revise(
        c,
        first,
        [
            {
                "entry_id": oracle.entries(first)[0][1]["entry_id"],
                "notes": "Visible revised planning note.",
            }
        ],
    )
    revised = api().project_calendar(c.store, second["ref"], vault_path=vault, source_root=c.root)
    oracle.check_projection(revised["projection"], vault)
    assert revised["projection"]["calendar_path"] == projected["projection"]["calendar_path"]
    current = calendar_path.read_bytes()
    assert current.startswith(prefix) and current.endswith(suffix)
    oracle.check_human_bytes(human, human_bytes)
    assert all((vault / p).read_bytes() == data for p, data in immutable_before.items())
    source_path = vault / revised["projection"]["source_paths"][0]
    source_before = source_path.read_bytes()
    source_path.write_bytes(source_before + b"\n[[MissingGeneratedTarget]]\n")
    with pytest.raises(AssertionError):
        oracle.check_projection(revised["projection"], vault)
    source_path.write_bytes(source_before)
    human.write_bytes(human_bytes + b"Unwanted rewrite")
    with pytest.raises(AssertionError):
        oracle.check_human_bytes(human, human_bytes)
    human.write_bytes(human_bytes)
    filesystem_before = {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    refuse(
        c,
        lambda: api().project_calendar(c.store, first["ref"], vault_path=vault, source_root=c.root),
    )
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == filesystem_before
    changed = current.replace(
        b"<!-- cairntir:calendar:begin -->",
        b"<!-- cairntir:calendar:begin -->\nUnexpected generated-block edit.",
        1,
    )
    calendar_path.write_bytes(changed)
    filesystem_before = {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    refuse(
        c,
        lambda: api().project_calendar(
            c.store, second["ref"], vault_path=vault, source_root=c.root
        ),
    )
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == filesystem_before


def test_a11_conflicting_generation_key_and_flex_collision_are_visible(case):
    c = case
    first = generate(c)
    changed_policy = dict(c.policy, daily_capacity=2)
    refuse(c, lambda: generate(c, policy=changed_policy))
    friday = next(item for date, item in oracle.entries(first) if date == "2026-11-06")
    revised = revise(c, first, [{"entry_id": friday["entry_id"], "date": "2026-11-08"}])
    collisions = [
        row
        for row in revised["collisions"]
        if row["kind"] == "flex" and row["date"] == "2026-11-08"
    ]
    assert len(collisions) == 1 and friday["entry_id"] in collisions[0]["entry_ids"]
    assert revised["context"]["human_confirmation"] is False
    assert revised["context"]["attribution"] == "historical_record_unverified"
    assert revised["policy"]["publication_policy"] == "planning_only_no_external_publish"


def test_a12_canonical_i03_graph_is_publicly_generated_and_stays_provisional(case):
    c = case
    i03_root = c.tmp / "canonical-source"
    shutil.copytree(HERE / "i03_fixture" / "sources", i03_root)
    channel_set = factory.create_channel_graph(c.store, c.wing, i03_root)
    policy = copy.deepcopy(c.policy)
    policy["weekly_slots"] = [
        {
            "id": "monday-original",
            "weekday": 0,
            "hook_cycle": ["community-discussion"],
            "title_by_hook": {
                "community-discussion": (
                    "Plan a discussion about reviewing synthetic notebook observations"
                )
            },
            "cta_by_hook": {
                "community-discussion": (
                    "Describe evidence that would help review a mock notebook observation."
                )
            },
        },
        {
            "id": "wednesday-repurpose",
            "weekday": 2,
            "repurpose_from_slot": "monday-original",
            "source_offset_days": -2,
            "hook_map": {"community-discussion": "newsletter"},
            "title_by_hook": {
                "newsletter": (
                    "Adapt Monday's mock notebook discussion into a short explanatory note"
                )
            },
            "cta_by_hook": {
                "newsletter": "Reply with a counterexample a mock observation should survive."
            },
        },
        {
            "id": "friday-video",
            "weekday": 4,
            "hook_cycle": ["short-video"],
            "title_by_hook": {
                "short-video": "Plan a short explanation of a provisional mock notebook review"
            },
            "cta_by_hook": {
                "short-video": "Name one mock notebook pattern to keep provisional pending review."
            },
        },
    ]
    result = generate(
        c,
        "canonical-calendar",
        context={"kind": "i03", "ref": channel_set["ref"]},
        policy=policy,
        source_root=i03_root,
    )
    assert result["context"]["kind"] == "i03"
    assert result["context"]["ref"] == channel_set["ref"]
    assert result["context"]["attribution"] == "historical_record_unverified"
    assert result["context"]["human_confirmation"] is False
    assert [day["date"] for day in result["days"]] == list(oracle.DATES)
    assert len(oracle.entries(result)) == 13
    known = {item["channel_id"]: item for item in channel_set["adaptations"]}
    for _, item in oracle.entries(result):
        adaptation = known[item["hook_id"]]
        assert item["idea_id"] == "synthetic-i03-notebook-idea"
        assert (
            item["channel"] == adaptation["channel_id"]
            and item["format"] == adaptation["format_id"]
        )
    before = snapshot(c.db)
    reopened = api().get_calendar(c.store, result["ref"], source_root=i03_root)
    assert reopened == result and snapshot(c.db) == before
    bad = {"kind": "i03", "ref": dict(channel_set["ref"], content_sha256="0" * 64)}
    refuse(
        c, lambda: generate(c, "forged-upstream", context=bad, policy=policy, source_root=i03_root)
    )


def test_a13_caller_owned_transactions_refuse_before_work(case):
    c = case
    with c.store.transaction():
        refuse(c, lambda: generate(c, "inside-caller-transaction"))
    first = generate(c)
    changes = [
        {"entry_id": oracle.entries(first)[0][1]["entry_id"], "notes": "No nested edit commit."}
    ]
    with c.store.transaction():
        refuse(c, lambda: revise(c, first, changes))


def test_a14_independent_connections_racing_one_parent_commit_one_successor(case):
    from cairntir.memory.embeddings import HashEmbeddingProvider
    from cairntir.memory.store import DrawerStore

    c = case
    first = generate(c)
    entry_id = oracle.entries(first)[0][1]["entry_id"]
    barrier = threading.Barrier(2, timeout=10)
    outcomes = queue.Queue()

    def writer(label):
        try:
            with DrawerStore(c.db, HashEmbeddingProvider(dimension=32)) as own_store:
                before = api().get_calendar(own_store, first["ref"], source_root=c.root)
                assert before == first
                barrier.wait()
                try:
                    result = api().revise_calendar(
                        own_store,
                        first["ref"],
                        expected_revision=first["revision"],
                        changes=[{"entry_id": entry_id, "notes": f"Concurrent editor {label}."}],
                        idempotency_key=f"race-editor-{label}",
                        source_root=c.root,
                    )
                    outcomes.put(("success", result))
                except api().CalendarError as exc:
                    outcomes.put(("refused", exc.code))
        except BaseException as exc:  # noqa: BLE001 - Surface every worker failure in outcomes.
            barrier.abort()
            outcomes.put(("unexpected", repr(exc)))

    threads = [threading.Thread(target=writer, args=(label,), daemon=True) for label in ("a", "b")]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 30
    for thread in threads:
        thread.join(timeout=max(0, deadline - time.monotonic()))
    assert not any(thread.is_alive() for thread in threads), "bounded race did not finish"
    observed = [outcomes.get_nowait() for _ in range(outcomes.qsize())]
    assert len(observed) == 2 and sorted(kind for kind, _ in observed) == ["refused", "success"], (
        observed
    )
    winner = next(value for kind, value in observed if kind == "success")
    assert next(value for kind, value in observed if kind == "refused") in {
        "CONFLICT",
        "STALE_REVISION",
    }
    oracle.check_lineage(first, winner)
    children = [
        row
        for row in c.store.list_by(
            wing=c.wing, room="ideation-calendars", limit=None, include_expired=True
        )
        if row.supersedes_id == first["ref"]["drawer_id"]
    ]
    assert len(children) == 1 and children[0].id == winner["ref"]["drawer_id"]
    assert get(c, first["ref"]) == first
    assert get(c, winner["ref"]) == winner
