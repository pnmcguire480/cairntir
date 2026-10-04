"""Freeze pytest reserved-name fixture amendment without changing behavior oracles."""

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    old = root / "test_managed_protocol.py"
    amended = root / "test_managed_protocol_v2.py"
    raw = old.read_text(encoding="utf-8")
    raw = raw.replace('"operation,request"', '"operation,payload"')
    raw = raw.replace(
        "def test_allowed_envelope_routes_exactly_one_public_operation(operation, request):",
        "def test_allowed_envelope_routes_exactly_one_public_operation(operation, payload):")
    begin = raw.index("def test_allowed_envelope_routes_exactly_one_public_operation")
    end = raw.index("\n\n@pytest.mark.parametrize", begin)
    raw = raw[:begin] + raw[begin:end].replace("operation, request", "operation, payload") + raw[end:]
    amended.write_text(raw, encoding="utf-8")
    config = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-r1004\pyproject.toml")
    subprocess.run([sys.executable, "-m", "ruff", "check", "--config", str(config),
                    "--select", "I", "--fix", str(amended)], check=True)
    subprocess.run([sys.executable, "-m", "ruff", "format", "--config", str(config),
                    str(amended)], check=True)

    def assertions(path, normalize):
        tree = ast.parse(path.read_bytes())
        if normalize:
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "payload":
                    node.id = "request"
        return [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.Assert)]

    previous = assertions(old, False)
    assert assertions(amended, True) == previous
    proof = {"issue": "pytest reserves request as a parametrized fixture name",
             "change": "Only first routing test parameter/local name request becomes payload; import sorting and line100 formatting",
             "assertions_unchanged_after_identifier_normalization": len(previous),
             "old_sha256": sha(old), "amended_sha256": sha(amended),
             "v1_freeze_sha256": sha(root / "FROZEN.json"),
             "preserved_collection_failure": "normal.log / normal-execution.json (no tests ran)"}
    (root / "V2-AMENDMENT.json").write_text(json.dumps(proof, indent=2) + "\n")
    original = json.loads((root / "FROZEN.json").read_bytes())["files_sha256"]
    assert all(sha(root / name) == expected for name, expected in original.items())
    files = {**original, "FROZEN.json": sha(root / "FROZEN.json"), amended.name: sha(amended),
             "V2-AMENDMENT.json": sha(root / "V2-AMENDMENT.json"), "amend_v2.py": sha(Path(__file__))}
    frozen = {"files_sha256": files, "normal_cases": 33, "wrong_control_cases": 1,
              "normal_module": amended.name, "fixture_amendment_only": True}
    (root / "FROZEN-v2.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(json.dumps({"freeze_v2_sha256": sha(root / "FROZEN-v2.json"), **proof}, indent=2))


if __name__ == "__main__":
    main()
