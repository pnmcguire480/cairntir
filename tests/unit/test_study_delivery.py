"""R13: staging the study export for a notebook, and updating it without duplicates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from cairntir import study
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

CATEGORIES = ("patterns", "rules", "walkthroughs", "projects")
WING = "r13-delivery"
KEY = "r13-notebook"
OLD = datetime(2020, 2, 3, 4, 5, 6, tzinfo=UTC)


def put(store, body, *, room="patterns", supersedes=None):
    return store.add(
        Drawer(wing=WING, room=room, content=body, created_at=OLD, supersedes_id=supersedes)
    )


@pytest.fixture
def case(tmp_path):
    owner = DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(32), automatic_backups=False)
    drawers = {
        category: put(
            owner, f"MARKER-{category.upper()}-ONE: synthetic {category} text.", room=category
        )
        for category in CATEGORIES
    }
    selection = {c: [owner.portable_identity(d.id)] for c, d in drawers.items()}
    yield SimpleNamespace(
        owner=owner,
        drawers=drawers,
        selection=selection,
        output=tmp_path / "study",
        dest=tmp_path / "deliver",
    )
    owner.close()


def export(case, selection=None):
    return study.export_study_sources(
        case.owner,
        wing=WING,
        notebook_key=KEY,
        selection=selection or case.selection,
        output=case.output,
    )


def supersede(case, category, selection):
    new = put(
        case.owner,
        f"MARKER-{category.upper()}-TWO: synthetic {category} text, revised.",
        room=category,
        supersedes=case.drawers[category].id,
    )
    case.drawers[category] = new
    selection[category] = [case.owner.portable_identity(new.id)]


def current_bytes(case):
    snap = study.read_study_sources(case.output)
    return {c: Path(p).read_bytes() for c, p in snap["paths"].items()}


def write_json(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


class Notebook:
    """A stand-in for a NotebookLM notebook: source name -> content."""

    def __init__(self):
        self.sources: dict[str, bytes] = {}

    def apply(self, result, files=None):
        files = files if files is not None else self.read(result)
        for row in result["plan"]:
            if row["action"] == "keep":
                assert row["name"] in self.sources, "plan kept a source the notebook lacks"
                continue
            if row["remove"] is not None:
                del self.sources[row["remove"]]
            assert row["upload"] not in self.sources, "plan uploads a duplicate"
            self.sources[row["upload"]] = files[row["upload"]]

    @staticmethod
    def read(result):
        return {
            row["upload"]: Path(result["destination"], row["upload"]).read_bytes()
            for row in result["plan"]
            if row["upload"]
        }

    def assert_matches(self, case):
        expected = current_bytes(case)
        assert len(self.sources) == 4, f"expected four sources, found {sorted(self.sources)}"
        for category in CATEGORIES:
            held = [d for n, d in self.sources.items() if n.startswith(f"{category}-")]
            assert held == [expected[category]], f"{category} is duplicated, missing or stale"


def actions(result):
    return {row["category"]: row["action"] for row in result["plan"]}


def test_first_delivery_stages_four_named_files_and_plans_add(case):
    export(case)
    result = study.stage_notebook_delivery(case.output, case.dest)
    assert actions(result) == dict.fromkeys(CATEGORIES, "add")
    expected = current_bytes(case)
    names = {p.name for p in case.dest.iterdir()} - {"DELIVERED.json"}
    assert len(names) == 4
    for row in result["plan"]:
        assert row["name"] == f"{row['category']}-{row['revision'][:12]}.md"
        assert (case.dest / row["name"]).read_bytes() == expected[row["category"]]
        assert row["remove"] is None and row["upload"] == row["name"]
    assert result["notebooklm"] == {"status": "UNVERIFIED"}
    notebook = Notebook()
    notebook.apply(result)
    notebook.assert_matches(case)


def test_update_replaces_only_changed_categories_without_duplicates(case):
    export(case)
    notebook = Notebook()
    first = study.stage_notebook_delivery(case.output, case.dest)
    notebook.apply(first)
    old = {row["category"]: row["name"] for row in first["plan"]}
    selection = {c: list(v) for c, v in case.selection.items()}
    supersede(case, "rules", selection)
    supersede(case, "projects", selection)
    export(case, selection)
    second = study.stage_notebook_delivery(case.output, case.dest)
    assert actions(second) == {
        "patterns": "keep",
        "rules": "replace",
        "walkthroughs": "keep",
        "projects": "replace",
    }
    for row in second["plan"]:
        if row["action"] == "replace":
            assert row["remove"] == old[row["category"]] and row["upload"] != row["remove"]
    notebook.apply(second)
    notebook.assert_matches(case)
    on_disk = {p.name for p in case.dest.iterdir()} - {"DELIVERED.json"}
    assert on_disk == {row["name"] for row in second["plan"]}
    rules = next(d for n, d in notebook.sources.items() if n.startswith("rules-")).decode()
    current, _, history = rules.partition("## Cited history")
    assert "MARKER-RULES-TWO" in current and "MARKER-RULES-ONE" not in current
    assert "MARKER-RULES-ONE" in history  # superseded text survives only as marked history


def test_repeat_delivery_with_no_change_keeps_everything_and_touches_nothing(case):
    export(case)
    study.stage_notebook_delivery(case.output, case.dest)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in case.dest.iterdir()}
    again = study.stage_notebook_delivery(case.output, case.dest)
    assert actions(again) == dict.fromkeys(CATEGORIES, "keep")
    assert all(row["upload"] is None and row["remove"] is None for row in again["plan"])
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in case.dest.iterdir()}
    assert after == before


def test_broken_control_upload_without_removing_is_detected(case):
    export(case)
    notebook = Notebook()
    notebook.apply(study.stage_notebook_delivery(case.output, case.dest))
    selection = {c: list(v) for c, v in case.selection.items()}
    supersede(case, "patterns", selection)
    export(case, selection)
    plan = study.stage_notebook_delivery(case.output, case.dest)
    for row in plan["plan"]:
        row["remove"] = None  # broken: forgets to delete the old source
    notebook.apply(plan)
    with pytest.raises(AssertionError, match="expected four sources"):
        notebook.assert_matches(case)


def test_broken_control_stale_plan_is_detected(case):
    export(case)
    first = study.stage_notebook_delivery(case.output, case.dest)
    first_files = Notebook.read(first)
    selection = {c: list(v) for c, v in case.selection.items()}
    supersede(case, "walkthroughs", selection)
    export(case, selection)
    study.stage_notebook_delivery(case.output, case.dest)
    notebook = Notebook()
    notebook.apply(first, first_files)  # broken: the notebook only ever saw the first plan
    with pytest.raises(AssertionError, match="walkthroughs is duplicated, missing or stale"):
        notebook.assert_matches(case)


def test_missing_or_tampered_export_is_refused_and_stages_nothing(case):
    with pytest.raises(study.StudyExportError):
        study.stage_notebook_delivery(case.output, case.dest)
    assert not case.dest.exists()
    export(case)
    snap = study.read_study_sources(case.output)
    Path(snap["paths"]["rules"]).write_bytes(b"tampered")
    with pytest.raises(study.StudyExportError):
        study.stage_notebook_delivery(case.output, case.dest)
    assert not case.dest.exists()


def test_foreign_files_and_other_notebook_records_are_refused(case):
    export(case)
    case.dest.mkdir()
    (case.dest / "my-notes.txt").write_text("not ours")
    with pytest.raises(study.StudyExportError, match="does not own"):
        study.stage_notebook_delivery(case.output, case.dest)
    (case.dest / "my-notes.txt").unlink()
    study.stage_notebook_delivery(case.output, case.dest)
    path = case.dest / "DELIVERED.json"
    record = json.loads(path.read_bytes())
    write_json(path, {**record, "notebook_key": "someone-else"})
    with pytest.raises(study.StudyExportError, match="another notebook"):
        study.stage_notebook_delivery(case.output, case.dest)
    write_json(path, {**record, "sources": {"patterns": "../escape.md"}})
    with pytest.raises(study.StudyExportError, match="delivery record is invalid"):
        study.stage_notebook_delivery(case.output, case.dest)


def test_cli_prints_plan_in_plain_words_and_as_json(case, monkeypatch):
    from typer.testing import CliRunner

    from cairntir import cli

    monkeypatch.setenv("CAIRNTIR_HOME", str(case.output.parent / "home"))
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")
    export(case)
    args = ["study-deliver", "--output", str(case.output), "--destination", str(case.dest)]
    first = CliRunner().invoke(cli.app, args)
    assert first.exit_code == 0, first.output
    assert first.stdout.count("upload   ") == 4 and "remove" not in first.stdout
    assert "UNVERIFIED" in first.stdout
    selection = {c: list(v) for c, v in case.selection.items()}
    supersede(case, "rules", selection)
    export(case, selection)
    second = CliRunner().invoke(cli.app, [*args, "--json"])
    assert second.exit_code == 0, second.output
    plan = json.loads(second.stdout)
    assert actions(plan)["rules"] == "replace" and actions(plan)["patterns"] == "keep"
    missing = ["study-deliver", "--output", str(case.output / "nope"), "--destination"]
    assert CliRunner().invoke(cli.app, [*missing, str(case.dest)]).exit_code == 1
