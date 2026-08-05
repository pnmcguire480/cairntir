"""Seam tests: components that must agree, exercised together in one test.

The law these tests enforce (P4 of
``plans/2026-08-05-seams-cost-and-the-real-test.md``): when two components
must agree, either make them share the code that defines the agreement, or
test them together. Testing them separately is exactly how ``settle`` and
``is_open_prediction`` shipped green on both sides while disagreeing in the
middle — a prediction could be settled through the only sanctioned path and
still be counted open forever.

Each test here is the paired proof for one seam declared in
``scripts/check_seams.py``. That checker fails CI when a declared seam loses
its test, so a seam cannot quietly become unguarded again.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

from cairntir.calibration import calibration_report
from cairntir.cli import app
from cairntir.errors import ContentIntegrityError, MCPError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.vault import apply_sync, plan_sync

REPO_ROOT = Path(__file__).resolve().parents[2]

runner = CliRunner()


@pytest.fixture()
def backend(tmp_path: Path) -> Iterator[CairntirBackend]:
    with DrawerStore(tmp_path / "seams.db", HashEmbeddingProvider(dimension=32)) as store:
        yield CairntirBackend(store)


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------- settle <-> handoff (P4.1/P4.2)


def test_settling_a_prediction_closes_it_in_handoff(backend: CairntirBackend) -> None:
    """The seam itself: remember(predicted) -> settle -> handoff -> count 0.

    Both halves had passing unit tests while the system as a whole was wrong:
    ``settle`` appends an observation and leaves the original untouched (the
    only way settlement can stay honest), and ``is_open_prediction`` reads the
    original's own fields (the only way the count stays auditable). Together
    they meant every settled prediction stayed listed as open forever. The
    fix must be proven here, where both sides are visible at once.
    """
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="the settlement seam closes the loop",
        claim="settle closes the handoff loop",
        predicted_outcome="the open count drops to zero after settle",
    )

    before = backend.handoff(wing="cairntir")
    assert "1 open prediction in this wing" in before

    backend.settle(drawer_id=1, observed_outcome="the count dropped to zero")

    after = backend.handoff(wing="cairntir")
    assert "open prediction" not in after
    assert "Open predictions" not in after

    # Append-only settlement: the original is untouched, only the reading moves.
    original = backend._store.get(1)
    assert original is not None
    assert original.observed_outcome is None
    assert original.predicted_outcome == "the open count drops to zero after settle"


def test_two_divergent_observations_leave_the_prediction_open(
    backend: CairntirBackend,
) -> None:
    """A contested settlement stays open: no silent winner, not even lowest id.

    Two observations superseding the same prediction contradict each other.
    Silently taking one of them is exactly the lineage defect the temporal
    walk has, and it would hide a branch; the honest read keeps the
    prediction listed until an adjudication exists.
    """
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="a prediction two sessions will disagree about",
        predicted_outcome="the gate holds",
    )
    backend.settle(drawer_id=1, observed_outcome="the gate held")
    backend.settle(
        drawer_id=1,
        observed_outcome="the gate actually broke",
        delta="the first observation said held; the second says broke",
    )

    rendered = backend.handoff(wing="cairntir")
    assert "1 open prediction in this wing" in rendered


def test_settle_writes_a_delta_a_later_session_can_read(backend: CairntirBackend) -> None:
    """The surprise signal must survive to the next session, not die in a receipt.

    ``delta`` had never been written in the store's history. Writing it is
    only half the loop — a later session has to be able to read it back
    through the ordinary surfaces, and calibration has to see the verdict.
    """
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="anchor coverage after the backfill",
        claim="anchors land",
        predicted_outcome="coverage exceeds 60%",
    )
    backend.settle(
        drawer_id=1,
        observed_outcome="coverage reached 40.6%",
        delta="overestimated by 20 points; seven wings had no repo mapping",
    )

    later_session = CairntirBackend(backend._store)
    observation = json.loads(later_session.get(drawer_id=2))
    assert observation["delta"] == ("overestimated by 20 points; seven wings had no repo mapping")
    assert observation["supersedes_id"] == 1
    assert observation["metadata"]["success"] is False

    report = calibration_report(backend._store, wing="cairntir")
    assert report.resolved == 1
    assert report.failed == 1
    assert report.unresolved == 0


# ------------------------- write guard <-> store-health rule 3 (P4.3)

# Markers plus non-JSON trailing prose: the exact fingerprint of rule 3,
# deliberately NOT the trailing-envelope shape (rule 1), so this test pins
# the shared line between the guard and the health check, not either rule's
# private extra reach.
_LEAKED_CONTENT = (
    "a swallowed tool call\n"
    "</content>\n"
    '<parameter name="content">the lost payload\n'
    "trailing prose that is not a JSON payload"
)


def test_write_guard_and_store_health_enforce_the_same_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guard refuses before the fact what the health check reports after.

    Both draw one line: envelope markers with an empty metadata column.
    Quoted markup with metadata attached stays writable in both. That
    agreement is by design today and must never again be by memory.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    db = home / "cairntir.db"

    with DrawerStore(db, HashEmbeddingProvider(dimension=32)) as store:
        # Writer side: the guard rejects the fingerprint outright...
        with pytest.raises(ContentIntegrityError, match="no metadata"):
            store.add(Drawer(wing="cairntir", room="damage", content=_LEAKED_CONTENT))
        # ...and lets quoted markup through when metadata is attached.
        documented = store.add(
            Drawer(
                wing="cairntir",
                room="docs",
                content=_LEAKED_CONTENT,
                metadata={"note": "quoting the defect on purpose"},
            )
        )
        clean = store.add(
            Drawer(wing="cairntir", room="journey", content="ordinary", metadata={"k": "v"})
        )
    assert documented.id is not None and clean.id is not None

    # Reader side: stage the damage behind the guard the only way such rows
    # can still arise — rewriting a stored row directly, like the pre-guard
    # history did — and the health check must catch what the guard prevented.
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE drawers SET content = ?, metadata = '' WHERE id = ?",
        (_LEAKED_CONTENT, clean.id),
    )
    conn.commit()
    conn.close()

    health = _load_script("check_store_health")
    assert health.main() == 1
    out = capsys.readouterr().out
    assert f"tool-call envelope serialized into content, metadata lost: [{clean.id}]" in out


# --------------------------- parse_anchors <-> recall_for_change (P4.3)


def test_anchors_accepted_on_write_are_reachable_on_read(tmp_path: Path) -> None:
    """Every anchor shape the writer accepts, the reader must surface.

    And the writer rejects the malformed shapes, so a fresh row can never
    reach the reader malformed — a pre-guard row that already is malformed
    must be reported loudly, never skipped.
    """
    with DrawerStore(tmp_path / "anchor-seam.db", HashEmbeddingProvider(dimension=32)) as store:
        backend = CairntirBackend(store)

        backend.remember(
            wing="cairntir",
            room="architecture",
            content="why the settlement fix is one pass over the wing scan",
            anchors=[
                {"path": "src/cairntir/handoff.py", "symbol": "settled_prediction_ids"},
                {"path": "src/cairntir/mcp/backend.py"},
            ],
        )
        reply = backend.recall_for_change(files=["src/cairntir/handoff.py"])
        assert "1 anchored drawer(s)" in reply
        assert "via src/cairntir/handoff.py:settled_prediction_ids" in reply

        # The writer refuses the legacy string shape at the door.
        with pytest.raises(MCPError, match="not a list of strings"):
            backend.remember(
                wing="cairntir",
                room="architecture",
                content="bad anchors",
                anchors=["src/cairntir/cli.py"],  # type: ignore[list-item]
            )

        # A row that predates the guard and is still malformed reaches the
        # reader anyway; the reader reports it loudly instead of skipping.
        conn = sqlite3.connect(tmp_path / "anchor-seam.db")
        conn.execute(
            "UPDATE drawers SET metadata = ? WHERE id = 1",
            (json.dumps({"anchors": ["src/cairntir/handoff.py"]}),),
        )
        conn.commit()
        conn.close()

        degraded = backend.recall_for_change(files=["src/cairntir/handoff.py"])
        assert "No anchored drawers touch" in degraded
        assert "malformed metadata.anchors" in degraded
        assert "#1" in degraded


# ------------------------------ vault-sync --check <-> apply_sync (P4.3)


def _vault_with_one_walkthrough(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    note = vault / "walkthroughs" / "Triangulate" / "2026-03-30-pipeline-audit.md"
    note.parent.mkdir(parents=True)
    note.write_text("The pipeline audit found three gaps.", encoding="utf-8")
    return vault


def test_vault_check_and_apply_agree_about_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drift the check reports is exactly the drift apply removes.

    ``--check`` on one side, ``apply_sync`` on the other, and the store in
    the middle: check fails, apply writes, check passes — one sequence, both
    sides of the seam.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("CAIRNTIR_VAULT", raising=False)
    monkeypatch.setenv("CAIRNTIR_HOME", str(home))
    monkeypatch.setattr(
        "cairntir.cli.production_embedding_provider",
        lambda: HashEmbeddingProvider(dimension=384),
    )
    vault = _vault_with_one_walkthrough(tmp_path)
    DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=384)).close()

    drifted = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check"])
    assert drifted.exit_code == 1, drifted.output
    assert "DRIFT" in drifted.output

    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=384)) as store:
        written = apply_sync(store, plan_sync(store, vault))
    assert len(written) == 1

    clean = runner.invoke(app, ["vault-sync", "--vault", str(vault), "--check"])
    assert clean.exit_code == 0, clean.output
    assert "ok: every vault walkthrough has a drawer" in clean.output
