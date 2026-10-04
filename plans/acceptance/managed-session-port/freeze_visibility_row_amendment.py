"""Prove and freeze normalization of the owner's existing SQLite Row fixture."""

import ast
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE / "visibility-v1"
AMEND = HERE / "visibility-v2"
AMEND.mkdir(exist_ok=True)
with closing(sqlite3.connect(":memory:")) as connection:
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT ? AS content", ("exact fixture content",)).fetchone()
    if row == ("exact fixture content",) or tuple(row) != ("exact fixture content",):
        raise RuntimeError("independent stdlib row behavior differs")
proof = {
    "status": "PASS",
    "product_imported": False,
    "sqlite_row_direct_tuple_equality": False,
    "sqlite_row_normalized_tuple_equality": True,
    "column_content_unchanged": True,
}
(AMEND / "ROW-FIXTURE-PROOF.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
original = (PRIOR / "test_hidden_event.py").read_bytes()
before = (
    b'    assert owner._conn.execute(\n'
    b'        "SELECT content FROM drawers WHERE id=?", (second["drawer_id"],)\n'
    b'    ).fetchone() == (hidden_text,)\n'
)
after = (
    b'    assert tuple(\n'
    b'        owner._conn.execute(\n'
    b'            "SELECT content FROM drawers WHERE id=?", (second["drawer_id"],)\n'
    b'        ).fetchone()\n'
    b'    ) == (hidden_text,)\n'
)
if original.count(before) != 1:
    raise RuntimeError("expected exactly one owner Row fixture assertion")
updated = original.replace(before, after)
old_asserts = [node for node in ast.walk(ast.parse(original)) if isinstance(node, ast.Assert)]
new_asserts = [node for node in ast.walk(ast.parse(updated)) if isinstance(node, ast.Assert)]
changed = []
for index, (old, new) in enumerate(zip(old_asserts, new_asserts, strict=True)):
    if ast.dump(old) != ast.dump(new):
        changed.append(index)
        left = new.test.left
        if not isinstance(left, ast.Call) or not isinstance(left.func, ast.Name) or left.func.id != "tuple":
            raise RuntimeError("fixture assertion change is not tuple normalization")
        new.test.left = left.args[0]
        if ast.dump(new) != ast.dump(old):
            raise RuntimeError("normalization changed the underlying exact-content assertion")
if len(changed) != 1:
    raise RuntimeError("expected only one normalized assertion")
target = AMEND / "test_hidden_event_v2.py"
if target.exists():
    raise RuntimeError("append-only visibility overlay already exists")
target.write_bytes(updated)
freeze = {
    "version": 2,
    "cases": 1,
    "files_sha256": {
        name: hashlib.sha256((AMEND / name).read_bytes()).hexdigest()
        for name in (target.name, "ROW-FIXTURE-PROOF.json")
    },
    "fixture_dependency_sha256": {
        "raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py": "0fdb5c914a9bd912084f1a110ba0cc3f1c634b0baa0ae2ab4a7ad4aa4ca2ed94"
    },
    "prior_freeze_sha256": hashlib.sha256((PRIOR / "FREEZE.json").read_bytes()).hexdigest(),
    "prior_test_sha256": hashlib.sha256(original).hexdigest(),
    "only_change": "tuple-normalize sqlite3.Row; original SELECT, drawer ID and exact content tuple unchanged",
    "all_other_assertion_asts_unchanged": True,
    "assertions": len(old_asserts),
    "runtime_changes": "none",
    "preserved_result": "candidate-repair2-final:80 pass/3 skip/9 subtests; one Row-vs-tuple fixture failure",
}
(AMEND / "FREEZE.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")
print(json.dumps({"freeze_sha256": hashlib.sha256((AMEND / "FREEZE.json").read_bytes()).hexdigest(),
                  "test_sha256": freeze["files_sha256"][target.name], "sqlite_only_proof": proof}))
