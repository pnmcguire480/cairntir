"""Seal authored controls and preserved inputs before candidate implementation."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = ROOT / "ACCEPTANCE-FROZEN-v4.json"
    if target.exists():
        raise FileExistsError(target)
    for before_name, after_name in [
        ("test_installed_boundary_v3.py", "test_installed_boundary_v4.py"),
        ("test_portability_v3.py", "test_portability_v4.py"),
    ]:
        before = ast.parse((ROOT / "originals/boundary" / before_name).read_bytes())
        after = ast.parse((ROOT / after_name).read_bytes())

        def assertions(tree):
            return [
                ast.dump(node)
                for function in tree.body
                if isinstance(function, ast.FunctionDef)
                for node in ast.walk(function)
                if isinstance(node, ast.Assert)
            ]

        assert assertions(before) == assertions(after), after_name
    files = {
        path.relative_to(ROOT).as_posix(): digest(path)
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    frozen = {
        "version": 4,
        "scope": "same four installed cases; reviewed source pin and exact verifier routing",
        "normal_pytest_module": "test_installed_followup.py",
        "normal_case_count": 24,
        "installed_manifest_sha256": digest(ROOT / "FROZEN.json"),
        "historical_installed_manifest_sha256": digest(ROOT / "HISTORICAL-INSTALLED-FROZEN.json"),
        "historical_boundary_seal_sha256": digest(ROOT / "originals/boundary/SEAL.json"),
        "inherited_boundary_assertion_asts_identical": True,
        "files_sha256": files,
        "local_models_installs_or_api_calls": False,
    }
    target.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"acceptance_freeze_sha256": digest(target), "files": len(files)}))


if __name__ == "__main__":
    main()
