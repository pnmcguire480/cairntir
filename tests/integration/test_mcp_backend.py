"""Integration tests for the transport-free MCP backend."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from cairntir.errors import MCPError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer


@pytest.fixture()
def backend(tmp_path: Path) -> Iterator[CairntirBackend]:
    with DrawerStore(tmp_path / "mcp.db", HashEmbeddingProvider(dimension=32)) as store:
        yield CairntirBackend(store)


def test_remember_then_recall_roundtrip(backend: CairntirBackend) -> None:
    reply = backend.remember(
        wing="cairntir", room="phase-2", content="MCP server wired with 6 tools"
    )
    assert "Stored drawer #1" in reply
    assert "cairntir/phase-2" in reply

    hits = backend.recall(query="MCP server wired with 6 tools")
    assert "#1" in hits
    assert "MCP server wired" in hits


def test_recall_for_change_surfaces_anchored_drawer(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="cold start went from twelve minutes to 1.4s by defaulting to fastembed",
        metadata={
            "anchors": [
                {"path": "src/cairntir/memory/embeddings.py", "symbol": "production_provider"}
            ]
        },
    )
    backend.remember(wing="cairntir", room="identity", content="unanchored drawer")

    reply = backend.recall_for_change(files=["src/cairntir/memory/embeddings.py"])

    assert "1 anchored drawer(s)" in reply
    assert "via src/cairntir/memory/embeddings.py:production_provider" in reply
    assert "cold start" in reply
    assert "unanchored drawer" not in reply
    # Recalled content must ride inside the prompt-safety evidence boundary.
    assert "instruction_authority" in reply


def test_recall_for_change_reports_no_match_without_failing(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="anchored elsewhere",
        metadata={"anchors": [{"path": "src/cairntir/cli.py"}]},
    )
    reply = backend.recall_for_change(files=["src/cairntir/memory/store.py"])
    assert "No anchored drawers touch" in reply
    assert "Scanned 1 anchored drawer(s)" in reply


def _write_legacy_drawer(backend: CairntirBackend, metadata: dict[str, object]) -> None:
    """Write straight to the store, bypassing ``remember``'s anchor validation.

    Reproduces a drawer that entered the store before write-time validation
    existed. Those rows are real — #199 and #204-#207 in the live store — so
    the reader must keep tolerating them after the writer is guarded.
    """
    backend._store.add(
        Drawer(wing="cairntir", room="architecture", content="bad", metadata=metadata)
    )


def test_recall_for_change_warns_about_malformed_anchors(backend: CairntirBackend) -> None:
    """A malformed anchor must be visible in the reply, never silently dropped."""
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="good",
        metadata={"anchors": [{"path": "src/cairntir/cli.py"}]},
    )
    _write_legacy_drawer(backend, {"anchors": [{"symbol": "missing path"}]})
    reply = backend.recall_for_change(files=["src/cairntir/cli.py"])
    assert "WARNING" in reply
    assert "malformed metadata.anchors" in reply
    assert "#2" in reply


def test_recall_for_change_still_reads_legacy_list_of_strings_as_malformed(
    backend: CairntirBackend,
) -> None:
    """The exact live-store defect: agents wrote ``["a.py"]``, the reader rejects it.

    Guarding the writer does not retroactively fix rows already stored, and it
    must not start silently accepting them either. They stay visibly malformed
    until someone backfills them.
    """
    _write_legacy_drawer(backend, {"anchors": ["src/cairntir/cli.py"]})
    reply = backend.recall_for_change(files=["src/cairntir/cli.py"])
    assert "No anchored drawers touch" in reply
    assert "malformed metadata.anchors" in reply


def test_remember_rejects_list_of_strings_anchors(backend: CairntirBackend) -> None:
    """The defect this guard exists for: the intuitive-but-wrong anchor shape.

    Five drawers in the live store were written this way and were unreadable
    by structural recall for weeks. The write must fail loudly instead.
    """
    with pytest.raises(MCPError) as excinfo:
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="anchored with the wrong shape",
            metadata={"anchors": ["sim-core/src/tech.rs", "data/tech-tree.toml"]},
        )
    message = str(excinfo.value)
    assert "must be an object" in message
    assert '{"path"' in message, "the error must show the shape that works"
    assert "not a list of strings" in message, "the error must name the mistake made"
    assert message.isascii(), "error text reaches cp1252 consoles; keep it ASCII"


def test_remember_rejects_anchor_without_a_path(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="path"):
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="no path",
            metadata={"anchors": [{"symbol": "SentenceTransformerProvider"}]},
        )


def test_remember_rejects_anchors_that_are_not_a_list(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="must be a list"):
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="anchors as a bare string",
            metadata={"anchors": "src/cairntir/cli.py"},
        )


def test_remember_rejects_before_writing_anything(backend: CairntirBackend) -> None:
    """A rejected write must not leave a half-stored drawer behind."""
    with pytest.raises(MCPError):
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="should never be stored",
            metadata={"anchors": ["wrong/shape.py"]},
        )
    assert backend.recall(query="should never be stored", wing="cairntir").count("#") == 0


def test_remember_accepts_valid_anchors_whatever_the_separator(backend: CairntirBackend) -> None:
    """Valid anchors round-trip. Content is stored verbatim; the reader normalizes."""
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="the gdext bridge decision",
        metadata={"anchors": [{"path": ".\\src\\cairntir\\cli.py", "symbol": "main"}]},
    )
    reply = backend.recall_for_change(files=["src/cairntir/cli.py"])
    assert "1 anchored drawer(s)" in reply
    assert "WARNING" not in reply


def test_remember_without_anchors_is_unaffected(backend: CairntirBackend) -> None:
    """Anchors are optional. Metadata with no anchors key must pass untouched."""
    reply = backend.remember(
        wing="cairntir",
        room="architecture",
        content="no anchors here",
        metadata={"topic": "release", "related_drawers": [94, 95]},
    )
    assert "Stored drawer #1" in reply


@pytest.mark.parametrize("files", [[], [""], ["  "]])
def test_recall_for_change_rejects_empty_file_list(
    backend: CairntirBackend, files: list[str]
) -> None:
    with pytest.raises(MCPError, match="at least one non-empty file path"):
        backend.recall_for_change(files=files)


def test_recall_receipt_links_to_complete_verbatim_get(backend: CairntirBackend) -> None:
    content = "A deliberately long educational drawer. " + ("evidence " * 40)
    backend.remember(
        wing="cairntir",
        room="exact",
        content=content,
        metadata={"source": "test", "nested": {"verified": True}},
    )

    hits = backend.recall(query="deliberately long educational drawer")
    assert "ref=cairntir://drawer/1" in hits
    assert f"len={len(content)}" in hits
    assert f"sha256={hashlib.sha256(content.encode()).hexdigest()}" in hits
    assert "truncated=true" in hits

    payload = json.loads(backend.get(drawer_id=1))
    assert payload["resource"] == "cairntir://drawer/1"
    assert payload["content"] == content
    assert payload["content_length"] == len(content)
    assert payload["metadata"]["nested"]["verified"] is True


def test_get_missing_drawer_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="no drawer"):
        backend.get(drawer_id=999)


def test_recall_empty_query_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.recall(query="   ")


def test_remember_rejects_bad_layer(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.remember(wing="cairntir", room="x", content="y", layer="nope")


def test_session_start_renders_layers(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="who", content="Patrick owns this", layer="identity")
    backend.remember(wing="cairntir", room="state", content="phase 2 shipping", layer="essential")
    out = backend.session_start(wing="cairntir")
    assert "Identity (1)" in out
    assert "Essential (1)" in out
    assert "Patrick owns this" in out
    assert "phase 2 shipping" in out


def test_session_start_with_query_pulls_on_demand(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="notes", content="kill cross chat amnesia forever")
    out = backend.session_start(wing="cairntir", query="kill cross chat amnesia forever")
    assert "On-demand" in out
    assert "amnesia" in out


def test_discovery_ledger_surfaces_active_learning_at_session_start(
    backend: CairntirBackend,
) -> None:
    backend.remember(
        wing="cairntir",
        room="evidence",
        content="Three independent scoped retrieval tests passed.",
    )
    recorded = backend.discover(
        wing="cairntir",
        title="Scoped retrieval became reliable",
        summary="Filtering before KNN consistently preserves relevant wing-local hits.",
        novelty="cairntir",
        evidence_ids=[1],
        state="candidate",
    )
    assert "Recorded discovery #2 [candidate]" in recorded

    session = backend.session_start(wing="cairntir")
    assert "Active discoveries" in session
    assert "Scoped retrieval became reliable" in session
    assert "cairntir://drawer/1" in session

    log = backend.learning_log(wing="cairntir")
    assert "Human Learning Log" in log
    assert "Scoped retrieval became reliable" in log


def test_discovery_transition_keeps_only_current_leaf(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="evidence", content="The method repeated.")
    backend.discover(
        wing="cairntir",
        title="Method emerged",
        summary="A repeatable workflow reduced repair time.",
        novelty="user",
        evidence_ids=[1],
        state="candidate",
    )
    corroborated = backend.transition_discovery(
        drawer_id=2,
        state="corroborated",
        note="Three independent examples reproduced the method.",
    )
    assert "drawer #3" in corroborated
    transitioned = backend.transition_discovery(
        drawer_id=3,
        state="promoted",
        note="Patrick reviewed and accepted the method.",
    )
    assert "drawer #4" in transitioned
    listing = backend.discoveries(wing="cairntir")
    assert "cairntir://drawer/4" in listing
    assert "cairntir://drawer/3" not in listing
    assert "cairntir://drawer/2" not in listing
    assert "[promoted]" in listing


def test_discover_rejects_invalid_novelty(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="invalid novelty"):
        backend.discover(
            wing="cairntir",
            title="Bad novelty",
            summary="This label is unsupported.",
            novelty="world-changing",
            evidence_ids=[1],
        )


def test_timeline_filters_by_entity(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="decisions", content="decided on sqlite-vec")
    backend.remember(wing="cairntir", room="decisions", content="unrelated note")
    backend.remember(wing="cairntir", room="decisions", content="sqlite-vec benchmarks passed")

    out = backend.timeline(wing="cairntir", entity="sqlite-vec")
    assert "2 entries" in out
    assert "decided on sqlite-vec" in out
    assert "unrelated note" not in out


def test_timeline_empty_entity_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.timeline(wing="cairntir", entity="")


def test_audit_emits_quality_skill_with_essentials(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="state",
        content="phase 3 in progress",
        layer=Layer.ESSENTIAL.value,
    )
    out = backend.audit(wing="cairntir")
    assert "name: quality" in out
    assert "QUALITY — The Ship Gate" in out
    assert "essential drawers=1" in out
    assert "phase 3 in progress" in out


def test_audit_reports_empty_essential_layer(backend: CairntirBackend) -> None:
    out = backend.audit(wing="cairntir")
    assert "essential drawers=0" in out
    assert "the essential layer is empty" in out


def test_crucible_emits_skill_with_claim(backend: CairntirBackend) -> None:
    out = backend.crucible(claim="cairntir will kill amnesia")
    assert "name: crucible" in out
    assert "CRUCIBLE — The Epistemic Forge" in out
    assert "## Claim under crucible" in out
    assert "cairntir will kill amnesia" in out


def test_crucible_rejects_empty(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.crucible(claim="  ")


# ------------------------------------------------------------ v1.1: cross_recall


def test_cross_recall_searches_every_wing(backend: CairntirBackend) -> None:
    backend.remember(wing="stars-2026", room="notes", content="deterministic lockstep was key")
    backend.remember(wing="ground-zero", room="notes", content="pure engine functions — no react")
    backend.remember(wing="cairntir", room="notes", content="lazy embedder fixed cold-start")

    out = backend.cross_recall(query="pure engine functions", limit=5)
    # The query text lands in one wing but the tool reports cross-wing provenance.
    assert "across" in out and "wing(s)" in out
    assert "[ground-zero]" in out


def test_cross_recall_finds_answer_in_another_wing(backend: CairntirBackend) -> None:
    backend.remember(
        wing="stars-2026",
        room="decisions",
        content="wasm32 determinism requires f64 rounding discipline",
    )
    # Question asked while the active wing is cairntir; answer lives in stars-2026.
    out = backend.cross_recall(query="wasm32 determinism requires f64 rounding discipline")
    assert "[stars-2026]" in out


def test_cross_recall_empty_query_errors(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError):
        backend.cross_recall(query="   ")


def test_cross_recall_no_hits_is_friendly(backend: CairntirBackend) -> None:
    out = backend.cross_recall(query="nothing like this was ever stored")
    assert "No drawers matched" in out


# --- Authoring-model provenance ---------------------------------------------
#
# No host tells the MCP subprocess which model is running, so the writing agent
# is the only party that knows. It is a per-write value, never per-process: a
# model fixed at startup keeps asserting the first model after the user
# switches, which is worse than "unknown" because it looks like data.


def test_remember_records_the_authoring_model(backend: CairntirBackend) -> None:
    """The model the agent declares must reach the immutable write receipt."""
    backend.remember(
        wing="cairntir",
        room="journey",
        content="wired per-write model provenance",
        model="claude-opus-5",
    )
    receipt = backend._store.get_provenance(1)
    assert receipt is not None
    assert receipt.model == "claude-opus-5"


def test_remember_without_a_model_stays_honestly_unknown(backend: CairntirBackend) -> None:
    """Omitting it must record 'unknown', never a guess inherited from elsewhere."""
    backend.remember(wing="cairntir", room="journey", content="no model declared")
    receipt = backend._store.get_provenance(1)
    assert receipt is not None
    assert receipt.model == "unknown"


def test_two_models_in_one_session_are_recorded_separately(backend: CairntirBackend) -> None:
    """The point of per-write: one process, one session, two authoring models."""
    backend.remember(wing="cairntir", room="journey", content="first", model="gpt-5")
    backend.remember(wing="cairntir", room="journey", content="second", model="claude-opus-5")
    first = backend._store.get_provenance(1)
    second = backend._store.get_provenance(2)
    assert first is not None and second is not None
    assert (first.model, second.model) == ("gpt-5", "claude-opus-5")
    assert first.session_id == second.session_id


# --- session_start context budget (P2 item 2) -------------------------------
#
# The 2026-07-27 audit wrote "restore explicit context budgets in the v1.2 core"
# into the plan. v1.2 then shipped, was verified across three hosts, released to
# PyPI and attested WITHOUT it, and nobody noticed for five days (drawer #212).


def _fill(backend: CairntirBackend, count: int) -> None:
    for index in range(count):
        backend.remember(
            wing="cairntir",
            room="journey",
            content=f"drawer number {index} " + ("padding text " * 40),
            layer="essential",
        )


def test_session_start_without_a_budget_returns_everything(backend: CairntirBackend) -> None:
    _fill(backend, 6)
    out = backend.session_start(wing="cairntir")
    for index in range(1, 7):
        assert f"#{index}" in out
    assert "Omitted for budget" not in out


def test_session_start_honours_the_budget(backend: CairntirBackend) -> None:
    _fill(backend, 6)
    unbounded = backend.session_start(wing="cairntir")
    bounded = backend.session_start(wing="cairntir", budget_chars=1200)
    assert len(bounded) < len(unbounded)
    assert "Omitted for budget" in bounded


def test_session_start_names_what_it_omitted(backend: CairntirBackend) -> None:
    """Naming the id lets a reader spend one cairntir_get instead of guessing."""
    _fill(backend, 6)
    bounded = backend.session_start(wing="cairntir", budget_chars=1200)
    assert "cairntir_get" in bounded
    assert "cairntir_handoff" in bounded


def test_session_start_rejects_a_nonsense_budget(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="at least 1"):
        backend.session_start(wing="cairntir", budget_chars=0)


# --- Anchors as a first-class argument (P0 item 2) --------------------------
#
# The anchor contract was published and validated months ago and coverage was
# still 11%, because nothing ever ASKED for anchors -- they were buried inside a
# free-form metadata blob. A named argument is asked for; a nested key is not.


def test_remember_accepts_anchors_as_a_first_class_argument(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir",
        room="architecture",
        content="the gdext bridge decision",
        anchors=[{"path": "src/cairntir/cli.py", "symbol": "main"}],
    )
    reply = backend.recall_for_change(files=["src/cairntir/cli.py"])
    assert "1 anchored drawer(s)" in reply
    assert "WARNING" not in reply


def test_remember_rejects_anchors_given_two_ways(backend: CairntirBackend) -> None:
    """Two spellings of one thing is the drift Cairntir exists to oppose."""
    with pytest.raises(MCPError, match="not both"):
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="ambiguous",
            anchors=[{"path": "src/cairntir/cli.py"}],
            metadata={"anchors": [{"path": "src/cairntir/handoff.py"}]},
        )


def test_remember_validates_first_class_anchors_too(backend: CairntirBackend) -> None:
    """The named argument must not be a way around the shape contract."""
    with pytest.raises(MCPError, match="must be an object"):
        backend.remember(
            wing="cairntir",
            room="architecture",
            content="wrong shape",
            anchors=["src/cairntir/cli.py"],  # type: ignore[list-item]
        )


def test_remember_nudges_when_a_drawer_names_files_but_has_no_anchors(
    backend: CairntirBackend,
) -> None:
    """Fire at the moment of omission, naming the paths the drawer just mentioned."""
    reply = backend.remember(
        wing="cairntir",
        room="architecture",
        content="rewrote src/cairntir/handoff.py to honour the budget",
    )
    assert "Stored drawer #1" in reply
    assert "no anchors" in reply
    assert "src/cairntir/handoff.py" in reply


def test_remember_does_not_nudge_when_anchors_are_present(backend: CairntirBackend) -> None:
    reply = backend.remember(
        wing="cairntir",
        room="architecture",
        content="rewrote src/cairntir/handoff.py",
        anchors=[{"path": "src/cairntir/handoff.py"}],
    )
    assert "no anchors" not in reply


def test_remember_does_not_nudge_a_drawer_about_no_file(backend: CairntirBackend) -> None:
    """Plenty of drawers are legitimately about nothing on disk. Stay quiet."""
    reply = backend.remember(
        wing="cairntir", room="working-preferences", content="Patrick prefers one path, not a menu"
    )
    assert "NOTE:" not in reply


# --- Predictions: writable, and settleable (P1) ------------------------------
#
# claim/predicted_outcome/observed_outcome/delta have existed since v0.2 and
# were used twice in 278 rows; delta had never been written once. Nothing in the
# write path asked for a prediction, and nothing could close one.


def test_remember_writes_a_falsifiable_prediction(backend: CairntirBackend) -> None:
    reply = backend.remember(
        wing="cairntir",
        room="predictions",
        content="anchor backfill will raise coverage",
        claim="verified backfill lifts structural recall above 40%",
        predicted_outcome="coverage exceeds 40% after the run",
    )
    assert "Open prediction" in reply
    stored = backend._store.get(1)
    assert stored is not None
    assert stored.claim == "verified backfill lifts structural recall above 40%"
    assert stored.predicted_outcome == "coverage exceeds 40% after the run"
    assert stored.observed_outcome is None


def test_remember_rejects_an_empty_prediction(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="falsifiable"):
        backend.remember(
            wing="cairntir", room="predictions", content="hollow", predicted_outcome="   "
        )


def test_settle_appends_and_leaves_the_original_untouched(backend: CairntirBackend) -> None:
    """A store that rewrites its own predictions cannot check whether it was right."""
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="the prediction",
        claim="c",
        predicted_outcome="coverage exceeds 40%",
    )
    before = backend._store.get(1)
    assert before is not None

    reply = backend.settle(drawer_id=1, observed_outcome="coverage reached 40.6%")

    after = backend._store.get(1)
    assert after is not None
    assert after.content == before.content, "the original prediction must not be rewritten"
    assert after.observed_outcome is None

    observation = backend._store.get(2)
    assert observation is not None
    assert observation.supersedes_id == 1
    assert observation.observed_outcome == "coverage reached 40.6%"
    assert observation.wing == before.wing and observation.room == before.room
    assert "held" in reply


def test_settle_writes_delta(backend: CairntirBackend) -> None:
    """The surprise signal. Never written once in the store's entire history."""
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="the prediction",
        predicted_outcome="coverage exceeds 60%",
    )
    reply = backend.settle(
        drawer_id=1,
        observed_outcome="coverage reached 40.6%",
        delta="overestimated by 20 points; most wings had no repo mapping",
    )
    observation = backend._store.get(2)
    assert observation is not None
    assert observation.delta == "overestimated by 20 points; most wings had no repo mapping"
    assert "did NOT hold" in reply


def test_settle_carries_the_predictions_anchors_forward(backend: CairntirBackend) -> None:
    """The outcome must stay reachable from a diff, not go dark when it matters most."""
    backend.remember(
        wing="cairntir",
        room="predictions",
        content="the prediction",
        predicted_outcome="the guard rejects tool-call markup",
        anchors=[{"path": "src/cairntir/memory/store.py", "symbol": "add"}],
    )
    backend.settle(drawer_id=1, observed_outcome="it does")
    reply = backend.recall_for_change(files=["src/cairntir/memory/store.py"])
    assert "2 anchored drawer(s)" in reply


def test_settle_rejects_a_drawer_carrying_no_prediction(backend: CairntirBackend) -> None:
    backend.remember(wing="cairntir", room="journey", content="just a note")
    with pytest.raises(MCPError, match="nothing to settle"):
        backend.settle(drawer_id=1, observed_outcome="whatever")


def test_settle_rejects_a_missing_drawer(backend: CairntirBackend) -> None:
    with pytest.raises(MCPError, match="does not exist"):
        backend.settle(drawer_id=999, observed_outcome="whatever")


def test_settle_rejects_an_empty_observation(backend: CairntirBackend) -> None:
    backend.remember(
        wing="cairntir", room="predictions", content="p", predicted_outcome="something"
    )
    with pytest.raises(MCPError, match="what actually happened"):
        backend.settle(drawer_id=1, observed_outcome="  ")


def test_blank_model_does_not_overwrite_the_receipt(backend: CairntirBackend) -> None:
    """Whitespace is not a declaration. Fall back rather than store an empty string."""
    backend.remember(wing="cairntir", room="journey", content="blank", model="   ")
    receipt = backend._store.get_provenance(1)
    assert receipt is not None
    assert receipt.model == "unknown"
