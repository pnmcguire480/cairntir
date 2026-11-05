"""One existing-contract control for a required managed event hidden by drawer scope."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant

from . import test_durable_boundaries as base

durable = base.durable


def test_hidden_required_event_cannot_become_complete_capture_or_projection(durable):
    """Withhold completeness while preserving hidden source and prior public file bytes."""
    b = durable
    owner, full, session, first, brief = base.ready(b, "owner")
    hidden_text = "  HIDDEN_REQUIRED_COMMITMENT café\r\nnot authorized to this drawer grant  "
    second = full.capture(
        {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": session,
            "sequence": 2,
            "task_id": first["task_id"],
            "expected_revision": first["revision"],
            "content": hidden_text,
        }
    )
    owner_closed = full.close(last_sequence=2)
    assert owner_closed["capture_complete"] is True
    target = b.project / "Last Session visibility.md"
    target.write_bytes(
        b"Human prefix\r\n<!-- cairntir:generated:begin -->\nold\n"
        b"<!-- cairntir:generated:end -->\r\nHuman suffix\r\n"
    )
    projected = b.projection.project_last_session(
        owner,
        root=b.project,
        path=target,
        wing=base.WING,
        session_id=session,
        epoch=brief["epoch"],
    )
    assert projected["status"] == "complete"
    assert projected["snapshot"]["capture_complete"] is True
    prior = target.read_bytes()
    token = issue_grant(
        owner,
        scopes=[{"wing": base.WING, "drawer_ids": [first["drawer_id"]]}],
        capabilities=["read", "write"],
    )
    scoped = bind_grant(owner, token)
    runtime = b.api.ManagedRuntime(scoped, config=deepcopy(b.config))
    public = []
    epoch = brief["epoch"]
    try:
        limited = runtime.start(session, task_id=first["task_id"])
    except b.api.ManagedRuntimeError:
        pass
    else:
        public.append(limited)
        epoch = limited["epoch"]
        assert limited["complete"] is False
        try:
            closed = runtime.close(last_sequence=1)
        except b.api.ManagedRuntimeError:
            pass
        else:
            public.append(closed)
            assert closed["capture_complete"] is False
    before_projection = base.snapshot(owner._conn)
    limited_view = b.projection.project_last_session(
        scoped,
        root=b.project,
        path=target,
        wing=base.WING,
        session_id=session,
        epoch=epoch,
    )
    public.append(limited_view)
    assert limited_view["status"] == "error" and limited_view.get("error")
    assert "snapshot" not in limited_view and "generated_sha256" not in limited_view
    assert target.read_bytes() == prior
    assert base.snapshot(owner._conn) == before_projection
    disclosed = json.dumps(public, ensure_ascii=False)
    assert hidden_text not in disclosed and second["source_identity"] not in disclosed
    assert tuple(
        owner._conn.execute(
            "SELECT content FROM drawers WHERE id=?", (second["drawer_id"],)
        ).fetchone()
    ) == (hidden_text,)
    recovered = b.projection.project_last_session(
        owner,
        root=b.project,
        path=target,
        wing=base.WING,
        session_id=session,
        epoch=brief["epoch"],
    )
    assert recovered["status"] == "complete"
    assert recovered["snapshot"]["capture_complete"] is True
    assert target.read_bytes() == prior
