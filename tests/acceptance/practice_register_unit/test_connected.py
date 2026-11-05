"""Independent R17 connected-register acceptance; freeze before candidate execution."""

from __future__ import annotations

import hashlib
import json
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import codeglass
from cairntir import procedures as api
from cairntir.access import (
    AccessDenied,
    ScopedStore,
    bind_grant,
    issue_grant,
    revoke_grant,
)
from cairntir.errors import ProjectionError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian
from cairntir.provenance import Sensitivity, WriteProvenance
from cairntir.reason.model import Experiment, Outcome

WING = "r17-register-proof"
AS_OF = "2026-04-01"
EVALUATOR = "r17-local/v1"
BEGIN = "<!-- cairntir:generated:begin -->"
END = "<!-- cairntir:generated:end -->"


@pytest.fixture(autouse=True)
def offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOME", "USERPROFILE", "CAIRNTIR_HOME", "XDG_CACHE_HOME", "HF_HOME"):
        target = tmp_path / name.lower()
        target.mkdir()
        monkeypatch.setenv(name, str(target))
    for name in (
        "CAIRNTIR_DISABLE_AUTOREGISTER",
        "CAIRNTIR_DISABLE_UPDATE_CHECK",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):
        monkeypatch.setenv(name, "1")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("R17 fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class InertRunner:
    def run(self, hypothesis: object) -> Outcome:
        passed = "candidate" in json.loads(hypothesis.claim)["steps"]
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="local inert R17 case"),
            observed="pass" if passed else "baseline",
            success=passed,
            delta="" if passed else "known baseline",
        )


def bundle(tmp_path: Path, *, source_provenance: WriteProvenance | None = None) -> SimpleNamespace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "register.db"
    store = DrawerStore(path, HashEmbeddingProvider(dimension=16))
    development = store.add(
        Drawer(wing=WING, room="cases", content="R17_SOURCE_SENTINEL: development evidence"),
        provenance=source_provenance,
    )
    holdouts = [
        store.add(Drawer(wing=WING, room="cases", content=f"independent holdout {index}"))
        for index in (1, 2)
    ]
    assert development.id is not None and all(item.id is not None for item in holdouts)
    manifest = api.EvaluationManifest(
        EVALUATOR,
        ("baseline",),
        tuple(
            api.HoldoutCase(f"holdout-{index}", item.id, "pass")
            for index, item in enumerate(holdouts, 1)
        ),
    )
    book = api.ProcedureBook(
        store,
        {EVALUATOR: api.RegisteredEvaluation(manifest, InertRunner())},
        operator_approval=lambda _request: True,
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return SimpleNamespace(path=path, store=store, book=book, source_id=development.id, vault=vault)


def spec(
    b: SimpleNamespace, title: str, *, owner: str | None, version: str = "1", due: str = AS_OF
) -> api.ProcedureSpec:
    governance = (
        None
        if owner is None
        else api.PracticeGovernance(owner, version, f"{title} rationale v{version}", due)
    )
    return api.ProcedureSpec(
        title,
        ("local input",),
        "R17 acceptance case",
        ("candidate",),
        "pass",
        ("return to source",),
        (b.source_id,),
        governance=governance,
    )


def promote(b: SimpleNamespace, value: api.ProcedureSpec) -> api.Procedure:
    candidate = b.book.propose(wing=WING, spec=value)
    return promote_candidate(b, candidate)


def promote_candidate(b: SimpleNamespace, candidate: api.Procedure) -> api.Procedure:
    evaluation = b.book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
    assert evaluation.passed is True
    return b.book.promote(evaluation.current_id, evaluation_id=evaluation.drawer_id)


def seed(b: SimpleNamespace) -> SimpleNamespace:
    first = promote(b, spec(b, "Alpha practice", owner="Alpha owner"))
    second = promote(b, spec(b, "Beta practice", owner="Beta owner", due="2026-05-01"))
    legacy = promote(b, spec(b, "Legacy practice", owner=None))
    previous_pending = promote(b, spec(b, "Pending practice", owner="Pending owner"))
    pending = b.book.revise(
        previous_pending.drawer_id,
        spec=spec(b, "Pending practice", owner="Pending new owner", version="2"),
    )
    previous_withdrawn = promote(b, spec(b, "Withdrawn practice", owner="Former owner"))
    withdrawn = b.book.rollback(previous_withdrawn.drawer_id, reason="withdrawal acceptance")
    return SimpleNamespace(
        first=first, second=second, legacy=legacy, pending=pending, withdrawn=withdrawn
    )


def snapshot(store: DrawerStore | ScopedStore, *, as_of: str = AS_OF) -> object:
    builder = getattr(codeglass, "build_practice_register", None)
    assert callable(builder), "R17_PUBLIC_API_MISSING: build_practice_register"
    return builder(store, wing=WING, as_of=as_of)


def rows(value: object) -> dict[str, object]:
    assert value.wing == WING and re.fullmatch(r"\d{4}-\d\d-\d\d", value.as_of)
    assert isinstance(value.rows, tuple)
    result = {item.title: item for item in value.rows}
    assert len(result) == len(value.rows), "distinct families were collapsed"
    return result


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def metadata_hash(value: dict[str, object]) -> str:
    return digest(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def durable_state(store: DrawerStore) -> tuple[object, ...]:
    """Ignore existing read-access counters, but detect new or changed evidence."""
    queries = (
        "SELECT id,wing,room,content,layer,metadata,created_at,claim,predicted_outcome,"
        "observed_outcome,delta,supersedes_id,belief_mass,trust,valid_until,provenance "
        "FROM drawers ORDER BY id",
        "SELECT drawer_id,root_id,parent_id,payload FROM procedure_records ORDER BY drawer_id",
        "SELECT drawer_id,payload FROM procedure_evaluations ORDER BY drawer_id",
    )
    return tuple(tuple(tuple(row) for row in store._conn.execute(query)) for query in queries)


def raw_drawer_state(store: DrawerStore) -> tuple[object, ...]:
    return tuple(tuple(row) for row in store._conn.execute("SELECT * FROM drawers ORDER BY id"))


def assert_history(row: object, b: SimpleNamespace) -> None:
    expected = b.book.history(row.current_id)
    assert row.root_id == expected[0].drawer_id
    assert [item.drawer_id for item in row.history] == [item.drawer_id for item in expected]
    for actual, registered in zip(row.history, expected, strict=True):
        original = b.store.get(actual.drawer_id)
        assert original is not None
        assert actual.supersedes_id == registered.supersedes_id
        assert actual.state == registered.state
        assert actual.revision_sha256 == registered.revision_sha256
        assert actual.content == original.content
        assert actual.content_sha256 == digest(original.content.encode("utf-8"))
        assert actual.metadata_sha256 == metadata_hash(original.metadata)


def generated(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    assert text.count(BEGIN) == text.count(END) == 1
    return text.split(BEGIN, 1)[1].split(END, 1)[0]


def publish(
    b: SimpleNamespace, *, store: DrawerStore | ScopedStore | None = None, as_of: str = AS_OF
) -> object:
    result = project_to_obsidian(
        store or b.store,
        vault=b.vault,
        wing=WING,
        practice_register=True,
        as_of=as_of,
    )
    assert result.practice_register_status == "published"
    assert result.practice_register_note is not None
    assert result.practice_register_note.is_file()
    assert result.practice_register_note.resolve().is_relative_to(b.vault.resolve())
    return result


def assert_links(b: SimpleNamespace, projection: object, value: object) -> None:
    register = generated(projection.practice_register_note)
    for row in value.rows:
        summary_lines = [line for line in register.splitlines() if row.title in line]
        assert len(summary_lines) == 1, row.title
        assert f"`{row.status}`" in summary_lines[0], row.title
    notes = tuple(projection.practice_history_notes)
    assert notes
    targets = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", register)
    for target in targets:
        if target.startswith("cairntir-sync/"):
            assert (b.vault / f"{target}.md").is_file(), target
    for note in notes:
        assert note.is_file() and note.resolve().is_relative_to(b.vault.resolve())
        assert note.relative_to(b.vault).with_suffix("").as_posix() in targets
    rendered = [generated(note) for note in notes]
    for row in value.rows:
        for revision in row.history:
            assert any(revision.content in text for text in rendered), revision.drawer_id


def test_01_status_scope_and_real_markdown(tmp_path: Path) -> None:
    b = bundle(tmp_path)
    try:
        created = seed(b)
        before_snapshot = b.store._conn.total_changes
        value = snapshot(b.store)
        assert b.store._conn.total_changes == before_snapshot
        found = rows(value)
        assert set(found) == {
            "Alpha practice",
            "Beta practice",
            "Legacy practice",
            "Pending practice",
            "Withdrawn practice",
        }
        assert found["Alpha practice"].status == found["Beta practice"].status == "active"
        assert found["Legacy practice"].status == "active_governance_incomplete"
        assert found["Pending practice"].status == "pending"
        assert found["Pending practice"].current_id == created.pending.drawer_id
        assert found["Withdrawn practice"].status == "withdrawn"
        for row in found.values():
            assert_history(row, b)
            assert_current_status(row, b)
        legacy = found["Legacy practice"]
        assert (
            legacy.owner,
            legacy.version,
            legacy.rationale,
            legacy.review_due,
            legacy.due,
            legacy.review_id,
        ) == (None,) * 6
        before_projection = b.store._conn.total_changes
        result = publish(b)
        assert b.store._conn.total_changes == before_projection
        assert_links(b, result, value)
        body = generated(result.practice_register_note)
        assert "governance incomplete" in body.lower()
        assert "revise" in body.lower()
        assert "pending" in body.lower() and "withdrawn" in body.lower()
        assert "Alpha owner" in body and "Beta owner" in body
        assert "2026-05-01" in body and "2026-04-01" in body

        token = issue_grant(b.store, scopes=[{"wing": WING}], capabilities=["read"])
        scoped = bind_grant(b.store, token)
        assert rows(snapshot(scoped)) == found
        assert publish(b, store=scoped).practice_register_status == "published"
    finally:
        b.store.close()


def test_02_replacement_then_legacy_opt_in(tmp_path: Path) -> None:
    b = bundle(tmp_path)
    try:
        created = seed(b)
        first = b.store.get(created.first.drawer_id)
        assert first is not None
        original = (first.content, metadata_hash(first.metadata))
        proposed = b.book.revise(
            created.first.drawer_id,
            spec=spec(b, "Alpha practice", owner="New Alpha owner", version="2", due="2026-08-01"),
        )
        before = rows(snapshot(b.store))["Alpha practice"]
        assert before.status == "pending" and before.current_id == proposed.drawer_id
        assert before.owner != "Alpha owner"
        current = promote_candidate(b, proposed)
        after = rows(snapshot(b.store))["Alpha practice"]
        assert after.status == "active" and after.current_id == current.drawer_id
        assert (after.owner, after.version, after.rationale, after.review_due) == (
            "New Alpha owner",
            "2",
            "Alpha practice rationale v2",
            "2026-08-01",
        )
        assert_history(after, b)
        assert any(
            item.drawer_id == created.first.drawer_id
            and (item.content, item.metadata_sha256) == original
            for item in after.history
        )

        still_legacy = rows(snapshot(b.store))["Legacy practice"]
        assert still_legacy.status == "active_governance_incomplete"
        opt_in = b.book.revise(
            created.legacy.drawer_id,
            spec=spec(
                b, "Legacy practice", owner="Named legacy owner", version="1", due="2026-09-01"
            ),
        )
        assert rows(snapshot(b.store))["Legacy practice"].status == "pending"
        converted = promote_candidate(b, opt_in)
        final = snapshot(b.store)
        final_rows = rows(final)
        assert final_rows["Legacy practice"].status == "active"
        assert final_rows["Legacy practice"].current_id == converted.drawer_id
        assert all(row.status != "active_governance_incomplete" for row in final.rows)
        assert all(
            row.owner and row.version and row.rationale and row.review_due
            for row in final.rows
            if row.status == "active"
        )
        result = publish(b)
        assert_links(b, result, final)
        assert "Named legacy owner" in generated(result.practice_register_note)

        b.store.close()
        with DrawerStore(b.path, HashEmbeddingProvider(dimension=16)) as reopened:
            revisited = snapshot(reopened)
            old = reopened.get(created.first.drawer_id)
            assert old is not None and (old.content, metadata_hash(old.metadata)) == original
            assert [(r.title, r.current_id, r.status) for r in revisited.rows] == [
                (r.title, r.current_id, r.status) for r in final.rows
            ]
            assert_links(
                SimpleNamespace(
                    **{**vars(b), "store": reopened, "book": api.ProcedureBook(reopened, {})}
                ),
                publish(b, store=reopened),
                revisited,
            )
    finally:
        b.store.close()


def test_03_review_receipt_changes_only_current_revision_due(tmp_path: Path) -> None:
    b = bundle(tmp_path)
    try:
        first = promote(b, spec(b, "Reviewed practice", owner="Review owner"))
        before = rows(snapshot(b.store, as_of="2026-03-31"))["Reviewed practice"]
        due = rows(snapshot(b.store))["Reviewed practice"]
        assert before.due is False and due.due is True
        assert before.review_id is due.review_id is None
        assert "Reviewed practice" in generated(publish(b).practice_register_note)

        assessment = b.book.assess_review(
            first.drawer_id,
            period_start="2026-01-01",
            period_end="2026-05-01",
            as_of=AS_OF,
            policy=api.PracticeReviewPolicy(minimum_observations=1, minimum_trigger_rate=0.5),
        )
        receipt = b.book.complete_review(
            first.drawer_id,
            assessment=assessment,
            reviewer="Actual reviewer",
            decision="retain",
            rationale="Review evidence examined",
            next_review_due="2026-07-01",
        )
        reviewed = rows(snapshot(b.store, as_of="2026-04-02"))["Reviewed practice"]
        assert reviewed.review_id == receipt.drawer_id
        assert reviewed.review_due == "2026-07-01" and reviewed.due is False
        assert b.book.get_review(reviewed.review_id) == receipt
        projection = publish(b, as_of="2026-04-02")
        body = generated(projection.practice_register_note)
        review_link = f"cairntir-sync/receipts/drawer-{receipt.drawer_id}"
        assert re.search(r"\[\[" + re.escape(review_link) + r"(?:\|[^\]]*)?\]\]", body)
        assert (b.vault / f"{review_link}.md").is_file()

        replacement = b.book.revise(
            first.drawer_id,
            spec=spec(b, "Reviewed practice", owner="Next reviewer", version="2", due="2026-05-01"),
        )
        current = promote_candidate(b, replacement)
        fresh = rows(snapshot(b.store, as_of="2026-06-01"))["Reviewed practice"]
        assert fresh.current_id == current.drawer_id
        assert fresh.review_id is None and fresh.review_due == "2026-05-01" and fresh.due is True
    finally:
        b.store.close()


def test_04_refresh_human_notes_and_broken_markers(tmp_path: Path) -> None:
    b = bundle(tmp_path)
    try:
        first = promote(b, spec(b, "Human note practice", owner="Human owner"))
        projected = publish(b)
        history = projected.practice_history_notes[0]
        for note in (projected.practice_register_note, history):
            note.write_text(
                note.read_text(encoding="utf-8") + "\nPERSONAL_R17_NOTE survives\n",
                encoding="utf-8",
            )
        replacement = b.book.revise(
            first.drawer_id, spec=spec(b, "Human note practice", owner="Later owner", version="2")
        )
        promote_candidate(b, replacement)
        for _ in range(2):
            updated = publish(b)
            assert "Later owner" in generated(updated.practice_register_note)
            for note in (updated.practice_register_note, history):
                assert note.read_text(encoding="utf-8").count("PERSONAL_R17_NOTE survives") == 1
        register = updated.practice_register_note
        register.write_text("This is a user-owned replacement without markers.\n", encoding="utf-8")
        with pytest.raises(ProjectionError):
            project_to_obsidian(
                b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
            )
        assert (
            register.read_text(encoding="utf-8")
            == "This is a user-owned replacement without markers.\n"
        )
    finally:
        b.store.close()


def test_05_unavailable_scope_sources_and_stale_output(tmp_path: Path) -> None:
    b = bundle(tmp_path / "ordinary")
    try:
        promote(b, spec(b, "Visible current practice", owner="Visible owner"))
        complete = issue_grant(b.store, scopes=[{"wing": WING}], capabilities=["read"])
        scoped = bind_grant(b.store, complete)
        published = publish(b, store=scoped)
        assert "Visible current practice" in generated(published.practice_register_note)
        published.practice_register_note.write_text(
            published.practice_register_note.read_text(encoding="utf-8")
            + "\nPERSONAL_PRIVATE_NOTE\n",
            encoding="utf-8",
        )
        before_state = durable_state(b.store)
        revoke_grant(b.store, complete)
        assert durable_state(b.store) == before_state
        unavailable = project_to_obsidian(
            scoped, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert unavailable.practice_register_status == "unavailable"
        assert "Visible current practice" not in generated(published.practice_register_note)
        assert "PERSONAL_PRIVATE_NOTE" in published.practice_register_note.read_text(
            encoding="utf-8"
        )
        assert not re.search(r"drawer-\d+|Drawer #\d+", generated(published.practice_register_note))
        for note in published.practice_history_notes:
            assert "Visible current practice" not in generated(note)
        assert durable_state(b.store) == before_state

        limited = bind_grant(
            b.store,
            issue_grant(
                b.store, scopes=[{"wing": WING, "rooms": ["discoveries"]}], capabilities=["read"]
            ),
        )
        with pytest.raises(AccessDenied) as denied:
            snapshot(limited)
        assert str(b.source_id) not in str(denied.value)
        assert durable_state(b.store) == before_state
        builder = codeglass.build_practice_register
        with pytest.raises((ValueError, ProjectionError)):
            builder(b.store, wing="", as_of=AS_OF)
        absent_vault = tmp_path / "absent-wing-vault"
        (absent_vault / ".obsidian").mkdir(parents=True)
        with pytest.raises((ValueError, ProjectionError)) as absent:
            project_to_obsidian(b.store, vault=absent_vault, practice_register=True, as_of=AS_OF)
        assert str(b.source_id) not in str(absent.value)
        assert not (absent_vault / "cairntir-sync").exists()
        assert durable_state(b.store) == before_state
    finally:
        b.store.close()

    for source_state in ("secret", "expired", "missing", "denied"):
        case = tmp_path / source_state
        case.mkdir()
        provenance = None
        if source_state == "secret":
            provenance = WriteProvenance.create(
                host="r17-fixture", capture_path="acceptance", sensitivity=Sensitivity.SECRET
            )
        elif source_state == "expired":
            provenance = WriteProvenance.create(
                host="r17-fixture",
                capture_path="acceptance",
                valid_until=datetime(2025, 1, 1, tzinfo=UTC),
            )
        item = bundle(case, source_provenance=provenance)
        try:
            promote(item, spec(item, f"Hidden {source_state} practice", owner="Hidden owner"))
            target_store: DrawerStore | ScopedStore = item.store
            if source_state == "missing":
                with item.store._conn:
                    item.store._conn.execute(
                        "DELETE FROM embedding_chunks WHERE drawer_id = ?", (item.source_id,)
                    )
                    item.store._conn.execute(
                        "DELETE FROM portable_records WHERE drawer_id = ?", (item.source_id,)
                    )
                    item.store._conn.execute("DELETE FROM drawers WHERE id = ?", (item.source_id,))
                assert item.store._read_drawer(item.source_id) is None
                assert not item.store._conn.execute("PRAGMA foreign_key_check").fetchall()
            elif source_state == "denied":
                token = issue_grant(
                    item.store,
                    scopes=[{"wing": WING, "rooms": ["discoveries"]}],
                    capabilities=["read"],
                )
                target_store = bind_grant(item.store, token)
            before = durable_state(item.store)
            result = project_to_obsidian(
                target_store, vault=item.vault, wing=WING, practice_register=True, as_of=AS_OF
            )
            assert result.practice_register_status == "unavailable"
            assert durable_state(item.store) == before
            if result.practice_register_note is not None:
                text = generated(result.practice_register_note)
                assert "unavailable" in text.lower()
                assert f"Hidden {source_state} practice" not in text
                assert "R17_SOURCE_SENTINEL" not in text
                assert f"drawer-{item.source_id}" not in text
                assert not re.search(r"drawer-\d+|Drawer #\d+", text)
        finally:
            item.store.close()


def test_06_cli_publication_path_and_store_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from cairntir import cli

    b = bundle(tmp_path)
    try:
        promote(b, spec(b, "CLI practice", owner="CLI owner"))
        before = durable_state(b.store)
        before_drawers = raw_drawer_state(b.store)
        monkeypatch.setattr(cli, "_open_store", lambda **_kwargs: b.store)
        result = CliRunner().invoke(
            cli.app, ["obsidian-project", str(b.vault), "--wing", WING, "--practice-register"]
        )
        assert result.exit_code == 0, result.output
        assert "cairntir-sync" in result.output and "practice" in result.output.lower()
        with DrawerStore(b.path, HashEmbeddingProvider(dimension=16)) as reopened:
            assert durable_state(reopened) == before
            assert raw_drawer_state(reopened) == before_drawers
        assert any((b.vault / "cairntir-sync").rglob("*.md"))
    finally:
        b.store.close()


def test_07_mutation_controls_reject_lost_history_and_false_current(tmp_path: Path) -> None:
    b = bundle(tmp_path)
    try:
        seed(b)
        value = snapshot(b.store)
        found = rows(value)
        projected = publish(b)
        assert_links(b, projected, value)

        original_revision = found["Alpha practice"].history[0]
        history_note = next(
            note
            for note in projected.practice_history_notes
            if original_revision.content in generated(note)
        )
        history_text = history_note.read_text(encoding="utf-8")
        history_note.write_text(
            history_text.replace(original_revision.content, "[TRUNCATED HISTORY]", 1),
            encoding="utf-8",
        )
        with pytest.raises(AssertionError):
            assert_links(b, projected, value)
        history_note.write_text(history_text, encoding="utf-8")

        register_note = projected.practice_register_note
        original_register = register_note.read_text(encoding="utf-8")
        lines = original_register.splitlines(keepends=True)
        matches = [
            index
            for index, line in enumerate(lines)
            if "Pending practice" in line and "`pending`" in line
        ]
        assert len(matches) == 1
        lines[matches[0]] = lines[matches[0]].replace("`pending`", "`active`", 1)
        register_note.write_text("".join(lines), encoding="utf-8")
        with pytest.raises(AssertionError):
            assert_links(b, projected, value)
        register_note.write_text(original_register, encoding="utf-8")
        assert_links(b, projected, value)
    finally:
        b.store.close()


def assert_current_status(row: object, b: SimpleNamespace) -> None:
    current = next(
        item
        for item in b.book.list(wing=WING, active_only=False)
        if item.drawer_id == row.current_id
    )
    expected = (
        "active_governance_incomplete"
        if current.state == "promoted" and current.spec.governance is None
        else "active"
        if current.state == "promoted"
        else "withdrawn"
        if current.state in {"expired", "rejected"}
        else "pending"
    )
    assert row.status == expected
    governance = current.spec.governance
    assert row.version == (governance.version if governance is not None else None)
