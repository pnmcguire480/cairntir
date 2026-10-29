"""Independent R19 acceptance; freeze before product implementation."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import codeglass, procedures
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian
from cairntir.provenance import Sensitivity, WriteProvenance
from cairntir.reason.model import Experiment, Outcome

WING = "r19-conflict-proof"
AS_OF = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
EVALUATOR = "r19-inert-local/v1"
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
        pytest.fail("R19 acceptance attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class InertRunner:
    def run(self, hypothesis: object) -> Outcome:
        passed = "candidate" in json.loads(hypothesis.claim)["steps"]
        return Outcome(
            experiment=Experiment(hypothesis=hypothesis, description="synthetic R19 holdout"),
            observed="pass" if passed else "baseline",
            success=passed,
            delta="" if passed else "known baseline",
        )


def seed(tmp_path: Path) -> SimpleNamespace:
    store = DrawerStore(tmp_path / "conflicts.db", HashEmbeddingProvider(dimension=16))
    first_source = store.add(
        Drawer(wing=WING, room="sources", content="SIMULATED rule source: use Postgres")
    )
    second_source = store.add(
        Drawer(wing=WING, room="sources", content="SIMULATED rule source: use SQLite")
    )
    conflict_source = store.add(
        Drawer(
            wing=WING,
            room="sources",
            content="SIMULATED conflict: Postgres and SQLite instructions disagree",
        )
    )
    holdouts = [
        store.add(Drawer(wing=WING, room="sources", content=f"independent holdout {n}"))
        for n in (1, 2)
    ]
    assert all(
        item.id is not None for item in (first_source, second_source, conflict_source, *holdouts)
    )
    manifest = procedures.EvaluationManifest(
        EVALUATOR,
        ("baseline",),
        tuple(
            procedures.HoldoutCase(f"holdout-{n}", item.id, "pass")
            for n, item in enumerate(holdouts, 1)
        ),
    )
    book = procedures.ProcedureBook(
        store,
        {EVALUATOR: procedures.RegisteredEvaluation(manifest, InertRunner())},
        operator_approval=lambda _request: True,
    )

    def promoted(title: str, source_id: int, instruction: str) -> procedures.Procedure:
        spec = procedures.ProcedureSpec(
            title,
            ("local datastore choice",),
            "SIMULATED database choice",
            ("candidate", instruction),
            "one datastore selected",
            ("return to prior choice",),
            (source_id,),
            governance=procedures.PracticeGovernance(
                "synthetic owner", "1", "R19 conflict fixture", "2026-05-01"
            ),
        )
        candidate = book.propose(wing=WING, spec=spec)
        receipt = book.evaluate(candidate.drawer_id, evaluator_id=EVALUATOR)
        assert receipt.passed
        return book.promote(receipt.current_id, evaluation_id=receipt.drawer_id)

    first = promoted("Postgres guidance", first_source.id, "use Postgres")
    second = promoted("SQLite guidance", second_source.id, "use SQLite")
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return SimpleNamespace(
        store=store,
        path=tmp_path / "conflicts.db",
        book=book,
        first=first,
        second=second,
        first_source=first_source.id,
        second_source=second_source.id,
        conflict_source=conflict_source.id,
        vault=vault,
    )


def rule(procedure_id: int, severity: str, context: tuple[str, ...], source_id: int) -> object:
    constructor = getattr(procedures, "PracticeConflictRule", None)
    assert callable(constructor), "R19_PUBLIC_API_MISSING: PracticeConflictRule"
    return constructor(procedure_id, severity, context, source_id)


def record(
    b: SimpleNamespace,
    *,
    first: object | None = None,
    second: object | None = None,
    situation: tuple[str, ...] = ("database", "single-user"),
    conflict_evidence_id: int | None = None,
) -> object:
    method = getattr(b.book, "record_conflict", None)
    assert callable(method), "R19_PUBLIC_API_MISSING: record_conflict"
    return method(
        wing=WING,
        first=first or rule(b.first.drawer_id, "P1", ("database",), b.first_source),
        second=second
        or rule(b.second.drawer_id, "P2", ("database", "single-user"), b.second_source),
        situation=situation,
        conflict_evidence_id=(
            b.conflict_source if conflict_evidence_id is None else conflict_evidence_id
        ),
        origin="simulated",
    )


def snapshot(b: SimpleNamespace) -> object:
    result = codeglass.build_practice_register(b.store, wing=WING, as_of=AS_OF)
    assert isinstance(result.conflicts, tuple), "conflicts absent from the public register"
    return result


def generated(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(BEGIN) == text.count(END) == 1
    return text.split(BEGIN, 1)[1].split(END, 1)[0]


def ledger_state(store: DrawerStore) -> tuple[object, ...]:
    queries = (
        "SELECT id,wing,room,content,layer,metadata,created_at,claim,predicted_outcome,"
        "observed_outcome,delta,supersedes_id,belief_mass,trust,valid_until,provenance "
        "FROM drawers ORDER BY id",
        "SELECT drawer_id,root_id,parent_id,payload FROM procedure_records ORDER BY drawer_id",
        "SELECT * FROM portable_records ORDER BY drawer_id",
        "SELECT * FROM embedding_chunks ORDER BY drawer_id",
    )
    return tuple(tuple(tuple(row) for row in store._conn.execute(query)) for query in queries)


def assert_public_conflict(
    text: str,
    *,
    first_title: str,
    second_title: str,
    status: str,
    conflict_id: int,
    revision_ids: tuple[int, int],
    source_ids: tuple[int, int, int],
) -> None:
    section = text.split("## Practice conflicts", 1)[1]
    link = f"cairntir-sync/receipts/drawer-{conflict_id}"
    row = next((line for line in section.splitlines() if link in line), None)
    assert row is not None, "conflict row missing"
    assert first_title in row
    assert second_title in row
    assert status in row
    for revision_id in revision_ids:
        assert f"revision-{revision_id}" in row
    for source_id in source_ids:
        assert f"cairntir-sync/receipts/drawer-{source_id}" in row


def test_severity_record_survives_reopen_without_hiding_either_rule(tmp_path: Path) -> None:
    b = seed(tmp_path)
    closed = False
    try:
        receipt = record(b)
        assert receipt.wing == WING
        assert receipt.status == "resolved"
        assert receipt.basis == "severity"
        assert receipt.winner_id == b.first.drawer_id
        assert receipt.first.procedure_id == b.first.drawer_id
        assert receipt.second.procedure_id == b.second.drawer_id
        assert receipt.origin == "simulated"
        assert len(receipt.record_sha256) == 64
        original_state = ledger_state(b.store)
        reversed_duplicate = record(
            b,
            first=rule(b.second.drawer_id, "P2", ("database", "single-user"), b.second_source),
            second=rule(b.first.drawer_id, "P1", ("database",), b.first_source),
        )
        assert reversed_duplicate.drawer_id == receipt.drawer_id
        assert ledger_state(b.store) == original_state
        rows = snapshot(b).rows
        assert {row.title for row in rows} >= {"Postgres guidance", "SQLite guidance"}
        conflict = next(
            row for row in snapshot(b).conflicts if row.conflict_id == receipt.drawer_id
        )
        assert conflict.current and conflict.status == "resolved"
        assert (conflict.first_id, conflict.second_id) == (
            b.first.drawer_id,
            b.second.drawer_id,
        )
        assert conflict.winner_id == b.first.drawer_id
        assert (conflict.first_severity, conflict.second_severity) == ("P1", "P2")
        assert conflict.first_context == ("database",)
        assert conflict.second_context == ("database", "single-user")
        assert conflict.basis == "severity"
        assert {b.first_source, b.second_source, b.conflict_source} <= set(conflict.source_ids)
        b.store.close()
        closed = True
        reopened = DrawerStore(b.path, HashEmbeddingProvider(dimension=16))
        try:
            read_book = procedures.ProcedureBook(reopened, {})
            persisted = read_book.get_conflict(receipt.drawer_id)
            assert persisted == receipt
            assert [item.drawer_id for item in read_book.list_conflicts(wing=WING)] == [
                receipt.drawer_id
            ]
        finally:
            reopened.close()
    finally:
        if not closed:
            b.store.close()


def test_specificity_is_recorded_but_ambiguous_context_queues_adr(tmp_path: Path) -> None:
    b = seed(tmp_path)
    try:
        specific = record(
            b,
            first=rule(b.first.drawer_id, "P2", ("database",), b.first_source),
            second=rule(b.second.drawer_id, "P2", ("database", "single-user"), b.second_source),
        )
        assert (specific.status, specific.basis, specific.winner_id) == (
            "resolved",
            "specificity",
            b.second.drawer_id,
        )
        ambiguous = record(
            b,
            first=rule(b.first.drawer_id, "P2", ("database", "local"), b.first_source),
            second=rule(b.second.drawer_id, "P2", ("database", "sqlite"), b.second_source),
            situation=("database", "local", "sqlite"),
        )
        assert ambiguous.status == "adr_required"
        assert ambiguous.winner_id is None and ambiguous.basis is None
        assert ambiguous.drawer_id != specific.drawer_id
        shown = {row.conflict_id: row for row in snapshot(b).conflicts}
        assert shown[ambiguous.drawer_id].status == "adr_required"
        assert shown[ambiguous.drawer_id].winner_id is None
        assert {item.title for item in snapshot(b).rows} >= {
            "Postgres guidance",
            "SQLite guidance",
        }
        b.store.add(
            Drawer(
                wing=WING,
                room="notes",
                content="SIMULATED developer ADR text; no authenticated decision",
                metadata={"kind": "developer-adr"},
            )
        )
        assert b.book.get_conflict(ambiguous.drawer_id).status == "adr_required"
    finally:
        b.store.close()


def test_invalid_or_unauthorized_claims_do_not_append_conflicts(tmp_path: Path) -> None:
    b = seed(tmp_path)
    try:
        foreign = b.store.add(Drawer(wing="other-wing", room="sources", content="foreign"))
        assert foreign.id is not None
        before = ledger_state(b.store)
        bad = (
            {"first": rule(b.second.drawer_id, "P1", ("database",), b.second_source)},
            {"first": rule(b.first.drawer_id, "P9", ("database",), b.first_source)},
            {"first": rule(b.first.drawer_id, "P1", ("unknown",), b.first_source)},
            {"first": rule(b.first.drawer_id, "P1", ("database",), b.second_source)},
            {"first": rule(b.first.drawer_id, "P1", ("database",), foreign.id)},
            {"conflict_evidence_id": foreign.id},
            {"conflict_evidence_id": 0},
        )
        for case in bad:
            with pytest.raises(procedures.ProcedureError):
                record(b, **case)
            assert ledger_state(b.store) == before
        candidate = b.book.revise(
            b.first.drawer_id,
            spec=procedures.ProcedureSpec(
                "Postgres guidance",
                ("local datastore choice",),
                "SIMULATED database choice",
                ("candidate", "use Postgres again"),
                "one datastore selected",
                ("return to prior choice",),
                (b.first_source,),
                governance=procedures.PracticeGovernance(
                    "synthetic owner", "2", "candidate revision", "2026-05-01"
                ),
            ),
        )
        before = ledger_state(b.store)
        stale = (
            {"first": rule(b.first.drawer_id, "P1", ("database",), b.first_source)},
            {"first": rule(candidate.drawer_id, "P1", ("database",), b.first_source)},
        )
        for case in stale:
            with pytest.raises(procedures.ProcedureError):
                record(b, **case)
            assert ledger_state(b.store) == before
    finally:
        b.store.close()


def test_practice_revision_stales_prior_resolution_without_erasing_history(tmp_path: Path) -> None:
    b = seed(tmp_path)
    try:
        receipt = record(b)
        next_spec = procedures.ProcedureSpec(
            "Postgres guidance",
            ("local datastore choice",),
            "SIMULATED database choice",
            ("candidate", "reconsider the datastore"),
            "one datastore selected",
            ("return to prior choice",),
            (b.first_source,),
            governance=procedures.PracticeGovernance(
                "synthetic owner", "2", "changed guidance", "2026-05-01"
            ),
        )
        b.book.revise(b.first.drawer_id, spec=next_spec)
        assert b.book.get_conflict(receipt.drawer_id) == receipt
        current = next(row for row in snapshot(b).conflicts if row.conflict_id == receipt.drawer_id)
        assert current.current is False
        assert current.status == "stale_revision"
        assert current.winner_id is None
    finally:
        b.store.close()


def test_projection_shows_both_sides_and_redacts_lost_source_preserving_notes(
    tmp_path: Path,
) -> None:
    b = seed(tmp_path)
    try:
        pending = record(
            b,
            first=rule(b.first.drawer_id, "P2", ("database",), b.first_source),
            second=rule(b.second.drawer_id, "P2", ("database",), b.second_source),
        )
        projection = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert projection.practice_register_status == "published"
        register = projection.practice_register_note
        assert register is not None
        shown = generated(register)
        assert_public_conflict(
            shown,
            first_title="Postgres guidance",
            second_title="SQLite guidance",
            status="adr_required",
            conflict_id=pending.drawer_id,
            revision_ids=(b.first.drawer_id, b.second.drawer_id),
            source_ids=(b.first_source, b.second_source, b.conflict_source),
        )
        assert shown.count("P2") >= 2 and "database" in shown and "simulated" in shown.lower()
        assert "developer ADR" in shown
        receipt_path = b.vault / "cairntir-sync" / "receipts" / f"drawer-{pending.drawer_id}.md"
        assert receipt_path.is_file()
        assert f"cairntir://drawer/{pending.drawer_id}" in generated(receipt_path)
        for source_id in (b.first_source, b.second_source, b.conflict_source):
            assert (b.vault / "cairntir-sync" / "receipts" / f"drawer-{source_id}.md").is_file()
        assert sum("revision-" in str(path) for path in projection.practice_history_notes) >= 2
        human = "\nMyNotes: retain this human explanation verbatim.\n"
        register.write_text(register.read_text(encoding="utf-8") + human, encoding="utf-8")
        again = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert again.practice_register_status == "published"
        assert register.read_text(encoding="utf-8").endswith(human)
        with b.store._conn:
            b.store._conn.execute(
                "DELETE FROM embedding_chunks WHERE drawer_id = ?", (b.conflict_source,)
            )
            b.store._conn.execute(
                "DELETE FROM portable_records WHERE drawer_id = ?", (b.conflict_source,)
            )
            b.store._conn.execute("DELETE FROM drawers WHERE id = ?", (b.conflict_source,))
        unavailable = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert unavailable.practice_register_status == "unavailable"
        redacted = generated(register)
        assert "unavailable" in redacted.lower()
        for forbidden in (
            "Postgres guidance",
            "SQLite guidance",
            "adr_required",
            str(pending.drawer_id),
            "SIMULATED conflict",
        ):
            assert forbidden not in redacted
        assert register.read_text(encoding="utf-8").endswith(human)
        for receipt_id in (
            pending.drawer_id,
            b.first_source,
            b.second_source,
            b.conflict_source,
        ):
            path = b.vault / "cairntir-sync" / "receipts" / f"drawer-{receipt_id}.md"
            assert f"cairntir://drawer/{receipt_id}" not in generated(path)
    finally:
        b.store.close()


def test_public_output_oracle_rejects_suppression_and_invented_resolution(
    tmp_path: Path,
) -> None:
    b = seed(tmp_path)
    try:
        pending = record(
            b,
            first=rule(b.first.drawer_id, "P2", ("database",), b.first_source),
            second=rule(b.second.drawer_id, "P2", ("database",), b.second_source),
        )
        result = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert result.practice_register_note is not None
        text = generated(result.practice_register_note)
        expected = {
            "first_title": "Postgres guidance",
            "second_title": "SQLite guidance",
            "status": "adr_required",
            "conflict_id": pending.drawer_id,
            "revision_ids": (b.first.drawer_id, b.second.drawer_id),
            "source_ids": (b.first_source, b.second_source, b.conflict_source),
        }
        assert_public_conflict(text, **expected)
        broken = (
            text.replace("SQLite guidance", ""),
            text.replace("adr_required", "resolved", 1),
            text.replace(f"cairntir-sync/receipts/drawer-{pending.drawer_id}", "", 1),
            text.replace(f"revision-{b.second.drawer_id}", ""),
            text.replace(f"cairntir-sync/receipts/drawer-{b.conflict_source}", ""),
        )
        for forged in broken:
            with pytest.raises(AssertionError):
                assert_public_conflict(forged, **expected)
    finally:
        b.store.close()


def test_secret_conflict_source_has_no_public_identity_or_count(tmp_path: Path) -> None:
    b = seed(tmp_path)
    try:
        secret = b.store.add(
            Drawer(wing=WING, room="sources", content="SECRET_R19_CONFLICT_SENTINEL"),
            provenance=WriteProvenance.create(
                host="r19-synthetic", capture_path="acceptance", sensitivity=Sensitivity.SECRET
            ),
        )
        assert secret.id is not None
        stored = record(b, conflict_evidence_id=secret.id)
        assert b.book.get_conflict(stored.drawer_id).drawer_id == stored.drawer_id
        result = project_to_obsidian(
            b.store, vault=b.vault, wing=WING, practice_register=True, as_of=AS_OF
        )
        assert result.practice_register_status == "unavailable"
        assert result.practice_register_note is not None
        public = generated(result.practice_register_note)
        assert "unavailable" in public.lower()
        for forbidden in (
            "SECRET_R19_CONFLICT_SENTINEL",
            str(secret.id),
            str(stored.drawer_id),
            "Postgres guidance",
            "SQLite guidance",
            "adr_required",
        ):
            assert forbidden not in public
    finally:
        b.store.close()


def test_counterfeit_and_tampered_conflict_records_are_refused(tmp_path: Path) -> None:
    b = seed(tmp_path)
    try:
        counterfeit = b.store.add(
            Drawer(
                wing=WING,
                room="practice-reviews",
                content='{"kind":"cairntir.practice-conflict.v1","winner_id":1}',
                metadata={"kind": "cairntir.practice-conflict.v1"},
            )
        )
        assert counterfeit.id is not None
        with pytest.raises(procedures.ProcedureError):
            b.book.get_conflict(counterfeit.id)
        genuine = record(b)
        assert b.book.get_conflict(genuine.drawer_id) == genuine
        raw = b.store._conn.execute(
            "SELECT payload FROM procedure_evaluations WHERE drawer_id = ?",
            (genuine.drawer_id,),
        ).fetchone()
        assert raw is not None
        forged = json.loads(raw[0])
        forged["record_sha256"] = "0" * 64
        with b.store._conn:
            b.store._conn.execute(
                "UPDATE procedure_evaluations SET payload = ? WHERE drawer_id = ?",
                (json.dumps(forged, sort_keys=True), genuine.drawer_id),
            )
        with pytest.raises(procedures.ProcedureError):
            b.book.get_conflict(genuine.drawer_id)
    finally:
        b.store.close()
