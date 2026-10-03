"""Preserve v1 and freeze only the projection fixture's generated markers."""

import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
AMEND = HERE / "marker-amendment-v2"
AMEND.mkdir(exist_ok=True)
source = HERE / "test_managed_durable_boundaries.py"
original = source.read_bytes()
updated = original
for before, after in (
    (b"<!-- cairntir:begin -->", b"<!-- cairntir:generated:begin -->"),
    (b"<!-- cairntir:end -->", b"<!-- cairntir:generated:end -->"),
):
    if updated.count(before) != 1:
        raise RuntimeError("expected exactly one inert fixture marker occurrence")
    updated = updated.replace(before, after)
before = [ast.dump(node) for node in ast.walk(ast.parse(original)) if isinstance(node, ast.Assert)]
after = [ast.dump(node) for node in ast.walk(ast.parse(updated)) if isinstance(node, ast.Assert)]
if before != after:
    raise RuntimeError("assertion changed during fixture-only amendment")
target = AMEND / "test_managed_durable_boundaries_v2.py"
if target.exists():
    raise RuntimeError("append-only marker fixture already exists")
target.write_bytes(updated)
freeze = {
    "version": 2,
    "kind": "projection fixture only",
    "prior_freeze_sha256": hashlib.sha256((HERE / "FREEZE.json").read_bytes()).hexdigest(),
    "prior_test_sha256": hashlib.sha256(original).hexdigest(),
    "files_sha256": {target.name: hashlib.sha256(updated).hexdigest()},
    "all_assertion_asts_unchanged": True,
    "assertions": len(before),
    "change": "two fixture marker literals now match existing qualified obsidian generated block markers",
    "old_baseline_retained_by_root": "baseline24routing2: 16 fail/8 pass, projection fixture failures distinct",
    "next_execution": "four projection cases only on unchanged historical product port",
}
(AMEND / "FREEZE.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")
print(json.dumps({"amendment_freeze_sha256": hashlib.sha256((AMEND / "FREEZE.json").read_bytes()).hexdigest(),
                  "test_sha256": freeze["files_sha256"][target.name], "assertions": len(before)}))
