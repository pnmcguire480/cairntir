from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from test_recovery_outcomes import TEXT, contents
from typer.testing import CliRunner

from cairntir import backups
from cairntir.cli import app
from cairntir.config import model_cache_dir
from cairntir.errors import EmbeddingError
from cairntir.learning import record_discovery
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.recipes import load_recipe

RUNNER = CliRunner()


@pytest.fixture(autouse=True)
def isolated_cli(tmp_cairntir_home, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider", lambda: HashEmbeddingProvider(dimension=32)
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "user"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.delenv("CAIRNTIR_VAULT", raising=False)
    return tmp_cairntir_home / "cairntir.db"


@pytest.mark.parametrize(
    "args",
    [
        ["cost", "empty"],
        ["cross-recall", "query"],
        ["get", "1"],
        ["recall", "query"],
        ["reindex", "--yes"],
        ["recipe-run", "unknown"],
        ["hotfix", "status", "--wing", "empty"],
        ["export", "unused.jsonl"],
        ["migrate"],
    ],
)
def test_missing_store_is_reported_without_creating_a_database(isolated_cli, args):
    result = RUNNER.invoke(app, args)
    assert result.exit_code == 1, result.output
    assert "cairntir:" in result.output
    assert not isolated_cli.exists()
    assert not Path("unused.jsonl").exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"\xff",
        b"[]",
        b"{}",
        b'{"content":"request","checkpoint":[]}',
        b'{"content":"request","checkpoint":{},"unexpected":true}',
    ],
)
def test_invalid_checkpoint_file_reports_error_without_mutating_any_table(
    seeded, tmp_path, payload
):
    database, _, _ = seeded
    before = contents(database)
    path = tmp_path / "checkpoint.json"
    path.write_bytes(payload)
    result = RUNNER.invoke(app, ["checkpoint", "recovery", "--input", str(path)])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert "Traceback" not in result.output
    assert contents(database) == before


def test_missing_checkpoint_file_is_reported_before_store_creation(isolated_cli):
    result = RUNNER.invoke(app, ["checkpoint", "recovery", "--input", "missing.json"])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert not isolated_cli.exists()


@pytest.mark.parametrize("payload", ["{", "[]", "true", "null"])
def test_invalid_hotfix_payload_cannot_append_a_case(seeded, payload):
    database, _, _ = seeded
    before = contents(database)
    result = RUNNER.invoke(app, ["hotfix", "open", "--wing", "recovery", "--payload", payload])
    assert result.exit_code == 1 and "--payload" in result.output
    assert contents(database) == before


def test_get_returns_complete_verbatim_memory_and_missing_id_is_explicit(seeded):
    database, _, _ = seeded
    result = RUNNER.invoke(app, ["get", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["content"] == TEXT
    before = contents(database)
    missing = RUNNER.invoke(app, ["get", "99999"])
    assert missing.exit_code == 1 and "cairntir:" in missing.output
    assert contents(database) == before


def test_doctor_runs_integrity_gate_without_mutating_the_store(seeded):
    database, _, _ = seeded
    before = contents(database)
    result = RUNNER.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 0, result.output
    assert "sqlite integrity:   ok" in result.output and "gate: ok" in result.output
    assert contents(database) == before


def test_doctor_reports_missing_vector_without_attempting_repair(seeded):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute("DELETE FROM vec_drawers WHERE drawer_id=1")
        store._conn.commit()
    before = contents(database)
    result = RUNNER.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 1 and "reindex" in result.output
    assert "2 vectors for 3 drawers" in result.output
    assert contents(database) == before


def test_cancelled_reindex_preserves_source_and_creates_no_backup(seeded):
    database, _, _ = seeded
    model_cache_dir()
    before = contents(database)
    files = set(database.parent.iterdir())
    result = RUNNER.invoke(app, ["reindex"], input="n\n")
    assert result.exit_code == 0 and "cancelled" in result.output
    assert contents(database) == before
    assert set(database.parent.iterdir()) == files


def test_unavailable_model_preflight_preserves_source_and_previous_backup(seeded, monkeypatch):
    database, _, _ = seeded
    before = contents(database)
    backup = database.with_name("previous-backup.db")
    backup.write_bytes(database.read_bytes())
    original = backup.read_bytes()

    class MissingModel:
        @property
        def dimension(self):
            raise EmbeddingError("cached model is unavailable")

    monkeypatch.setattr("cairntir.cli.production_embedding_provider", MissingModel)
    result = RUNNER.invoke(app, ["reindex", "--yes", "--backup", str(backup)])
    assert result.exit_code == 1 and "preflight failed" in result.output
    assert "store was NOT modified" in result.output
    assert contents(database) == before and backup.read_bytes() == original


@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf"])
def test_bad_cli_backup_interval_keeps_existing_policy_and_store(seeded, tmp_path, interval):
    database, _, _ = seeded
    destination = tmp_path / "backups"
    backups.configure(database, destination)
    before = contents(database)
    policy = backups.status(database)
    result = RUNNER.invoke(
        app, ["backup", "configure", str(destination), "--interval-hours", interval]
    )
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert backups.status(database) == policy and contents(database) == before


def test_cli_reports_busy_backup_without_claiming_success(seeded, tmp_path):
    database, _, _ = seeded
    backups.configure(database, tmp_path / "backups")
    before = contents(database)
    with backups._lock(database, create=True) as acquired:
        assert acquired
        result = RUNNER.invoke(app, ["backup", "run"])
        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "busy"
        denied = RUNNER.invoke(app, ["backup", "disable"])
        assert denied.exit_code == 1 and "in progress" in denied.output
    assert contents(database) == before and backups.status(database)["enabled"]


@pytest.fixture()
def typed_recipe(tmp_path, monkeypatch):
    contract = tmp_path / "recipe.toml"
    contract.write_text(
        """[recipe]
name = "typed-inputs"
description = "Preserve the user's declared input types."
version = "1"
output_wing = "recipe-probe"
skills = ["quality"]
[input.count]
type = "integer"
required = true
[input.confirmed]
type = "boolean"
required = true
""",
        encoding="utf-8",
    )
    recipe = load_recipe(contract)
    monkeypatch.setattr("cairntir.recipes.discover_recipes", lambda: [recipe])
    return recipe


@pytest.mark.parametrize(("value", "stored"), [("yes", "True"), ("OFF", "False")])
def test_recipe_cli_preserves_typed_user_input_and_idempotent_retry(
    seeded, typed_recipe, value, stored
):
    database, _, _ = seeded
    args = [
        "recipe-run",
        "typed-inputs",
        "--input",
        "count=007",
        "--input",
        f"confirmed={value}",
        "--idempotency-key",
        "typed-recipe",
    ]
    first = RUNNER.invoke(app, args)
    assert first.exit_code == 0, first.output
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        produced = store.list_by(wing="recipe-probe")
        assert any(
            "**count:** 7" in item.content and f"**confirmed:** {stored}" in item.content
            for item in produced
        )
    before = contents(database)
    replay = RUNNER.invoke(app, args)
    assert replay.exit_code == 0 and replay.output == first.output
    assert contents(database) == before


@pytest.mark.parametrize(
    ("argument", "message"),
    [
        ("broken", "KEY=VALUE"),
        ("unknown=1", "no input"),
        ("count=oops", "expected integer"),
        ("confirmed=maybe", "expected boolean"),
    ],
)
def test_bad_recipe_cli_input_does_not_write_partial_evidence(
    seeded, typed_recipe, argument, message
):
    database, _, _ = seeded
    before = contents(database)
    result = RUNNER.invoke(app, ["recipe-run", "typed-inputs", "--input", argument])
    assert result.exit_code != 0 and message in result.output
    assert contents(database) == before


def test_setup_declined_registration_leaves_host_files_untouched(isolated_cli, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    before = set(Path.home().rglob("*"))
    result = RUNNER.invoke(app, ["setup"], input="n\n")
    assert result.exit_code == 0, result.output
    assert "skipped host registration" in result.output
    assert "write + read round-trip passed" in result.output
    assert set(Path.home().rglob("*")) == before
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=32)) as store:
        assert store.list_by()


@pytest.mark.parametrize(
    "args",
    [
        ["discover", "", "summary", "--wing", "recovery", "--novelty", "user", "--evidence", "1"],
        ["discover", "title", "", "--wing", "recovery", "--novelty", "user", "--evidence", "1"],
        [
            "discover",
            "title",
            "summary",
            "--wing",
            "recovery",
            "--novelty",
            "unknown",
            "--evidence",
            "1",
        ],
        [
            "discover",
            "title",
            "summary",
            "--wing",
            "recovery",
            "--novelty",
            "user",
            "--evidence",
            "9999",
        ],
        [
            "discover",
            "title",
            "summary",
            "--wing",
            "recovery",
            "--novelty",
            "user",
            "--evidence",
            "1",
            "--state",
            "unknown",
        ],
        ["discovery-transition", "9999", "candidate", "--note", "reviewed"],
    ],
)
def test_invalid_discovery_cli_request_cannot_append_evidence(seeded, args):
    database, _, _ = seeded
    before = contents(database)
    result = RUNNER.invoke(app, args)
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert contents(database) == before


@pytest.mark.parametrize("command", ["discoveries", "learning-log"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("discovery_state", "unknown"),
        ("novelty_scope", "unknown"),
        ("evidence_drawer_ids", "1"),
        ("discovery_title", ""),
        ("discovery_summary", ""),
        ("confidence", True),
        ("confidence", 1.1),
        ("observation_count", 0),
        ("baseline", []),
        ("counterexample_drawer_ids", [True]),
    ],
)
def test_cli_surfaces_damaged_learning_records_instead_of_an_empty_success(
    seeded, command, field, value
):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        discovery = record_discovery(
            store,
            wing="recovery",
            title="Observed improvement",
            summary="Retrieval preserved exact evidence.",
            novelty="user",
            evidence_ids=(1,),
            state="candidate",
        )
        row = store.get(discovery.drawer_id)
        metadata = dict(row.metadata)
        metadata[field] = value
        store._conn.execute(
            "UPDATE drawers SET metadata=? WHERE id=?", (json.dumps(metadata), row.id)
        )
        store._conn.commit()
    before = contents(database)
    result = RUNNER.invoke(app, [command, "--wing", "recovery"])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert f"drawer #{discovery.drawer_id}" in result.output
    assert contents(database) == before


def test_cli_projects_real_learning_and_preserves_user_notes(seeded, tmp_path):
    database, _, _ = seeded
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    note = vault / "personal.md"
    note.write_text("The user's own notes.\n", encoding="utf-8")
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        record_discovery(
            store,
            wing="recovery",
            title="Restoration verified",
            summary=TEXT,
            novelty="user",
            evidence_ids=(1,),
            state="candidate",
        )
    result = RUNNER.invoke(app, ["obsidian-project", str(vault), "--wing", "recovery"])
    assert result.exit_code == 0, result.output
    projected = [path.read_text(encoding="utf-8") for path in vault.rglob("*.md") if path != note]
    assert any("Restoration verified" in text and TEXT.strip() in text for text in projected)
    assert note.read_text(encoding="utf-8") == "The user's own notes.\n"
    files = {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    repeated = RUNNER.invoke(app, ["obsidian-project", str(vault), "--wing", "recovery"])
    assert repeated.exit_code == 0
    assert {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()} == files


def test_cli_projection_failure_preserves_source_and_unavailable_destination(seeded, tmp_path):
    database, _, _ = seeded
    destination = tmp_path / "unavailable-vault"
    destination.write_text("mounted destination unavailable", encoding="utf-8")
    before = contents(database)
    result = RUNNER.invoke(app, ["obsidian-project", str(destination)])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert contents(database) == before
    assert destination.read_text(encoding="utf-8") == "mounted destination unavailable"


def test_reindex_cli_cannot_overwrite_the_previous_recovery_point(seeded, tmp_path):
    database, _, _ = seeded
    destination = tmp_path / "backup.db"
    shutil.copyfile(database, destination)
    before = contents(database), destination.read_bytes()
    result = RUNNER.invoke(app, ["reindex", "--yes", "--backup", str(destination)])
    assert result.exit_code == 1 and "refusing to overwrite" in result.output
    assert (contents(database), destination.read_bytes()) == before


def test_interactive_reason_preserves_the_answers_and_replays_without_duplicate_writes(seeded):
    database, _, _ = seeded
    args = [
        "reason",
        "Will restoration work?",
        "--wing",
        "recovery",
        "--idempotency-key",
        "prompted-reason",
    ]
    answers = (
        "The snapshot is complete.\nAll memories survive.\nEvery original memory survived.\ny\n"
    )
    result = RUNNER.invoke(app, args, input=answers)
    assert result.exit_code == 0, result.output
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        rows = store.list_by(wing="recovery", room="predictions")
        assert any(
            row.claim == "The snapshot is complete."
            and row.predicted_outcome == "All memories survive."
            for row in rows
        )
        assert any(row.observed_outcome == "Every original memory survived." for row in rows)
    before = contents(database)
    replayed = RUNNER.invoke(app, args, input=answers)
    assert replayed.exit_code == 0 and replayed.output == result.output
    assert contents(database) == before


def test_cli_context_demo_reports_whole_evidence_under_the_requested_budget(seeded, tmp_path):
    database, _, _ = seeded
    before = contents(database)
    destination = tmp_path / "context-report"
    result = RUNNER.invoke(app, ["context-demo", str(destination), "--budget", "8192"])
    assert result.exit_code == 0, result.output
    report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
    selected = json.loads(report["selected_payload"])
    history = json.loads(report["full_history_payload"])["evidence"]
    originals = {item["drawer_id"]: item["content"] for item in history}
    assert selected["status"] == "selected" and selected["evidence"]
    assert report["metrics"]["selected_chars"] == len(report["selected_payload"]) <= 8192
    assert all(item["content"] == originals[item["drawer_id"]] for item in selected["evidence"])
    assert json.loads(report["abstention_payload"])["status"] == "abstained"
    assert contents(database) == before


def test_cli_context_demo_unavailable_output_does_not_touch_existing_store(seeded, tmp_path):
    database, _, _ = seeded
    destination = tmp_path / "not-a-directory"
    destination.write_bytes(b"existing document")
    before = contents(database)
    result = RUNNER.invoke(app, ["context-demo", str(destination)])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert destination.read_bytes() == b"existing document" and contents(database) == before


def test_empty_recipe_inventory_is_explicit_and_readonly(seeded, monkeypatch):
    database, _, _ = seeded
    before = contents(database)
    monkeypatch.setattr("cairntir.recipes.discover_recipes", lambda: [])
    listed = RUNNER.invoke(app, ["recipe-list"])
    assert listed.exit_code == 0 and "no recipes found" in listed.output
    missing = RUNNER.invoke(app, ["recipe-run", "missing"])
    assert missing.exit_code == 1 and "not found" in missing.output
    assert contents(database) == before


@pytest.mark.parametrize(
    "arguments",
    [
        ["doctor"],
        ["reindex", "--yes"],
        ["cost", "recovery"],
        ["calibration", "--wing", "recovery"],
        ["discover-scan", "--wing", "recovery"],
        ["hotfix", "status", "--wing", "recovery"],
    ],
)
def test_damaged_database_is_reported_without_false_success_or_replacement(isolated_cli, arguments):
    isolated_cli.parent.mkdir(parents=True, exist_ok=True)
    original = b"damaged SQLite snapshot: preserve this for diagnosis" * 100
    isolated_cli.write_bytes(original)
    result = RUNNER.invoke(app, arguments)
    assert result.exit_code == 1, result.output
    assert "cairntir:" in result.output and "Traceback" not in result.output
    assert isolated_cli.read_bytes() == original
    assert not list(isolated_cli.parent.glob("*.backup-*"))


def test_cli_calibration_and_discovery_scan_do_not_invent_results_without_observations(seeded):
    database, _, _ = seeded
    before = contents(database)
    calibration = RUNNER.invoke(app, ["calibration", "--wing", "recovery"])
    assert calibration.exit_code == 0, calibration.output
    assert "not enough resolved predictions" in calibration.output
    assert "confirmed / failed: 0 / 0" in calibration.output
    scan = RUNNER.invoke(app, ["discover-scan", "--wing", "recovery"])
    assert scan.exit_code == 0 and "No new multi-episode" in scan.output
    assert contents(database) == before


def test_cli_recovery_requires_explicit_selection_before_storing_verbatim_request(
    seeded, monkeypatch
):
    database, _, _ = seeded
    project = Path.cwd()
    transcript = Path.home() / ".codex" / "sessions" / "rollout-previous.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": "previous", "cwd": str(project)}})
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-09-07T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": TEXT},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CAIRNTIR_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_SESSION_ID", raising=False)
    args = ["recover", "--host", "codex", "--wing", "new-project"]
    before = contents(database)
    shown = RUNNER.invoke(app, args)
    assert shown.exit_code == 0, shown.output
    quoted = shown.output.split("<cairntir-transcript-evidence>\n", 1)[1].split("\n</", 1)[0]
    assert json.loads(quoted)["content"] == TEXT
    assert contents(database) == before
    invalid = RUNNER.invoke(app, [*args, "--write", "2"])
    assert invalid.exit_code == 1 and "--write index" in invalid.output
    assert contents(database) == before
    stored = RUNNER.invoke(app, [*args, "--write", "1"])
    assert stored.exit_code == 0 and "trust=untrusted" in stored.output, stored.output
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        recovered = store.list_by(wing="new-project")
        assert len(recovered) == 1 and recovered[0].content == TEXT
        provenance = store.get_provenance(recovered[0].id)
        assert provenance.trust.value == "untrusted"
        assert provenance.capture_path == "transcript_recovered"


def test_recipe_inventory_identifies_the_available_contract_without_running_it(
    seeded, typed_recipe
):
    database, _, _ = seeded
    before = contents(database)
    listed = RUNNER.invoke(app, ["recipe-list"])
    assert listed.exit_code == 0 and "typed-inputs" in listed.output
    assert "source:" in listed.output and str(typed_recipe.source_path) in listed.output
    assert contents(database) == before


def test_cli_reindex_creates_a_restorable_default_backup_before_changing_index(seeded):
    database, task, expected = seeded
    before = contents(database)
    result = RUNNER.invoke(app, ["reindex", "--yes"])
    assert result.exit_code == 0, result.output
    copies = list(database.parent.glob("*.backup-*.db"))
    assert len(copies) == 1 and contents(copies[0], standalone=True) == before
    from cairntir.tasks import TaskBook

    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        assert TaskBook(store).resume("recovery", task_id=task) == expected
        assert store.search(TEXT, wing="recovery", room="evidence", limit=1)[0][0].content == TEXT


@pytest.mark.parametrize("metadata", ['{"anchors":[{"path":" "}]}', '{"anchors":1}', "{"])
def test_doctor_gate_identifies_bad_anchor_evidence_without_repairing_it(seeded, metadata):
    database, _, _ = seeded
    with DrawerStore(database, HashEmbeddingProvider(dimension=32)) as store:
        store._conn.execute("UPDATE drawers SET metadata=? WHERE id=1", (metadata,))
        store._conn.commit()
    before = contents(database)
    result = RUNNER.invoke(app, ["doctor", "--gate"])
    assert result.exit_code == 1, result.output
    assert "malformed metadata.anchors" in result.output and "[1]" in result.output
    assert contents(database) == before


def test_doctor_gate_cannot_claim_vault_verification_when_destination_is_unavailable(
    seeded, tmp_path
):
    database, _, _ = seeded
    before = contents(database)
    result = RUNNER.invoke(app, ["doctor", "--gate", "--vault", str(tmp_path / "missing-vault")])
    assert result.exit_code == 1 and "cairntir:" in result.output
    assert contents(database) == before
