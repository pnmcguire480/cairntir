"""Preserve exact inputs and author finite active fixture amendments externally."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
FILES = [
    "plans/acceptance/managed-session-port/visibility-v1/test_hidden_event.py",
    "plans/acceptance/managed-session-port/visibility-v2/test_hidden_event_v2.py",
    "plans/acceptance/managed-session-port/test_managed_durable_boundaries.py",
    "plans/acceptance/managed-session-port/marker-amendment-v2/test_managed_durable_boundaries_v2.py",
    "plans/acceptance/managed-session-port/raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py",
    "plans/acceptance/managed-installed-qualification/originals/test_managed_projection.py",
    "plans/acceptance/v2-managed-projection/test_managed_projection.py",
    "plans/acceptance/v2-managed-runtime/evidence/repair-2-independent/run.py",
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assertions(source):
    return [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Assert)]


def main():
    originals = ROOT / "originals"
    originals.mkdir()
    records = {}
    for relative in FILES:
        raw = (BASE / relative).read_bytes()
        target = originals / (relative + ".raw")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        records[relative] = {"sha256": sha(raw), "size": len(raw),
                             "input": target.relative_to(ROOT).as_posix()}
    (ROOT / "RESOURCE-MAP.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    consumers = ["tests/unit/test_managed_port_acceptance.py", "tests/unit/test_managed_runtime.py",
                 "tests/unit/test_last_session_projection.py", "tests/unit/test_managed_installed_qualification.py",
                 "scripts/check_verification_preservation.py", "scripts/verify_package.py",
                 "pyproject.toml"]
    consumer_hashes = {}
    for relative in consumers:
        raw = (BASE / relative).read_bytes()
        destination = originals / (relative + ".raw")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        consumer_hashes[relative] = sha(raw)
    (ROOT / "CONSUMER-BASELINE.json").write_text(json.dumps(consumer_hashes, indent=2) + "\n", encoding="utf-8")
    active = ROOT / "active"
    active.mkdir()
    durable = (BASE / FILES[4]).read_text(encoding="utf-8")
    old_cleanup = "    try:\n        yield bundle\n    finally:\n        owner.close()\n"
    beginning = "    owner = DrawerStore(path, HashEmbeddingProvider(dimension=16))\n"
    start = durable.index(beginning)
    end = durable.index(old_cleanup, start)
    body = durable[start + len(beginning):end]
    replacement = "    with DrawerStore(path, HashEmbeddingProvider(dimension=16)) as owner:\n"
    replacement += "".join("    " + line if line.strip() else line for line in body.splitlines(keepends=True))
    replacement += "        yield bundle\n"
    amended = durable[:start] + replacement + durable[end + len(old_cleanup):]
    header = "        with pytest.raises(CallerRollbackError), caller_transaction(bundle, store, style):\n"
    assert amended.count(header) == 2
    for _ in range(2):
        start = amended.index(header)
        end = amended.index("        assert store.transaction_active is False", start)
        body = amended[start + len(header):end]
        replacement = "        try:\n            with caller_transaction(bundle, store, style):\n"
        replacement += "".join("    " + line if line.strip() else line for line in body.splitlines(keepends=True))
        replacement += "        except CallerRollbackError:\n            pass\n        else:\n            pytest.fail('Caller rollback witness did not raise')\n"
        amended = amended[:start] + replacement + amended[end:]
    assert assertions(durable) == assertions(amended)
    (active / "test_managed_durable_boundaries_v4.py").write_text(amended, encoding="utf-8", newline="\n")
    visibility = (BASE / FILES[1]).read_text(encoding="utf-8")
    original_path = '(\n    Path(__file__).resolve().parents[1]\n    / "raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py"\n)'
    assert visibility.count(original_path) == 1
    amended_visibility = visibility.replace(original_path, 'Path(__file__).with_name("test_managed_durable_boundaries_v4.py")')
    side_effect = '    assert full.close(last_sequence=2)["capture_complete"] is True\n'
    assert amended_visibility.count(side_effect) == 1
    amended_visibility = amended_visibility.replace(side_effect,
        '    owner_closed = full.close(last_sequence=2)\n    assert owner_closed["capture_complete"] is True\n')
    normalized = amended_visibility.replace('    owner_closed = full.close(last_sequence=2)\n', '').replace(
        'assert owner_closed["capture_complete"] is True', 'assert full.close(last_sequence=2)["capture_complete"] is True')
    assert assertions(visibility) == assertions(normalized)
    (active / "test_hidden_event_v3.py").write_text(amended_visibility, encoding="utf-8", newline="\n")
    projection = (BASE / FILES[6]).read_text(encoding="utf-8")
    old_assert = "self.assertTrue(expected_ids <= sources.keys())"
    new_assert = "self.assertLessEqual(expected_ids, sources.keys())"
    assert projection.count(old_assert) == 1
    amended_projection = projection.replace(old_assert, new_assert)
    assert ast.dump(ast.parse(amended_projection.replace(new_assert, old_assert))) == ast.dump(ast.parse(projection))
    (active / "test_managed_projection_v2.py").write_text(amended_projection, encoding="utf-8", newline="\n")
    for path in active.glob("*.py"):
        result = subprocess.run([sys.executable, "-m", "ruff", "format", "--config", str(BASE / "pyproject.toml"), str(path)], capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
    proof = {"durable_assertion_asts_identical": len(assertions(durable)),
             "visibility_semantic_assertions_retained": len(assertions(visibility)),
             "projection_entire_ast_equal_after_exact_diagnostic_normalization": True,
             "active_files_sha256": {path.name: sha(path.read_bytes()) for path in active.glob("*.py")},
             "runtime_changes": False, "test_execution": False}
    (ROOT / "AMENDMENT-PROOF.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
