"""Transport-free backend for Cairntir's MCP tools.

The backend wraps a :class:`~cairntir.memory.store.DrawerStore` and a
:class:`~cairntir.memory.retrieval.Retriever` with pure-Python methods, one
per MCP tool. The MCP :mod:`cairntir.mcp.server` module is a thin adapter
that turns JSON-RPC calls into method invocations and text replies.

Keeping the backend transport-free lets the unit tests invoke tools directly
without needing to stand up a stdio server.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from cairntir.calibration import calibration_report, render_calibration
from cairntir.codeglass import (
    READER_LEVELS,
    TEACH_BACK_PHASES,
    TeachBackResponse,
    record_teachback,
    record_walkthrough,
    render_retention,
    retention_report,
    walkthrough_fingerprint,
)
from cairntir.durability import request_hash
from cairntir.errors import AnchorError, MCPError
from cairntir.handoff import DEFAULT_BUDGET_CHARS, Handoff
from cairntir.handoff import compose as compose_handoff
from cairntir.learning import (
    DISCOVERY_STATES,
    NOVELTY_SCOPES,
    format_discoveries,
    human_learning_log,
    list_discoveries,
    propose_multi_episode_discoveries,
    record_discovery,
    transition_discovery,
)
from cairntir.memory.anchors import ANCHORS_KEY, extract_path_candidates, parse_anchors
from cairntir.memory.anchors import recall_for_change as anchors_recall_for_change
from cairntir.memory.retrieval import RetrievalResult, Retriever
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.prompt_safety import (
    EVIDENCE_BOUNDARY,
    assess_memory_content,
    render_evidence_block,
    render_memory_evidence,
)
from cairntir.provenance import WriteProvenance
from cairntir.skills import load_skill

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore


ANCHOR_SHAPE_HINT = (
    'Anchors must be a list of objects like [{"path": "src/cairntir/cli.py", '
    '"symbol": "main"}], not a list of strings. Only "path" is required'
)
"""Correct anchor shape, appended to every anchor rejection.

The original defect was not that agents wrote bad anchors; it was that
nothing ever told them the shape. The error message is the one place a
writing agent is guaranteed to read, so it carries the contract.
"""


def _anchor_nudge(content: str, metadata: dict[str, Any]) -> str:
    """Return a reminder when a drawer names code files but carries no anchors.

    Anchors are the only retrieval path that needs no good question from the
    reader, and they were on 11% of the store because **nothing ever asked for
    them**. The tool description states the contract, but a description is read
    once and forgotten; this fires at the exact moment the omission happens,
    naming the paths the drawer itself just mentioned.

    Advisory only. The write already succeeded — a drawer stored without
    anchors is worth more than a drawer refused over a nicety, and plenty of
    drawers are legitimately about no file at all.
    """
    if metadata.get(ANCHORS_KEY):
        return ""
    candidates = extract_path_candidates(content)
    if not candidates:
        return ""
    shown = ", ".join(candidates[:3])
    return (
        f"\nNOTE: this drawer mentions {shown} but carries no anchors, so "
        "cairntir_recall_for_change will never surface it from a diff. "
        f"Add them with: cairntir anchor {{id}} -p <path>"
    )


def _prediction_nudge(claim: str | None, predicted_outcome: str | None) -> str:
    """Return a reminder when a drawer asserts a claim but carries no prediction.

    The claim says what the drawer asserts; ``predicted_outcome`` says what
    would prove it wrong. The second is what lets ``cairntir_settle`` ever
    measure the first — and deltas were still 0/292 eight days after settle
    landed, for the exact reason anchors were at 11%: **nothing ever asked**.
    Same fix shape as :func:`_anchor_nudge`: fire at the moment of the
    omission, advisory only, never fatal.
    """
    if predicted_outcome or not (claim and claim.strip()):
        return ""
    return (
        "\nNOTE: this drawer asserts a claim without a predicted_outcome, so "
        "nothing can ever settle it or write a delta for it. When the claim "
        "is load-bearing, pass predicted_outcome too: what would prove it "
        "wrong?"
    )


class CairntirBackend:
    """Transport-free implementation of Cairntir's MCP tools."""

    def __init__(self, store: DrawerStore) -> None:
        """Create a backend over an existing :class:`DrawerStore`."""
        self._store = store
        self._retriever = Retriever(store)

    # ------------------------------------------------------------------ tools

    def remember(
        self,
        *,
        wing: str,
        room: str,
        content: str,
        layer: str = "on_demand",
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        anchors: list[dict[str, Any]] | None = None,
        claim: str | None = None,
        predicted_outcome: str | None = None,
    ) -> str:
        """Store a verbatim drawer. Returns a human-readable confirmation."""
        try:
            layer_enum = Layer(layer)
        except ValueError as exc:
            raise MCPError(
                f"invalid layer {layer!r}; expected one of {[x.value for x in Layer]}"
            ) from exc

        merged = dict(metadata or {})
        if anchors is not None:
            # Two ways to say the same thing is exactly the drift Cairntir
            # exists to oppose, so refuse rather than silently pick a winner.
            if ANCHORS_KEY in merged:
                raise MCPError(
                    "pass anchors either as the 'anchors' argument or as metadata.anchors, not both"
                )
            merged[ANCHORS_KEY] = anchors
        if merged:
            # Fail here, not weeks later in recall_for_change. An agent that
            # guesses the anchor shape wrong gets a correctable error inside
            # the session that wrote it; the alternative is a silent bad row
            # and a warning in a different tool, in a different chat, about a
            # drawer nobody can reconstruct from memory.
            try:
                parse_anchors(merged)
            except AnchorError as exc:
                raise MCPError(f"{exc}. {ANCHOR_SHAPE_HINT}") from exc

        if predicted_outcome is not None and not predicted_outcome.strip():
            raise MCPError("predicted_outcome must be a falsifiable prediction, not empty")

        drawer = Drawer(
            wing=wing,
            room=room,
            content=content,
            layer=layer_enum,
            metadata=merged,
            claim=claim,
            predicted_outcome=predicted_outcome,
        )
        saved = self._store.add(drawer, model=model)
        reply = (
            f"Stored drawer #{saved.id} in {saved.wing}/{saved.room} "
            f"(layer={saved.layer.value}, ref={_drawer_ref(saved)})."
        )
        if predicted_outcome:
            reply += f" Open prediction — settle it with cairntir_settle({saved.id}, ...)."
        return reply + _anchor_nudge(content, merged) + _prediction_nudge(claim, predicted_outcome)

    @staticmethod
    def _verdict_phrase(verdict: bool | None) -> str:
        """Render the three-state verdict without ever guessing the third."""
        if verdict is True:
            return "held"
        if verdict is False:
            return "did NOT hold"
        return "was not scored (a delta was written with no verdict)"

    def settle(
        self,
        *,
        drawer_id: int,
        observed_outcome: str,
        held: bool | None = None,
        delta: str | None = None,
        model: str | None = None,
    ) -> str:
        """Close an open prediction by recording what actually happened.

        Settles by **appending**, never by rewriting. The original prediction
        is left exactly as written and a new observation drawer supersedes it,
        which is the same contract ``ReasonLoop.step`` has used since v0.6 and
        the reason verbatim content can be called a floor at all. A store that
        edits its own predictions after the fact cannot be used to check
        whether it was right.

        ``held`` is the verdict and ``delta`` is the surprise. They are
        **different questions**, and conflating them was a real defect
        (drawer #342, fixed 2026-08-10). Until this fix the verdict was
        derived from delta presence alone — ``held = not delta`` — so writing
        an honest note about a surprising *route* to a correct outcome
        silently recorded that correct prediction as a miss. The incentive
        ran backwards: an agent wanting good calibration numbers was pushed to
        omit exactly the surprise signal ``delta`` exists to capture, and which
        the v0.4 design calls "the gradient when there are no weights."

        Resolution order, and none of it infers a verdict from prose:

        * ``held`` given — authoritative. Write a delta freely; a correct
          prediction reached by a surprising path stays correct.
        * ``held`` omitted, no delta — the prediction held. Unchanged
          behaviour, and still the common case.
        * ``held`` omitted, delta given — **the verdict is unknown and is not
          recorded.** ``metadata["success"]`` is left off entirely rather than
          guessed, so ``cairntir_calibration`` skips the observation instead of
          counting a fabricated one. The reply says so and asks for ``held``.
          Not counting beats counting wrong.

        The verdict, when known, is persisted as ``metadata["success"]`` — the
        same field ``ReasonLoop.step`` has written since v0.6 and the one
        calibration already reads, so both sanctioned settlement paths keep one
        shape, the original prediction stays immutable, and no schema changes.
        """
        if not observed_outcome.strip():
            raise MCPError("observed_outcome must say what actually happened")
        prediction = self._store.get(drawer_id)
        if prediction is None:
            raise MCPError(f"drawer {drawer_id} does not exist")
        if not (prediction.predicted_outcome or "").strip():
            raise MCPError(
                f"drawer {drawer_id} carries no predicted_outcome, so there is "
                "nothing to settle. Predictions are written with "
                "cairntir_remember(predicted_outcome=...)"
            )

        has_delta = bool(delta and delta.strip())
        # The verdict is only ever stated, never inferred from prose — the one
        # constraint drawer #342 made binding. `held is None and has_delta` is
        # the genuinely ambiguous case, and it stays ambiguous on the record.
        verdict: bool | None = held if held is not None else (None if has_delta else True)
        body = "\n".join(
            [
                f"SETTLED the prediction in drawer #{drawer_id}.",
                f"CLAIM: {prediction.claim or '(none recorded)'}",
                f"PREDICTED: {prediction.predicted_outcome}",
                f"OBSERVED: {observed_outcome}",
                f"DELTA: {delta if has_delta else 'none'}",
                f"VERDICT: the prediction {self._verdict_phrase(verdict)}.",
            ]
        )
        # Carry the prediction's own anchors onto the observation. They were
        # validated when the prediction was written and describe the same code,
        # so the outcome stays reachable from a diff instead of going dark the
        # moment it matters most. ``success`` is the verdict derivable from the
        # delta contract — no delta means the prediction held — persisted in
        # the exact field calibration already counts, which is how the reason
        # loop has settled since v0.6. One shape for both settlement paths.
        #
        # `success` is omitted entirely when the verdict is unknown. Calibration
        # counts only observations whose `success` is a bool, so an omitted key
        # is skipped rather than scored — the honest answer, and the reason this
        # fix needs no calibration change at all.
        metadata: dict[str, Any] = {"settles": drawer_id}
        if verdict is not None:
            metadata["success"] = verdict
        if prediction.metadata.get(ANCHORS_KEY):
            metadata[ANCHORS_KEY] = prediction.metadata[ANCHORS_KEY]

        saved = self._store.add(
            Drawer(
                wing=prediction.wing,
                room=prediction.room,
                content=body,
                layer=prediction.layer,
                metadata=metadata,
                claim=prediction.claim,
                predicted_outcome=prediction.predicted_outcome,
                observed_outcome=observed_outcome,
                delta=delta if has_delta else None,
                supersedes_id=drawer_id,
            ),
            model=model,
        )
        reply = (
            f"Settled drawer #{drawer_id}: the prediction {self._verdict_phrase(verdict)}. "
            f"Observation stored as drawer #{saved.id} (ref={_drawer_ref(saved)}), "
            f"superseding #{drawer_id}. The original is unchanged."
        )
        if verdict is None:
            reply += (
                " The delta was recorded but the verdict was not, because a delta means"
                " 'something surprised me', not 'the prediction was wrong' — a correct"
                " prediction reached by a surprising path is still correct. Calibration"
                " skips this observation. Pass held=True or held=False to score it."
            )
        return reply

    def get(self, *, drawer_id: int) -> str:
        """Return one complete drawer as stable, structured JSON."""
        drawer = self._store.get(drawer_id)
        if drawer is None:
            raise MCPError(f"no drawer with id {drawer_id}")
        provenance = self._required_provenance(drawer_id)
        assessment = assess_memory_content(drawer.content)
        payload = {
            "resource": _drawer_ref(drawer),
            "id": drawer.id,
            "wing": drawer.wing,
            "room": drawer.room,
            "layer": drawer.layer.value,
            "content": drawer.content,
            "content_length": len(drawer.content),
            "content_hash": _content_hash(drawer.content),
            "metadata": drawer.metadata,
            "created_at": drawer.created_at.isoformat(),
            "claim": drawer.claim,
            "predicted_outcome": drawer.predicted_outcome,
            "observed_outcome": drawer.observed_outcome,
            "delta": drawer.delta,
            "supersedes_id": drawer.supersedes_id,
            "belief_mass": drawer.belief_mass,
            "provenance": provenance.to_dict(),
            "instruction_authority": "none",
            "suspicious": assessment.suspicious,
            "security_signals": list(assessment.signals),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    def recall(
        self,
        *,
        query: str,
        wing: str | None = None,
        room: str | None = None,
        limit: int = 10,
        full_content: int = 0,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
    ) -> str:
        """Semantic search. Returns a formatted list of hits.

        ``full_content`` returns the top N hits with their **complete**
        content in the evidence block instead of a snippet. One good drawer
        beats ten headlines, and it removes the ``get`` round trip for the
        hits that actually answer the question. Whole drawers or none: a hit
        too large to deliver whole is named, never truncated. The default of
        0 keeps today's stub-only output byte-identical.

        ``budget_chars`` is a **cumulative** ceiling across everything
        delivered whole, the same contract
        :func:`cairntir.handoff.compose` has always kept. It is the whole
        point of the v1.3 context-budget release, and full content shipped
        without it: the size test used to be per drawer against the same
        constant, so ``full_content=10`` over ten 11,900-character drawers
        delivered ~119,000 characters while every drawer individually
        "fit". Once the budget is spent the remaining hits fall back to
        snippets and are named with their ids, exactly as an oversize hit is.

        The parameter is deliberately **not** published in the
        ``cairntir_recall`` tool schema yet. The ceiling is what fixes the
        defect; the tunable is new surface, and new surface makes a MINOR
        under ``docs/release-cadence.md``. It exists here so the bound is
        testable at small sizes, and so the next MINOR can expose it by
        adding the property and nothing else.
        """
        if not query.strip():
            raise MCPError("recall requires a non-empty query")
        if full_content < 0:
            raise MCPError("full_content must be zero or positive")
        if budget_chars < 1:
            raise MCPError("budget_chars must be positive")
        hits = self._store.search(query, wing=wing, room=room, limit=limit)
        if not hits:
            return f"No drawers matched {query!r}."
        lines = [f"{len(hits)} hit(s) for {query!r}:"]
        evidence: list[str] = []
        spent = 0
        for index, (drawer, distance) in enumerate(hits):
            wants_full = index < full_content
            size = len(drawer.content)
            remaining = budget_chars - spent
            fits = size <= remaining
            served_full = wants_full and fits
            if served_full:
                spent += size
            note = ""
            if wants_full and not fits:
                reason = (
                    f"too large for full delivery: {size} chars"
                    if size > budget_chars
                    else f"budget spent: needs {size} chars, {remaining} left"
                )
                note = f"  ({reason} — {_drawer_ref(drawer)} via cairntir_get)"
            lines.append(
                f"  #{drawer.id}  {drawer.wing}/{drawer.room}  "
                f"[{drawer.layer.value}]  d={distance:.4f}  "
                f"{_content_receipt(drawer, full=served_full)}{note}"
            )
            evidence.append(
                render_memory_evidence(
                    drawer,
                    self._required_provenance(drawer.id),
                    content=drawer.content if served_full else _snippet(drawer.content),
                )
            )
        if full_content:
            lines.insert(1, f"  full content: {spent:,}/{budget_chars:,} chars used.")
        return "\n".join(lines) + "\n\n" + render_evidence_block(evidence)

    def cross_recall(self, *, query: str, limit: int = 10) -> str:
        """Semantic search over *every* wing. Returns hits annotated by wing.

        Where :meth:`recall` scopes to a single wing by default, this
        method intentionally does not — a question asked in one
        project can find its answer in another. The output groups the
        wing-of-origin count in the header so the caller sees at a
        glance how widely the memory reached.
        """
        if not query.strip():
            raise MCPError("cross_recall requires a non-empty query")
        hits = self._store.search(query, limit=limit)
        if not hits:
            return f"No drawers matched {query!r} in any wing."
        wings_seen = {d.wing for d, _ in hits}
        lines = [f"{len(hits)} hit(s) across {len(wings_seen)} wing(s) for {query!r}:"]
        evidence: list[str] = []
        for drawer, distance in hits:
            lines.append(
                f"  #{drawer.id}  [{drawer.wing}]  {drawer.room}  "
                f"[{drawer.layer.value}]  d={distance:.4f}  "
                f"{_content_receipt(drawer)}"
            )
            evidence.append(
                render_memory_evidence(
                    drawer,
                    self._required_provenance(drawer.id),
                    content=_snippet(drawer.content),
                )
            )
        return "\n".join(lines) + "\n\n" + render_evidence_block(evidence)

    def recall_for_change(
        self,
        *,
        files: list[str],
        wing: str | None = None,
        rooms: list[str] | None = None,
        limit: int = 20,
    ) -> str:
        """Structural recall: surface drawers anchored to the files being changed.

        Where :meth:`recall` answers a question the caller thought to ask,
        this answers one they did not — given a diff, it returns the memory
        already attached to those files. A drawer participates only if
        someone gave it an ``metadata.anchors`` entry, so silence here means
        "nothing was ever written about these files," not "nothing matched."

        Deliberately does **not** flag staleness. See
        :mod:`cairntir.memory.anchors` for why that is held.
        """
        if not files or not any(f.strip() for f in files):
            raise MCPError("recall_for_change requires at least one non-empty file path")
        result = anchors_recall_for_change(self._store, files, wing=wing, rooms=rooms, limit=limit)
        scope = f" in wing {wing!r}" if wing else ""
        if not result.matches:
            base = (
                f"No anchored drawers touch those {len(files)} file(s){scope}. "
                f"Scanned {result.scanned} anchored drawer(s)."
            )
            return base + _malformed_note(result.malformed_drawer_ids)

        lines = [
            f"{len(result.matches)} anchored drawer(s) touch those {len(files)} file(s){scope}:"
        ]
        evidence: list[str] = []
        for match in result.matches:
            drawer = match.drawer
            where = ", ".join(
                a.path if a.symbol is None else f"{a.path}:{a.symbol}" for a in match.anchors
            )
            lines.append(
                f"  #{drawer.id}  {drawer.wing}/{drawer.room}  "
                f"[{drawer.layer.value}]  via {where}  {_content_receipt(drawer)}"
            )
            evidence.append(
                render_memory_evidence(
                    drawer,
                    self._required_provenance(drawer.id),
                    content=_snippet(drawer.content),
                )
            )
        body = "\n".join(lines) + _malformed_note(result.malformed_drawer_ids)
        return body + "\n\n" + render_evidence_block(evidence)

    def handoff(
        self,
        *,
        wing: str,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
        files: list[str] | None = None,
        max_deltas: int = 8,
    ) -> str:
        """Compose one bounded brief for ``wing`` — the replacement for HANDOFF.md.

        Where :meth:`session_start` answers "what is in this wing?" with a
        stub per drawer, this answers "what do I need to start working?"
        with whole drawers and a hard ceiling. Drawers that do not fit are
        named, never cut. See :mod:`cairntir.handoff`.
        """
        try:
            brief = compose_handoff(
                self._store,
                wing=wing,
                budget_chars=budget_chars,
                files=files,
                max_deltas=max_deltas,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        return _format_handoff(brief, store=self._store)

    def session_start(
        self, *, wing: str, query: str | None = None, budget_chars: int | None = None
    ) -> str:
        """Load 4-layer context plus active learning signals for ``wing``.

        ``budget_chars`` caps the returned drawer content. Prefer
        :meth:`handoff`, which is bounded by default and composes an actual
        brief; this remains the exhaustive listing.
        """
        if budget_chars is not None and budget_chars < 1:
            raise MCPError("budget_chars must be at least 1")
        result = self._retriever.load(wing=wing, query=query, include_deep=False)
        context = _format_retrieval(wing, result, store=self._store, budget_chars=budget_chars)
        active = list_discoveries(self._store, wing=wing, active_only=True, limit=5)
        if not active:
            return context
        records: list[str] = []
        for discovery in active:
            drawer = self._store.get(discovery.drawer_id)
            if drawer is None:
                raise MCPError(f"discovery drawer {discovery.drawer_id} is missing")
            records.append(
                render_memory_evidence(
                    drawer,
                    self._required_provenance(discovery.drawer_id),
                )
            )
        return (
            context
            + "\n# Active discoveries — tell the user what Cairntir is learning\n\n"
            + render_evidence_block(records)
            + "\n"
        )

    def discover(
        self,
        *,
        wing: str,
        title: str,
        summary: str,
        novelty: str,
        evidence_ids: list[int],
        state: str = "signal",
    ) -> str:
        """Record an evidence-backed emergent pattern in the Discovery Ledger."""
        if novelty not in NOVELTY_SCOPES:
            raise MCPError(f"invalid novelty {novelty!r}; expected one of {NOVELTY_SCOPES}")
        if state not in DISCOVERY_STATES:
            raise MCPError(f"invalid discovery state {state!r}; expected one of {DISCOVERY_STATES}")
        try:
            discovery = record_discovery(
                self._store,
                wing=wing,
                title=title,
                summary=summary,
                novelty=novelty,
                evidence_ids=tuple(evidence_ids),
                state=state,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        return (
            f"Recorded discovery #{discovery.drawer_id} [{discovery.state}] "
            f"{discovery.title!r} (novelty={discovery.novelty}). "
            "Tell the user what changed and cite its evidence."
        )

    def transition_discovery(
        self,
        *,
        drawer_id: int,
        state: str,
        note: str,
    ) -> str:
        """Promote, reject, corroborate, or expire a discovery append-only."""
        if state not in DISCOVERY_STATES:
            raise MCPError(f"invalid discovery state {state!r}; expected one of {DISCOVERY_STATES}")
        try:
            discovery = transition_discovery(
                self._store,
                drawer_id=drawer_id,
                state=state,
                note=note,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        return (
            f"Discovery #{drawer_id} transitioned to [{discovery.state}] "
            f"as drawer #{discovery.drawer_id}."
        )

    def discoveries(
        self,
        *,
        wing: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> str:
        """List current Discovery Ledger leaves."""
        if state is not None and state not in DISCOVERY_STATES:
            raise MCPError(f"invalid discovery state {state!r}; expected one of {DISCOVERY_STATES}")
        try:
            records = list_discoveries(
                self._store,
                wing=wing,
                state=state,
                limit=limit,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        return (
            EVIDENCE_BOUNDARY
            + "\n"
            + format_discoveries(
                records,
                heading="Cairntir Discovery Ledger",
            )
        )

    def learning_log(
        self,
        *,
        wing: str | None = None,
        include_candidates: bool = True,
        limit: int = 100,
    ) -> str:
        """Return the easy-to-read Human Learning Log."""
        try:
            return (
                EVIDENCE_BOUNDARY
                + "\n"
                + human_learning_log(
                    self._store,
                    wing=wing,
                    include_candidates=include_candidates,
                    limit=limit,
                )
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc

    def discover_scan(
        self,
        *,
        wing: str,
        min_observations: int = 3,
        confidence_threshold: float = 0.8,
    ) -> str:
        """Derive conservative candidates from repeated prediction episodes."""
        try:
            with self._store.transaction():
                proposed = propose_multi_episode_discoveries(
                    self._store,
                    wing=wing,
                    min_observations=min_observations,
                    confidence_threshold=confidence_threshold,
                )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        if not proposed:
            return (
                f"No new multi-episode discovery candidates in wing {wing!r}; "
                "existing candidates were left unchanged."
            )
        return (
            EVIDENCE_BOUNDARY
            + "\n"
            + format_discoveries(
                proposed,
                heading="New automatic discovery candidates — human review required",
            )
        )

    def calibration(self, *, wing: str) -> str:
        """Return empirical prediction quality and uncertainty for one wing."""
        return render_calibration(calibration_report(self._store, wing=wing))

    def codeglass_record(
        self,
        *,
        wing: str,
        target: str,
        reader_level: str,
        what: str,
        how: str,
        where: str,
        when: str,
        why: str,
        evidence_ids: list[int],
        glossary: str,
        danger_zones: str,
        idempotency_key: str | None = None,
    ) -> str:
        """Validate and durably store an evidence-cited walkthrough."""
        if reader_level not in READER_LEVELS:
            raise MCPError(f"invalid reader_level {reader_level!r}; expected {READER_LEVELS}")
        level = reader_level
        sections = {
            "what": what.strip(),
            "how": how.strip(),
            "where": where.strip(),
            "when": when.strip(),
            "why": why.strip(),
        }
        fingerprint = walkthrough_fingerprint(
            wing=wing,
            target=target,
            reader_level=level,
            sections=sections,
            evidence_ids=tuple(evidence_ids),
        )
        request = {
            "fingerprint": fingerprint,
            "glossary": glossary,
            "danger_zones": danger_zones,
        }

        def _record() -> dict[str, object]:
            saved = record_walkthrough(
                self._store,
                wing=wing,
                target=target,
                reader_level=level,
                sections=sections,
                evidence_ids=tuple(evidence_ids),
                glossary=glossary,
                danger_zones=danger_zones,
            )
            return {"drawer_id": saved.id}

        try:
            execution = self._store.execute_once(
                idempotency_key=idempotency_key or f"codeglass:{request_hash(request)}",
                operation="codeglass.walkthrough",
                request=request,
                action=_record,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        replay = " (replayed; no duplicate)" if execution.replayed else ""
        return f"Stored CodeGlass walkthrough #{execution.result['drawer_id']}{replay}."

    def codeglass_teachback(
        self,
        *,
        walkthrough_id: int,
        phase: str,
        responses: list[dict[str, Any]],
        mastered_concepts: list[str] | None = None,
        misunderstood_concepts: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Record immediate or delayed teach-back and update the learning log."""
        if phase not in TEACH_BACK_PHASES:
            raise MCPError(f"invalid phase {phase!r}; expected {TEACH_BACK_PHASES}")
        teachback_phase = phase
        try:
            parsed = tuple(
                TeachBackResponse(
                    question=str(item["question"]),
                    answer=str(item["answer"]),
                    score=float(item["score"]),
                )
                for item in responses
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MCPError(f"invalid teach-back response: {exc}") from exc
        request = {
            "walkthrough_id": walkthrough_id,
            "phase": phase,
            "responses": responses,
            "mastered_concepts": mastered_concepts or [],
            "misunderstood_concepts": misunderstood_concepts or [],
        }

        def _record() -> dict[str, object]:
            saved = record_teachback(
                self._store,
                walkthrough_id=walkthrough_id,
                phase=teachback_phase,
                responses=parsed,
                mastered_concepts=tuple(mastered_concepts or ()),
                misunderstood_concepts=tuple(misunderstood_concepts or ()),
            )
            return {"drawer_id": saved.id}

        try:
            execution = self._store.execute_once(
                idempotency_key=idempotency_key or f"codeglass-teachback:{request_hash(request)}",
                operation="codeglass.teachback",
                request=request,
                action=_record,
            )
        except ValueError as exc:
            raise MCPError(str(exc)) from exc
        replay = " (replayed; no duplicate)" if execution.replayed else ""
        return f"Stored CodeGlass {phase} teach-back #{execution.result['drawer_id']}{replay}."

    def codeglass_retention(self, *, walkthrough_id: int) -> str:
        """Show immediate-versus-delayed comprehension and concepts to revisit."""
        return render_retention(retention_report(self._store, walkthrough_id=walkthrough_id))

    def timeline(self, *, wing: str, entity: str, limit: int = 50) -> str:
        """Chronological view of drawers in ``wing`` mentioning ``entity``."""
        if not entity.strip():
            raise MCPError("timeline requires a non-empty entity")
        drawers = self._store.list_by(wing=wing, limit=limit)
        needle = entity.lower()
        matched = [
            d
            for d in drawers
            if needle in d.content.lower()
            or needle in json.dumps(d.metadata, sort_keys=True).lower()
        ]
        matched.sort(key=lambda d: d.created_at)
        if not matched:
            return f"No timeline entries for {entity!r} in wing {wing!r}."
        lines = [f"Timeline for {entity!r} in {wing!r} ({len(matched)} entries):"]
        evidence: list[str] = []
        for d in matched:
            lines.append(f"  {_fmt_ts(d.created_at)}  #{d.id}  {d.room}  {_content_receipt(d)}")
            evidence.append(
                render_memory_evidence(
                    d,
                    self._required_provenance(d.id),
                    content=_snippet(d.content),
                )
            )
        return "\n".join(lines) + "\n\n" + render_evidence_block(evidence)

    def audit(self, *, wing: str) -> str:
        """Return the Quality skill prompt plus the wing's essential drawers.

        The caller (the LLM) runs the skill using the returned text as the
        system-level instructions and the drawer dump as the evidence base.
        """
        essentials = self._store.list_by(wing=wing, layer=Layer.ESSENTIAL, limit=100)
        skill = load_skill("quality")
        context = [
            f"## Context — wing={wing!r}, essential drawers={len(essentials)}",
        ]
        if essentials:
            for d in essentials:
                context.append(
                    render_memory_evidence(
                        d,
                        self._required_provenance(d.id),
                        content=_snippet(d.content),
                    )
                )
        else:
            context.append("(none — the essential layer is empty)")
        return f"{skill}\n\n---\n\n" + render_evidence_block(context) + "\n"

    def crucible(self, *, claim: str) -> str:
        """Return the Crucible skill prompt wrapped around ``claim``."""
        if not claim.strip():
            raise MCPError("crucible requires a non-empty claim")
        skill = load_skill("crucible")
        return f"{skill}\n\n---\n\n## Claim under crucible\n\n{claim.strip()}\n"

    def _required_provenance(self, drawer_id: int | None) -> WriteProvenance:
        if drawer_id is None:
            raise MCPError("stored drawer is missing its id")
        provenance = self._store.get_provenance(drawer_id)
        if provenance is None:
            raise MCPError(f"drawer {drawer_id} is missing write provenance")
        return provenance


# ------------------------------------------------------------------ helpers


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _drawer_ref(drawer: Drawer) -> str:
    return f"cairntir://drawer/{drawer.id}"


def _content_receipt(drawer: Drawer, *, snippet_limit: int = 100, full: bool = False) -> str:
    """Render the per-hit receipt: what this drawer is, and what you are seeing of it.

    The field is ``snippet_shortened``, not ``truncated``. It says only that
    the preview line above it was cut for display; the drawer is stored
    whole and ``sha256`` is over the complete content, so the reader can
    verify that for themselves.

    The old name was ``truncated``, and it was actively dangerous in the one
    situation where it mattered most. On 2026-08-10 the embedder was found
    to be cutting every drawer at 128 tokens, hiding 73.4% of the corpus
    from search. Proving the fix meant retrieving a drawer by text from its
    tail — and the receipt on that very hit read ``truncated=true``, which
    reads as "the defect is still here" and is about something else
    entirely. A field name that invites the wrong conclusion about the
    defect it sits next to is a bug in the receipt, not a nitpick.
    """
    shortened = len(" ".join(drawer.content.split())) > snippet_limit
    suffix = " full=true" if full else ""
    return (
        f"ref={_drawer_ref(drawer)} len={len(drawer.content)} "
        f"sha256={_content_hash(drawer.content)} snippet_shortened={str(shortened).lower()}"
        f"{suffix}"
    )


def _unknown_wing_notice(store: DrawerStore, wing: str) -> str | None:
    """Warn — and name the real wings — when ``wing`` holds nothing.

    Returns None when the wing exists, so the common path is unchanged.

    Why this is not a nicety. IDENTITY is deliberately cross-wing, so
    ``session_start`` on a wing that does not exist still returns a stack of
    identity drawers belonging to *other* projects, with Essential, On-demand
    and Deep all at zero and nothing anywhere saying the wing was never real.
    On 2026-08-11 a Cursor session asked for wing ``'workspace'`` — a name
    that has never existed — and reported back to the user: *"store is empty
    (no identity/essential/on-demand/deep drawers)."* The store held 424
    drawers across 24 wings at that moment.

    **Falsely reporting emptiness is the worst failure this product has.** It
    is indistinguishable from data loss to the person reading it, and it
    teaches them not to trust the tool meant to be their backbone.
    ``handoff`` has warned on an unknown wing since 1.3.0; ``session_start``
    never did, which is the same asymmetry that hid the on_demand blind spot.

    The notice names the actual wings because "no such wing" alone still
    leaves the caller guessing, and a guessing caller writes to a new wing
    and splits the project's memory in two.
    """
    if store.wing_exists(wing):
        return None
    counts = store.wing_counts()
    if not counts:
        return (
            f"WING {wing!r} DOES NOT EXIST, and neither does any other — this store is "
            "genuinely empty. If that is unexpected, it may be new or misconfigured. "
            "Do not substitute model memory."
        )
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    listed = ", ".join(f"{name} ({n})" for name, n in ranked[:12])
    more = "" if len(ranked) <= 12 else f", and {len(ranked) - 12} more"
    return (
        f"WING {wing!r} DOES NOT EXIST. **This store is not empty** — it holds "
        f"{total:,} drawers across {len(ranked)} wings, and any identity drawers "
        "listed below belong to other wings, because identity is cross-wing by "
        "design.\n\n"
        f"Existing wings: {listed}{more}.\n\n"
        "Do not report this as an empty or broken store, and do not start writing "
        "to a new wing without asking — that splits a project's memory in two. Pick "
        "the wing that matches this project, or ask the user which one is right."
    )


def _snippet(content: str, limit: int = 100) -> str:
    single = " ".join(content.split())
    return single if len(single) <= limit else single[: limit - 1] + "…"


def _malformed_note(drawer_ids: tuple[int, ...]) -> str:
    """Render a visible warning for drawers whose anchors could not be parsed.

    Surfaced rather than swallowed. A malformed anchor is a data defect the
    user needs to see and fix; it must never be silently skipped.
    """
    if not drawer_ids:
        return ""
    ids = ", ".join(f"#{i}" for i in drawer_ids)
    return f"\n\nWARNING: {len(drawer_ids)} drawer(s) have malformed metadata.anchors: {ids}"


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")


def _provenance_or_fail(store: DrawerStore, drawer_id: int) -> WriteProvenance:
    provenance = store.get_provenance(drawer_id)
    if provenance is None:
        raise MCPError(f"drawer {drawer_id} is missing write provenance")
    return provenance


def _format_handoff(brief: Handoff, *, store: DrawerStore) -> str:
    """Render a composed brief: an index, then whole drawers as evidence.

    The header lines are a cheap index — id, room, size — and the
    evidence block carries each included drawer's **full** content
    exactly once. Omitted drawers appear in the index only, with the
    cost of fetching them, so the caller can spend one targeted
    ``cairntir_get`` instead of a blind ``cairntir_recall``.
    """
    used_pct = (brief.used_chars * 100 // brief.budget_chars) if brief.budget_chars else 0
    lines = [
        f"# Cairntir handoff — wing={brief.wing!r}",
        "",
        f"Budget {brief.budget_chars:,} chars of drawer content "
        f"(~{brief.budget_chars // 4:,} tokens est.; the evidence envelope adds "
        f"provenance on top) · used {brief.used_chars:,} (~{brief.used_tokens:,}, "
        f"{used_pct}%) · "
        f"{brief.included_count} drawer(s) whole, {brief.omitted_count} named but not fetched.",
        "",
    ]
    if brief.is_empty:
        if brief.wing_is_unknown:
            lines.append(
                f"Nothing is recorded for wing {brief.wing!r}. If that is unexpected, "
                "the store may be new or misconfigured — do not substitute model memory."
            )
        else:
            # The store is healthy; these drawers are simply not briefing
            # material. Saying "nothing is recorded" here would send someone
            # to debug a store that is working exactly as designed.
            #
            # But it must not claim health either. The string this replaces
            # read "Nothing here is broken" and printed at the exact moment
            # the caller got nothing back — reassurance in place of a
            # reason, which is how the on_demand blind spot survived from
            # v1.3.0 to 2026-08-10. Name what was skipped and why.
            skipped = (
                f"all {brief.deep_total} are in the deep layer"
                if brief.deep_total == brief.wing_total
                else f"{brief.deep_total} of them are in the deep layer"
            )
            lines.append(
                f"Wing {brief.wing!r} holds {brief.wing_total} drawer(s) and this brief "
                f"returned none of them: {skipped}, which is the one layer handoff never "
                "loads on its own. That is a deliberate exclusion, not a fault — but it "
                "does mean this brief is not evidence the wing is empty. Reach them with "
                "cairntir_recall, or cairntir_get if you already have an id."
            )
        return "\n".join(lines) + "\n"

    evidence: list[str] = []
    for section in brief.sections:
        if not section.included and not section.omitted:
            continue
        lines.append(f"## {section.title} ({len(section.included)})")
        lines.append(f"_{section.why}_")
        for drawer in section.included:
            if drawer.id is None:
                raise MCPError("stored drawer is missing its id")
            lines.append(f"  #{drawer.id}  {drawer.room}  {len(drawer.content):,} chars")
            evidence.append(render_memory_evidence(drawer, _provenance_or_fail(store, drawer.id)))
        if section.omitted:
            lines.append(
                f"  ...{len(section.omitted)} not fetched — cairntir_get(<id>) for any you need:"
            )
            for miss in section.omitted:
                lines.append(
                    f"    #{miss.drawer_id}  {miss.room}  [{miss.layer.value}]  "
                    f"{miss.chars:,} chars (~{miss.tokens:,} tokens)"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n\n" + render_evidence_block(evidence) + "\n"


def _format_retrieval(
    wing: str,
    result: RetrievalResult,
    *,
    store: DrawerStore,
    budget_chars: int | None = None,
) -> str:
    """Render a session_start payload, optionally under a hard character ceiling.

    The budget is the commitment the 2026-07-27 audit wrote into the v1.2 core
    list and that v1.2 then shipped without -- see drawer #212. It behaves like
    :mod:`cairntir.handoff`: a drawer is included whole or named and skipped,
    never cut in half, because half a drawer is a misleading drawer.

    Layers are spent in priority order, so identity survives a tight budget and
    deep is dropped first. What did not fit is listed by id, so the reader can
    spend one ``cairntir_get`` on exactly what they want instead of guessing.
    """
    lines = [f"# Cairntir session_start — wing={wing!r}", ""]
    notice = _unknown_wing_notice(store, wing)
    if notice:
        lines.extend([notice, ""])
    evidence: list[str] = []
    omitted: list[int] = []
    spent = 0
    for title, drawers in (
        ("Identity", result.identity),
        ("Essential", result.essential),
        ("On-demand", result.on_demand),
        ("Deep", result.deep),
    ):
        lines.append(f"## {title} ({len(drawers)})")
        if not drawers:
            lines.append("  (none)")
        for d in drawers:
            if d.id is None:
                raise MCPError("stored drawer is missing its id")
            provenance = store.get_provenance(d.id)
            if provenance is None:
                raise MCPError(f"drawer {d.id} is missing write provenance")
            stub = f"  #{d.id}  {d.room}  {_content_receipt(d)}"
            entry = render_memory_evidence(d, provenance, content=_snippet(d.content))
            cost = len(stub) + len(entry)
            if budget_chars is not None and spent + cost > budget_chars:
                omitted.append(d.id)
                continue
            spent += cost
            lines.append(stub)
            evidence.append(entry)
        lines.append("")
    if omitted:
        lines.append(
            f"## Omitted for budget ({len(omitted)})\n"
            f"  {omitted}\n"
            "  Fetch any of these whole with cairntir_get, or use cairntir_handoff "
            "for a composed brief."
        )
    return "\n".join(lines).rstrip() + "\n\n" + render_evidence_block(evidence) + "\n"
