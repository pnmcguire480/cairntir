"""Tests for the Obsidian vault -> Cairntir ingest.

The defect this feature closes is not "the import was wrong", it is "the import
did not exist and nothing noticed for four months." So the load-bearing tests
here are the ones that assert `--check` **fails**: a drift gate that can only
pass is the same defect wearing a disguise.

Nothing here touches the real vault or the real store. Every test builds a fake
vault under `tmp_path` and points `CAIRNTIR_HOME` at a temporary directory.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

from cairntir.cli import app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.vault import (
    VaultSyncError,
    apply_sync,
    collect,
    parse_name,
    plan_sync,
    render_plan,
    resolve_vault,
    room_for,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_vault_and_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real vault or real store leak into a test.

    `CAIRNTIR_VAULT` is a documented env var, so a machine that has one set
    would otherwise silently supply it to every `--vault`-less invocation.
    """
    monkeypatch.delenv("CAIRNTIR_VAULT", raising=False)
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=384),
    )


def _make_vault(root: Path, notes: dict[str, str] | None = None) -> Path:
    """Build a minimal Obsidian vault with two mapped walkthrough folders."""
    vault = root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    contents = notes or {
        "Triangulate/2026-03-30-pipeline-audit.md": "The pipeline audit found three gaps.",
        "Triangulate/2026-04-02-schema-review.md": "Schema review: the join key is wrong.",
        "examples/2026-05-01-walkthrough-of-the-loop.md": "How the reason loop actually runs.",
    }
    for relative, text in contents.items():
        target = vault / "walkthroughs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return vault


def _store(tmp_path: Path) -> DrawerStore:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=384))


def _load_wrapper() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "scripts_vault_sync", REPO_ROOT / "scripts" / "vault_sync.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- vault resolution -------------------------------------------------------


def test_resolve_vault_requires_a_path_and_names_both_ways_to_give_one() -> None:
    with pytest.raises(VaultSyncError) as caught:
        resolve_vault(None)
    assert "--vault" in str(caught.value)
    assert "CAIRNTIR_VAULT" in str(caught.value)


def test_resolve_vault_rejects_a_directory_that_is_not_an_obsidian_vault(tmp_path: Path) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    with pytest.raises(VaultSyncError, match=r"missing \.obsidian"):
        resolve_vault(plain)


def test_resolve_vault_rejects_a_path_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(VaultSyncError, match="not a directory"):
        resolve_vault(tmp_path / "nowhere")


def test_resolve_vault_accepts_a_real_vault(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    assert resolve_vault(str(vault)) == vault


# --- name and room derivation ----------------------------------------------


def test_parse_name_splits_a_dated_stem_into_its_date_and_slug() -> None:
    when, slug = parse_name("2026-03-30-pipeline-audit")
    assert when == datetime(2026, 3, 30, tzinfo=UTC)
    assert slug == "pipeline-audit"


def test_parse_name_returns_no_date_for_an_undated_or_impossible_stem() -> None:
    assert parse_name("pipeline-audit") == (None, "pipeline-audit")
    assert parse_name("2026-02-31-pipeline-audit") == (None, "2026-02-31-pipeline-audit")


def test_room_for_produces_an_identifier_the_taxonomy_accepts() -> None:
    assert room_for("2026-03-30-Pipeline Audit", wing="triangulate") == (
        "walkthrough-2026-03-30-pipeline-audit"
    )
    # codeglass notes are examples, not walkthroughs.
    assert room_for("loop", wing="codeglass") == "example-loop"
    # Rooms cap at 64 characters and never end on a separator.
    long_room = room_for("x" * 200, wing="triangulate")
    assert len(long_room) <= 64
    assert long_room[-1].isalnum()


# --- collection -------------------------------------------------------------


def test_collect_reads_mapped_folders_and_ignores_everything_else(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {
            "Triangulate/2026-03-30-pipeline-audit.md": "mapped folder",
            "NotAWing/2026-03-30-orphan.md": "unmapped folder, must not be imported",
            "Triangulate/2026-04-01-empty.md": "   ",
        },
    )
    found = collect(vault)

    assert [item.wing for item in found] == ["triangulate"]
    assert found[0].content == "mapped folder"
    assert found[0].task_slug == "pipeline-audit"
    assert "orphan" not in {item.task_slug for item in found}


def test_collect_dates_a_drawer_from_its_filename_not_from_today(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    found = {item.task_slug: item for item in collect(vault)}
    assert found["pipeline-audit"].created_at == datetime(2026, 3, 30, tzinfo=UTC)


# --- plan / apply -----------------------------------------------------------


def test_plan_sync_reports_every_walkthrough_as_drift_against_an_empty_store(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path)
    with _store(tmp_path) as store:
        plan = plan_sync(store, vault)
    assert len(plan.found) == 3
    assert len(plan.missing) == 3
    assert plan.present == 0
    assert plan.has_drift is True
    assert plan.counts_by_wing() == {"codeglass": 1, "triangulate": 2}


def test_apply_sync_writes_verbatim_content_and_then_reports_no_drift(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    with _store(tmp_path) as store:
        written = apply_sync(store, plan_sync(store, vault))
        assert len(written) == 3
        assert {d.content for d in written} == {
            "The pipeline audit found three gaps.",
            "Schema review: the join key is wrong.",
            "How the reason loop actually runs.",
        }

        again = plan_sync(store, vault)
        assert again.has_drift is False
        assert again.present == 3
        # Idempotent: a second apply writes nothing.
        assert apply_sync(store, again) == ()


def test_apply_sync_records_where_the_drawer_came_from(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    with _store(tmp_path) as store:
        written = apply_sync(store, plan_sync(store, vault))
    drawer = next(d for d in written if d.room.endswith("pipeline-audit"))
    assert drawer.metadata["kind"] == "obsidian_walkthrough"
    assert drawer.metadata["importer"] == "cairntir.vault"
    assert drawer.metadata["source_path"].endswith("2026-03-30-pipeline-audit.md")
    assert drawer.created_at == datetime(2026, 3, 30, tzinfo=UTC)


def test_collect_surfaces_an_unreadable_note_instead_of_skipping_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_vault(tmp_path)

    def _boom(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("disk fell over")

    monkeypatch.setattr(Path, "read_text", _boom)
    with pytest.raises(VaultSyncError, match="could not read vault note"):
        collect(vault)


def test_render_plan_summarises_once_the_sample_runs_out(tmp_path: Path) -> None:
    notes = {f"Triangulate/2026-03-{day:02d}-note.md": f"note {day}" for day in range(1, 9)}
    vault = _make_vault(tmp_path, notes)
    with _store(tmp_path) as store:
        rendered = render_plan(plan_sync(store, vault), check=False)
    assert "... and 3 more" in rendered


def test_render_plan_names_the_drift_when_checking(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    with _store(tmp_path) as store:
        plan = plan_sync(store, vault)
    assert "DRIFT: 3 vault walkthrough(s) have no drawer" in render_plan(plan, check=True)


# --- CLI --------------------------------------------------------------------


def test_check_exits_nonzero_when_a_walkthrough_has_no_drawer(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    result = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check"])

    assert result.exit_code == 1, result.output
    assert "DRIFT" in result.output
    assert "3 vault walkthrough(s) have no drawer" in result.output


def test_check_writes_nothing_even_when_it_finds_drift(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    assert runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check"]).exit_code == 1

    with _store(tmp_path) as store:
        assert store.list_by(limit=100) == []


def test_check_passes_once_every_walkthrough_is_imported(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    with _store(tmp_path) as store:
        apply_sync(store, plan_sync(store, vault))

    result = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check"])

    assert result.exit_code == 0, result.output
    assert "ok: every vault walkthrough has a drawer" in result.output


def test_writing_mode_is_a_dry_run_by_default(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    result = runner.invoke(app, ["vault-sync", "--vault", str(vault)])

    assert result.exit_code == 0, result.output
    assert "DRY RUN, nothing written" in result.output
    with _store(tmp_path) as store:
        assert store.list_by(limit=100) == []


def test_apply_imports_and_a_second_apply_is_a_no_op(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    first = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--apply"])
    assert first.exit_code == 0, first.output
    assert "wrote 3 drawer(s)" in first.output

    second = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--apply"])
    assert second.exit_code == 0, second.output
    assert "wrote 0 drawer(s)" in second.output

    with _store(tmp_path) as store:
        assert len(store.list_by(limit=100)) == 3


def test_the_vault_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()
    monkeypatch.setenv("CAIRNTIR_VAULT", str(vault))

    result = runner.invoke(app, ["vault-sync", "--check"])

    assert result.exit_code == 1, result.output
    assert str(vault) in result.output


def test_no_vault_anywhere_fails_with_usage_advice(tmp_path: Path) -> None:
    _store(tmp_path).close()

    result = runner.invoke(app, ["vault-sync", "--check"])

    assert result.exit_code == 2
    combined = result.output + (result.stderr or "")
    assert "--vault" in combined
    assert "CAIRNTIR_VAULT" in combined


def test_a_directory_without_the_obsidian_marker_is_refused(tmp_path: Path) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    _store(tmp_path).close()

    result = runner.invoke(app, ["vault-sync", "--vault", str(plain), "--check"])

    assert result.exit_code == 2
    combined = result.output + (result.stderr or "")
    assert "missing .obsidian" in combined


def test_check_and_apply_together_are_refused(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    result = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check", "--apply"])

    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "read-only" in combined
    with _store(tmp_path) as store:
        assert store.list_by(limit=100) == []


# --- the wrapper script -----------------------------------------------------


def test_the_loose_script_still_runs_and_forwards_to_the_cli(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _store(tmp_path).close()

    wrapper = _load_wrapper()

    assert wrapper.main(["--vault", str(vault), "--check"]) == 1
    assert wrapper.main(["--vault", str(vault), "--apply"]) == 0
    assert wrapper.main(["--vault", str(vault), "--check"]) == 0
