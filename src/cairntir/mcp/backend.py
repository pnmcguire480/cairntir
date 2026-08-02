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
from cairntir.memory.anchors import parse_anchors
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
    ) -> str:
        """Store a verbatim drawer. Returns a human-readable confirmation."""
        try:
            layer_enum = Layer(layer)
        except ValueError as exc:
            raise MCPError(
                f"invalid layer {layer!r}; expected one of {[x.value for x in Layer]}"
            ) from exc
        if metadata:
            # Fail here, not weeks later in recall_for_change. An agent that
            # guesses the anchor shape wrong gets a correctable error inside
            # the session that wrote it; the alternative is a silent bad row
            # and a warning in a different tool, in a different chat, about a
            # drawer nobody can reconstruct from memory.
            try:
                parse_anchors(metadata)
            except AnchorError as exc:
                raise MCPError(f"{exc}. {ANCHOR_SHAPE_HINT}") from exc
        drawer = Drawer(
            wing=wing,
            room=room,
            content=content,
            layer=layer_enum,
            metadata=metadata or {},
        )
        saved = self._store.add(drawer)
        return (
            f"Stored drawer #{saved.id} in {saved.wing}/{saved.room} "
            f"(layer={saved.layer.value}, ref={_drawer_ref(saved)})."
        )

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
    ) -> str:
        """Semantic search. Returns a formatted list of hits."""
        if not query.strip():
            raise MCPError("recall requires a non-empty query")
        hits = self._store.search(query, wing=wing, room=room, limit=limit)
        if not hits:
            return f"No drawers matched {query!r}."
        lines = [f"{len(hits)} hit(s) for {query!r}:"]
        evidence: list[str] = []
        for drawer, distance in hits:
            lines.append(
                f"  #{drawer.id}  {drawer.wing}/{drawer.room}  "
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

    def session_start(self, *, wing: str, query: str | None = None) -> str:
        """Load 4-layer context plus active learning signals for ``wing``."""
        result = self._retriever.load(wing=wing, query=query, include_deep=False)
        context = _format_retrieval(wing, result, store=self._store)
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


def _content_receipt(drawer: Drawer, *, snippet_limit: int = 100) -> str:
    truncated = len(" ".join(drawer.content.split())) > snippet_limit
    return (
        f"ref={_drawer_ref(drawer)} len={len(drawer.content)} "
        f"sha256={_content_hash(drawer.content)} truncated={str(truncated).lower()}"
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


def _format_retrieval(
    wing: str,
    result: RetrievalResult,
    *,
    store: DrawerStore,
) -> str:
    lines = [f"# Cairntir session_start — wing={wing!r}", ""]
    evidence: list[str] = []
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
            lines.append(f"  #{d.id}  {d.room}  {_content_receipt(d)}")
            if d.id is None:
                raise MCPError("stored drawer is missing its id")
            provenance = store.get_provenance(d.id)
            if provenance is None:
                raise MCPError(f"drawer {d.id} is missing write provenance")
            evidence.append(render_memory_evidence(d, provenance, content=_snippet(d.content)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n\n" + render_evidence_block(evidence) + "\n"
