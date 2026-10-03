"""Independently bind the final root-owned diagnostic-only verifier hook."""

import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-questions-work-20261003")
BASE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-combined-work-v2-20261003")
source = (ROOT / "scripts/verify_package.py").read_bytes()
old_source = (BASE / "scripts/verify_package.py").read_bytes()


def assertions(data):
    return Counter(
        ast.dump(node, include_attributes=False)
        for node in ast.walk(ast.parse(data))
        if isinstance(node, ast.Assert)
    )


before, after = assertions(old_source), assertions(source)
missing = before - after
if missing:
    raise RuntimeError("existing generic verifier assertions changed or removed")
receipt = {
    "status": "PASS_STATIC_BINDING",
    "verifier_sha256": hashlib.sha256(source).hexdigest(),
    "generic_base_verifier_sha256": hashlib.sha256(old_source).hexdigest(),
    "original_generic_assertions_retained": sum(before.values()),
    "current_verifier_assertions": sum(after.values()),
    "helper_sha256": hashlib.sha256((HERE / "verify_installed_questions_v2.py").read_bytes()).hexdigest(),
    "freeze_sha256": hashlib.sha256((HERE / "FROZEN.json").read_bytes()).hexdigest(),
    "helper_hash_bound_via_frozen_manifest": True,
    "execution": "none; no install or model construction",
    "hosted_diagnostic_attempt": "pending; original Windows cause remains unresolved",
}
target = HERE / "FINAL-HOOK-BINDING.json"
if target.exists():
    raise RuntimeError("append-only hook binding already exists")
target.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
destination = ROOT / "plans/acceptance/questions-installed-ci-1.16-v2" / target.name
if destination.exists():
    raise RuntimeError("public hook binding already exists")
destination.write_bytes(target.read_bytes())
print(json.dumps(receipt, indent=2))
