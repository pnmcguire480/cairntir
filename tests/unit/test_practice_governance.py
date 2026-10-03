"""Regression checks for opt-in attributed practice governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from cairntir import procedures as api
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def test_opt_in_api_is_available() -> None:
    assert hasattr(api, "PracticeGovernance"), "optional governance API is absent"


@pytest.fixture
def bundle(tmp_path: Path) -> Any:
    with DrawerStore(tmp_path / "governance.db", HashEmbeddingProvider(dimension=32)) as store:
        evidence = store.add(Drawer(wing="governance", room="cases", content="observed ordering"))
        assert evidence.id is not None
        spec = api.ProcedureSpec(
            "Ordered practice",
            ("List input",),
            "Ordering case",
            ("Sort",),
            "Ordered list",
            ("Reuse original",),
            (evidence.id,),
        )
        yield store, api.ProcedureBook(store, {}), spec


def _governed(
    spec: api.ProcedureSpec, version_label: str = "1", **fields: Any
) -> api.ProcedureSpec:
    return replace(
        spec,
        governance=api.PracticeGovernance(
            **{
                "owner": "  Maintainer  ",
                "version": version_label,
                "rationale": "Reason\nverbatim  ",
                "review_due": "2024-02-29",
                **fields,
            }
        ),
    )


def _counts(store: DrawerStore) -> tuple[int, int]:
    return (
        store._conn.execute("SELECT count(*) FROM drawers").fetchone()[0],
        store._conn.execute("SELECT count(*) FROM procedure_records").fetchone()[0],
    )


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def test_legacy_wire_content_and_hash_stay_exact(bundle: Any) -> None:
    store, book, spec = bundle
    first = book.propose(wing="governance", spec=spec)
    payload = asdict(spec)
    payload.pop("governance", None)
    assert (
        first.revision_sha256
        == hashlib.sha256(
            _canonical({"wing": "governance", "spec": payload}).encode("utf-8")
        ).hexdigest()
    )
    assert store.get(first.drawer_id).content == (
        f"Discovery: {spec.title}\nState: candidate\n\n{_canonical(payload)}"
    )
    saved = json.loads(
        store._conn.execute(
            "SELECT payload FROM procedure_records WHERE drawer_id=?", (first.drawer_id,)
        ).fetchone()[0]
    )
    assert "governance" not in saved["spec"]
    assert book.history(first.drawer_id)[0] == first


def test_opt_in_history_is_append_only_and_versions_are_family_specific(bundle: Any) -> None:
    store, book, spec = bundle
    legacy = book.propose(wing="governance", spec=spec)
    original = store.get(legacy.drawer_id).content
    first = book.revise(legacy.drawer_id, spec=_governed(spec))
    second = book.revise(first.drawer_id, spec=_governed(spec, "2", owner="New owner"))
    assert store.get(legacy.drawer_id).content == original
    assert [item.spec.governance for item in book.history(second.drawer_id)] == [
        None,
        first.spec.governance,
        second.spec.governance,
    ]
    before = _counts(store)
    for invalid in (spec, _governed(spec), _governed(spec, "2")):
        with pytest.raises(api.ProcedureError):
            book.revise(second.drawer_id, spec=invalid)
        assert _counts(store) == before
    other = book.propose(wing="governance", spec=_governed(spec))
    assert other.spec.governance.version == "1"
    assert book.rollback(second.drawer_id, reason="reviewed withdrawal").spec == second.spec


@pytest.mark.parametrize(
    "name,value",
    [
        ("owner", " "),
        ("owner", 1),
        ("owner", "bad\ud800"),
        ("version", " 1"),
        ("version", True),
        ("version", "bad\udfff"),
        ("rationale", None),
        ("rationale", "bad\ud800"),
        ("review_due", "2024-02-30"),
        ("review_due", "20240229"),
        ("review_due", "2024-W09-4"),
        ("review_due", "2024-2-29"),
        ("review_due", "2024-02-29 "),
        ("review_due", "bad\udfff"),
    ],
)
def test_invalid_governance_propose_and_revise_are_atomic(
    bundle: Any, name: str, value: Any
) -> None:
    store, book, spec = bundle
    first = book.propose(wing="governance", spec=_governed(spec))
    malformed = _governed(spec, "2", **{name: value})
    before = _counts(store)
    for action in (
        lambda: book.propose(wing="governance", spec=malformed),
        lambda: book.revise(first.drawer_id, spec=malformed),
    ):
        with pytest.raises(api.ProcedureError):
            action()
        assert _counts(store) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "Another"),
        ("version", "2"),
        ("rationale", "New reason"),
        ("review_due", "2027-01-01"),
    ],
)
def test_every_governance_field_binds_identity(bundle: Any, field: str, value: str) -> None:
    _, book, spec = bundle
    original = _governed(spec)
    first = book.propose(wing="governance", spec=original)
    changed = replace(original, governance=replace(original.governance, **{field: value}))
    second = book.propose(wing="governance", spec=changed)
    assert first.revision_sha256 != second.revision_sha256


@pytest.mark.parametrize("governance", [None, {}, {"owner": "only owner"}, "metadata"])
def test_malformed_stored_metadata_is_typed_on_public_reads(bundle: Any, governance: Any) -> None:
    store, book, spec = bundle
    first = book.propose(wing="governance", spec=_governed(spec))
    row = store._conn.execute(
        "SELECT payload FROM procedure_records WHERE drawer_id=?", (first.drawer_id,)
    ).fetchone()
    payload = json.loads(row[0])
    payload["spec"]["governance"] = governance
    store._conn.execute(
        "UPDATE procedure_records SET payload=? WHERE drawer_id=?",
        (json.dumps(payload), first.drawer_id),
    )
    for read in (
        lambda: book.history(first.drawer_id),
        lambda: book.list(wing="governance", active_only=False),
    ):
        with pytest.raises(api.ProcedureError):
            read()
