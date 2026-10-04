"""Keep explicit provisional checkpoints and make raw-writer setup compatible."""

import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE / "marker-amendment-v2"
AMEND = HERE / "raw-projection-amendment-v3"
AMEND.mkdir(exist_ok=True)
original = (PREVIOUS / "test_managed_durable_boundaries_v2.py").read_bytes()
before = b'            TaskBook(store).checkpoint(WING, ROOM, "Uncommitted caller checkpoint", checkpoint)\n'
after = (
    b'            if style == "explicit":\n'
    b'                TaskBook(store).checkpoint(WING, ROOM, "Uncommitted caller checkpoint", checkpoint)\n'
    b'            else:\n'
    b'                bundle.owner._conn.execute(\n'
    b'                    "INSERT INTO store_metadata(key,value) VALUES (?,?)",\n'
    b'                    ("managed_raw_caller_work", "raw uncommitted caller-owned marker"),\n'
    b'                )\n'
)
if original.count(before) != 1:
    raise RuntimeError("expected exactly one projection caller-setup line")
updated = original.replace(before, after)
old_asserts = [ast.dump(node) for node in ast.walk(ast.parse(original)) if isinstance(node, ast.Assert)]
new_asserts = [ast.dump(node) for node in ast.walk(ast.parse(updated)) if isinstance(node, ast.Assert)]
if old_asserts != new_asserts:
    raise RuntimeError("raw fixture amendment changed assertion")
target = AMEND / "test_managed_durable_boundaries_v3.py"
if target.exists():
    raise RuntimeError("append-only raw fixture already exists")
target.write_bytes(updated)
freeze = {
    "version": 3,
    "kind": "raw projection caller setup only",
    "previous_freeze_sha256": hashlib.sha256((PREVIOUS / "FREEZE.json").read_bytes()).hexdigest(),
    "previous_test_sha256": hashlib.sha256(original).hexdigest(),
    "files_sha256": {target.name: hashlib.sha256(updated).hexdigest()},
    "all_assertion_asts_unchanged": True,
    "assertions": len(old_asserts),
    "contract": "Explicit cases retain real provisional TaskBook checkpoint; raw cases retain committed valid checkpoint and insert unrelated uncommitted caller marker, because public TaskBook cannot nest into raw BEGIN. Both require renderer refusal and unchanged file/database/caller work. No transaction bypass or production change.",
    "preserved_previous_result": "projection-baseline-v2:2 genuine publication failures plus2 raw TaskBook fixture errors",
    "next_execution": "two raw projection cases only on unchanged historical product port",
}
(AMEND / "FREEZE.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")
print(json.dumps({"amendment_freeze_sha256": hashlib.sha256((AMEND / "FREEZE.json").read_bytes()).hexdigest(),
                  "test_sha256": freeze["files_sha256"][target.name], "assertions": len(old_asserts)}))
