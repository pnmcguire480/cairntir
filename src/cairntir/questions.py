"""Append-only, evidence-bound questions with durable declared resolutions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cairntir.access import ScopedStore
from cairntir.errors import CairntirError
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.provenance import Sensitivity, TrustLevel, WriteProvenance

_Store = DrawerStore | ScopedStore
_RECEIPT = "cairntir.question-receipt.v1"
_FIELDS = {
    "schema",
    "operation",
    "status",
    "request_id",
    "question_id",
    "question_drawer_id",
    "question_sha256",
    "resolution_drawer_id",
}


class QuestionError(CairntirError):
    """A question request or lifecycle record cannot satisfy its evidence contract."""


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise QuestionError(f"{name} must be nonblank text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise QuestionError(f"{name} must be valid UTF-8 text") from exc


def _uuid(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise QuestionError(f"{name} must be a canonical UUID")
    try:
        canonical = str(UUID(value))
    except ValueError as exc:
        raise QuestionError(f"{name} must be a canonical UUID") from exc
    if value != canonical:
        raise QuestionError(f"{name} must be a canonical UUID")


def _identity(value: object, name: str) -> None:
    if type(value) is not int or not 0 < value < 2**63:
        raise QuestionError(f"{name} must be a positive drawer ID")


def _hash(value: object, name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QuestionError(f"{name} must be a lowercase SHA256")


def _request(value: object, wing: str, operation: str) -> dict[str, Any]:
    fields = {"schema", "request_id", "wing", "content", "evidence"}
    fields |= (
        {"room", "owner"}
        if operation == "open"
        else {"question_id", "question_drawer_id", "question_sha256"}
    )
    if not isinstance(value, dict) or value.keys() != fields:
        raise QuestionError("question request fields do not match the schema")
    payload = deepcopy(value)
    if payload["schema"] != f"cairntir.question-{operation}.v1" or payload["wing"] != wing:
        raise QuestionError("question request schema or wing does not match")
    _validate_ident(wing, "wing")
    _uuid(payload["request_id"], "request_id")
    _text(payload["content"], "content")
    if operation == "open":
        _validate_ident(payload["room"], "room")
        if payload["owner"] is not None:
            _text(payload["owner"], "owner")
    else:
        _uuid(payload["question_id"], "question_id")
        _identity(payload["question_drawer_id"], "question_drawer_id")
        _hash(payload["question_sha256"], "question_sha256")
    refs = payload["evidence"]
    if not isinstance(refs, list) or (operation == "resolve" and not refs):
        raise QuestionError("evidence must be a list, nonempty for resolution")
    for ref in refs:
        if not isinstance(ref, dict) or ref.keys() != {
            "drawer_id",
            "source_identity",
            "content_sha256",
        }:
            raise QuestionError("evidence reference fields do not match the schema")
        _identity(ref["drawer_id"], "evidence drawer_id")
        _uuid(ref["source_identity"], "evidence source_identity")
        _hash(ref["content_sha256"], "evidence content_sha256")
    return payload


def _available(provenance: WriteProvenance) -> bool:
    now = datetime.now(UTC)
    return (
        provenance.sensitivity != Sensitivity.SECRET
        and (provenance.valid_from is None or provenance.valid_from <= now)
        and (provenance.valid_until is None or provenance.valid_until > now)
    )


def _evidence(store: _Store, request: dict[str, Any], *, current: bool = True) -> None:
    refs = request["evidence"]
    records = {
        drawer.id: (drawer, provenance)
        for drawer, provenance in store.context_relatives(
            wing=request["wing"], drawer_ids=[ref["drawer_id"] for ref in refs]
        )
    }
    for ref in refs:
        pair = records.get(ref["drawer_id"])
        if pair is None:
            raise QuestionError("question evidence is unavailable")
        drawer, provenance = pair
        if (
            provenance.sensitivity == Sensitivity.SECRET
            or (current and not _available(provenance))
            or store.portable_identity(ref["drawer_id"]) != ref["source_identity"]
            or _sha(drawer.content) != ref["content_sha256"]
        ):
            raise QuestionError("question evidence binding does not match")


def _metadata(request: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "request_id": request["request_id"],
        "evidence_ids": [ref["drawer_id"] for ref in request["evidence"]],
    }


def _receipt(
    store: _Store, request: dict[str, Any], question: Drawer, resolution: Drawer | None
) -> dict[str, Any]:
    if question.id is None or (resolution is not None and resolution.id is None):
        raise QuestionError("question append returned no persisted drawer")
    return {
        "schema": _RECEIPT,
        "operation": "open" if resolution is None else "resolve",
        "status": "committed",
        "request_id": request["request_id"],
        "question_id": store.portable_identity(question.id),
        "question_drawer_id": question.id,
        "question_sha256": _sha(question.content),
        "resolution_drawer_id": resolution.id if resolution is not None else None,
        "_question": {
            **request,
            **({"resolution_sha256": _sha(resolution.content)} if resolution else {}),
        },
    }


def _execute(
    store: _Store, request: dict[str, Any], action: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    result = store.execute_once(
        idempotency_key="question:" + request["request_id"],
        operation=request["schema"],
        request=request,
        action=action,
    )
    receipt = result.result
    rows = {
        int(drawer.id or 0): (drawer, provenance)
        for drawer, provenance in store.context_relatives(
            wing=request["wing"], drawer_ids=[receipt["question_drawer_id"]]
        )
    }
    required = {receipt["question_drawer_id"]}
    if receipt["resolution_drawer_id"] is not None:
        required.add(receipt["resolution_drawer_id"])
    if any(key not in rows or rows[key][1].sensitivity == Sensitivity.SECRET for key in required):
        raise QuestionError("committed question evidence is unavailable")
    _committed(store, receipt, rows)
    return {**{key: result.result[key] for key in _FIELDS}, "replayed": result.replayed}


def open_question(store: _Store, request: object, *, wing: str) -> dict[str, Any]:
    """Append an exact declared question, or replay its committed opening receipt."""
    try:
        if store.transaction_active:
            raise QuestionError("question operation cannot run inside a caller transaction")
        payload = _request(request, wing, "open")
        with store.transaction():
            if isinstance(store, ScopedStore):
                store.authorize("read", wing=wing, room=payload["room"])
                store.authorize("write", wing=wing, room=payload["room"])
            _evidence(store, payload, current=False)

            def append() -> dict[str, Any]:
                _evidence(store, payload)
                question = store.add(
                    Drawer(
                        wing=wing,
                        room=payload["room"],
                        content=payload["content"],
                        metadata={**_metadata(payload, "question.open"), "open_question": True},
                    ),
                    provenance=WriteProvenance.create(
                        host="questions", capture_path="question.open", trust=TrustLevel.UNTRUSTED
                    ),
                )
                return _receipt(store, payload, question, None)

            return _execute(store, payload, append)
    except CairntirError as exc:
        if isinstance(exc, QuestionError):
            raise
        raise QuestionError(str(exc)) from exc


def _bound(
    store: _Store, receipt: dict[str, Any], question: Drawer, operation: str
) -> dict[str, Any]:
    if (
        receipt.get("schema") != _RECEIPT
        or receipt.get("status") != "committed"
        or receipt.get("operation") != operation
        or receipt.get("question_drawer_id") != question.id
        or receipt.get("question_sha256") != _sha(question.content)
        or receipt.get("question_id") != store.portable_identity(int(question.id or 0))
    ):
        raise QuestionError("committed question receipt does not match original evidence")
    state = deepcopy(receipt.get("_question"))
    if not isinstance(state, dict):
        raise QuestionError("committed question request is missing")
    if operation == "resolve":
        _hash(state.pop("resolution_sha256", None), "resolution_sha256")
    payload = _request(state, question.wing, operation)
    if payload["request_id"] != receipt.get("request_id"):
        raise QuestionError("committed question request identity does not match")
    if operation == "open":
        if (
            payload["content"] != question.content
            or payload["room"] != question.room
            or receipt.get("resolution_drawer_id") is not None
        ):
            raise QuestionError("committed opening does not match original question")
    elif any(
        payload[key] != receipt[key]
        for key in ("question_id", "question_drawer_id", "question_sha256")
    ):
        raise QuestionError("committed resolution does not match its question")
    _evidence(store, payload, current=False)
    return payload


def _committed(
    store: _Store,
    receipt: dict[str, Any],
    rows: dict[int, tuple[Drawer, WriteProvenance]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    question, provenance = rows[receipt["question_drawer_id"]]
    payload = _bound(store, receipt, question, receipt["operation"])
    if receipt["operation"] == "open":
        return payload, None
    drawer, written = rows[receipt["resolution_drawer_id"]]
    if (
        drawer.content != payload["content"]
        or _sha(drawer.content) != receipt["_question"]["resolution_sha256"]
        or drawer.supersedes_id != question.id
        or drawer.room != question.room
        or drawer.layer != question.layer
        or written.trust != TrustLevel.UNTRUSTED
        or written.sensitivity != provenance.sensitivity
        or written.visibility != provenance.visibility
    ):
        raise QuestionError("committed resolution does not match resolution evidence")
    return payload, {
        "drawer_id": drawer.id,
        "content": drawer.content,
        "content_sha256": _sha(drawer.content),
        "evidence": payload["evidence"],
    }


def _register(store: _Store, wing: str) -> list[dict[str, Any]]:
    records, withheld = store._question_records(wing=wing)
    rows = {
        int(drawer.id or 0): (drawer, provenance)
        for drawer, provenance in store.context_candidates(wing=wing)[0]
    }
    openings: dict[int, dict[str, Any]] = {}
    resolutions: dict[int, dict[str, Any]] = {}
    for record in records:
        key = record["question_drawer_id"]
        required = {key, *(ref["drawer_id"] for ref in record["_question"]["evidence"])}
        if record["resolution_drawer_id"] is not None:
            required.add(record["resolution_drawer_id"])
        if any(
            item not in rows or rows[item][1].sensitivity == Sensitivity.SECRET for item in required
        ):
            withheld.add(key)
            continue
        committed_payload, resolution = _committed(store, record, rows)
        if any(not _available(rows[item][1]) for item in required):
            withheld.add(key)
        if resolution is not None:
            if key in resolutions:
                raise QuestionError("multiple committed resolutions for one question")
            resolutions[key] = resolution
        else:
            openings[key] = committed_payload
    candidates = {
        key: pair for key, pair in rows.items() if key not in withheld and _available(pair[1])
    }
    superseded = {drawer.supersedes_id for drawer, _ in candidates.values()}
    if isinstance(store, ScopedStore):
        superseded.update(store.context_suppressed_ids(list(candidates)))
    entries = []
    for key, (question, _provenance) in sorted(candidates.items()):
        payload = openings.get(key)
        if payload is None and (
            question.metadata.get("kind") or not question.metadata.get("open_question")
        ):
            continue
        resolution = resolutions.get(key)
        status = (
            "resolved"
            if resolution
            else (
                "legacy_superseded_unverified" if payload is None and key in superseded else "open"
            )
        )
        entries.append(
            {
                "question_id": store.portable_identity(key),
                "drawer_id": key,
                "content": question.content,
                "content_sha256": _sha(question.content),
                "owner": payload["owner"] if payload else None,
                "evidence": payload["evidence"] if payload else [],
                "status": status,
                "legacy": payload is None,
                "resolution": resolution,
            }
        )
    return entries


def list_questions(store: _Store, *, wing: str, include_resolved: bool = False) -> dict[str, Any]:
    """Read visible question state without touching source rows or inferring answers."""
    try:
        _validate_ident(wing, "wing")
        if type(include_resolved) is not bool:
            raise QuestionError("include_resolved must be boolean")
        if isinstance(store, ScopedStore):
            store.authorize("read", wing=wing)
        return {
            "schema": "cairntir.question-register.v1",
            "wing": wing,
            "questions": [
                entry
                for entry in _register(store, wing)
                if include_resolved or entry["status"] == "open"
            ],
        }
    except CairntirError as exc:
        if isinstance(exc, QuestionError):
            raise
        raise QuestionError(str(exc)) from exc


def resolve_question(store: _Store, request: object, *, wing: str) -> dict[str, Any]:
    """Append an evidence-linked declared resolution; original question stays immutable."""
    try:
        if store.transaction_active:
            raise QuestionError("question operation cannot run inside a caller transaction")
        payload = _request(request, wing, "resolve")
        with store.transaction():
            key = payload["question_drawer_id"]
            if isinstance(store, ScopedStore):
                store.authorize("read", drawer_id=key)
                store.authorize("write", drawer_id=key)
            family = store.context_relatives(wing=wing, drawer_ids=[key])
            pair = next((pair for pair in family if pair[0].id == key), None)
            if pair is None or pair[1].sensitivity == Sensitivity.SECRET:
                raise QuestionError("question is unavailable")
            question, provenance = pair
            if (
                store.portable_identity(key) != payload["question_id"]
                or _sha(question.content) != payload["question_sha256"]
            ):
                raise QuestionError("question binding does not match")
            _evidence(store, payload, current=False)

            def append() -> dict[str, Any]:
                _evidence(store, payload)
                entry = next(
                    (item for item in _register(store, wing) if item["drawer_id"] == key), None
                )
                if entry is None or entry["status"] != "open":
                    raise QuestionError("question is unavailable or no longer open")
                resolution = store.add(
                    Drawer(
                        wing=wing,
                        room=question.room,
                        layer=question.layer,
                        content=payload["content"],
                        supersedes_id=key,
                        metadata=_metadata(payload, "question.resolution"),
                    ),
                    provenance=WriteProvenance.create(
                        host="questions",
                        capture_path="question.resolve",
                        trust=TrustLevel.UNTRUSTED,
                        sensitivity=provenance.sensitivity,
                        visibility=provenance.visibility,
                        valid_from=provenance.valid_from,
                        valid_until=provenance.valid_until,
                    ),
                )
                return _receipt(store, payload, question, resolution)

            return _execute(store, payload, append)
    except CairntirError as exc:
        if isinstance(exc, QuestionError):
            raise
        raise QuestionError(str(exc)) from exc
