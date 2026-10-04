"""Retain v2 and freeze its one omitted canonical-assignment oracle update."""

import ast
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    old = root / "test_portability_v2.py"
    updated = root / "test_portability_v3.py"
    raw = old.read_bytes()
    old_literal = b'"directory = Path(temporary)"'
    assert raw.count(old_literal) == 1
    updated.write_bytes(raw.replace(old_literal, b'"directory = Path(temporary).resolve()"'))
    primary = root / "test_installed_boundary_v3.py"
    primary.write_bytes((root / "test_installed_boundary.py").read_bytes().replace(
        b'test_portability_v2.py', b'test_portability_v3.py').replace(
        b'installed_portability_v2', b'installed_portability_v3'))
    normalized = updated.read_bytes().replace(b'"directory = Path(temporary).resolve()"', old_literal)
    assert normalized == raw
    old_asserts = [ast.dump(node) for node in ast.walk(ast.parse((root / "test_installed_boundary.py").read_bytes()))
                  if isinstance(node, ast.Assert)]
    new_asserts = [ast.dump(node) for node in ast.walk(ast.parse(primary.read_bytes()))
                  if isinstance(node, ast.Assert)]
    assert old_asserts == new_asserts
    proof = {"issue": "v2 omitted inherited expected canonical assignment string update",
             "change": "Only directory = Path(temporary) expected AST string gains .resolve(); primary module only updates its v3 import filename/name",
             "old_freeze_sha256": sha(root / "FROZEN.json"),
             "old_portability_v2_sha256": sha(old), "portability_v3_sha256": sha(updated),
             "primary_assertions_identical": len(old_asserts),
             "preserved_failure": "candidate.log:9pass1fixturefailure; product probes and44assertions pass",
             "no_runtime_change": True}
    (root / "V3-AMENDMENT.json").write_text(json.dumps(proof, indent=2) + "\n")
    frozen = json.loads((root / "FROZEN.json").read_bytes())
    files = {**frozen["files_sha256"], "FROZEN.json": sha(root / "FROZEN.json"),
             "originals/portability/FROZEN.json": sha(root / "originals/portability/FROZEN.json"),
             updated.name: sha(updated), primary.name: sha(primary),
             "V3-AMENDMENT.json": sha(root / "V3-AMENDMENT.json"), "amend_v3.py": sha(Path(__file__))}
    assert all(sha(root / name) == expected for name, expected in files.items())
    (root / "FROZEN-v3.json").write_text(json.dumps({"files_sha256": files,
        "normal_cases": 10, "module": primary.name, "fixture_amendment_only": True}, indent=2) + "\n")
    print(json.dumps({"freeze_v3_sha256": sha(root / "FROZEN-v3.json"), "artifacts": len(files), **proof}, indent=2))


if __name__ == "__main__":
    main()
