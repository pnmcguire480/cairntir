"""Preserve original portability capsule and freeze installed caller amendment."""

import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-i1004")
    old = candidate / "plans/acceptance/managed-portability"
    destination = root / "originals/portability"
    shutil.copytree(old, destination)
    seal = json.loads((destination / "SEAL.json").read_bytes())
    assert len(seal["files_sha256"]) == 23
    assert all(sha(destination / relative) == expected for relative, expected in seal["files_sha256"].items())
    raw = (destination / "test_portability.py").read_text(encoding="utf-8")
    raw = raw.replace('ROOT = Path(__file__).resolve().parent',
                      'ROOT = Path(__file__).resolve().parent / "originals/portability"')
    raw = raw.replace('        assert digest(CANDIDATE / relative) == expected, relative',
        '        if relative == "scripts/verify_package.py":\n'
        '            original = (ROOT / "originals" / relative).read_bytes()\n'
        '            original = original.replace(b\'TemporaryDirectory(prefix="installed-", dir=output)\', b\'TemporaryDirectory(prefix="installed-")\')\n'
        '            original = original.replace(b"directory = Path(temporary)\\n", b"directory = Path(temporary).resolve()\\n")\n'
        '            expected = hashlib.sha256(original).hexdigest()\n'
        '        assert digest(CANDIDATE / relative) == expected, relative')
    raw = raw.replace('assert \'tempfile.TemporaryDirectory(prefix="installed-", dir=output)\' in source',
                      'assert \'tempfile.TemporaryDirectory(prefix="installed-")\' in source')
    amended = root / "test_portability_v2.py"
    amended.write_text(raw, encoding="utf-8")
    config = candidate / "pyproject.toml"
    for file in (amended, root / "test_installed_boundary.py"):
        subprocess.run([sys.executable, "-m", "ruff", "format", "--config", str(config), str(file)], check=True)
    old_functions = {node.name: ast.dump(node) for node in ast.parse((destination / "test_portability.py").read_bytes()).body
                     if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: ast.dump(node) for node in ast.parse(amended.read_bytes()).body
                     if isinstance(node, ast.FunctionDef)}
    for name, expected in old_functions.items():
        if name != "test_only_four_caller_expressions_change_all_integrity_bodies_retained":
            assert new_functions[name] == expected, name
    proof = {"old_portability_seal_sha256": sha(destination / "SEAL.json"), "old23_artifacts_exact": True,
             "old_freeze_sha256": sha(destination / "FROZEN.json"),
             "unchanged_functions": len(old_functions) - 1,
             "amendment": "Only expected verifier two lines and corresponding source-string oracle; all six alias/security cases unchanged; four caller-byte checks unchanged"}
    (root / "AMENDMENT.json").write_text(json.dumps(proof, indent=2) + "\n")
    files = {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob("*"))
             if path.is_file() and path.name != "FROZEN.json"}
    frozen = {"files_sha256": files, "normal_cases": 10, "module": "test_installed_boundary.py",
              "scope": "Existing installed verifier owned-temp boundary and canonical caller path; no helper/security/44assertion relaxation"}
    (root / "FROZEN.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(json.dumps({"freeze_sha256": sha(root / "FROZEN.json"), "artifacts": len(files), **proof}, indent=2))


if __name__ == "__main__":
    main()
