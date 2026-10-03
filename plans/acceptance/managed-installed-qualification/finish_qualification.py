"""Append routing amendment, static integration evidence, and a public seal."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
PUBLIC = CANDIDATE / "plans/acceptance/managed-installed-qualification"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    path = ROOT / name
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def assertions(raw):
    parsed = ast.parse(raw)
    ordered = sorted((node for node in ast.walk(parsed) if isinstance(node, ast.Assert)),
                     key=lambda node: (node.lineno, node.col_offset))
    return [ast.dump(node, include_attributes=False) for node in ordered]


def checked_command(name, command):
    result = subprocess.run(command, cwd=CANDIDATE, capture_output=True, timeout=25)
    (ROOT / (name + ".log")).write_bytes(result.stdout + result.stderr)
    write(name + ".json", {"command": command, "exit_code": result.returncode,
                           "model_or_install_execution": False})
    assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")


def main():
    old = ROOT / "test_managed_installed_qualification.py"
    before = old.read_text(encoding="utf-8")
    assert before.count("def runTest(self):") == 2
    amended = before.replace("def runTest(self):", "def runTest(self):  # noqa: N802 - required unittest override")
    assert ast.dump(ast.parse(before)) == ast.dump(ast.parse(amended))
    new = ROOT / "test_managed_installed_qualification_v2.py"
    assert not new.exists()
    new.write_text(amended, encoding="utf-8", newline="\n")
    router = CANDIDATE / "tests/unit/test_managed_installed_qualification.py"
    assert router.read_bytes() == old.read_bytes()
    shutil.copyfile(new, router)
    write("ROUTER-v2-FROZEN.json", {"prior_router_sha256": sha(old), "router_sha256": sha(new),
                                  "only_change": "two explained unittest method naming noqa comments",
                                  "entire_ast_unchanged": True,
                                  "installed_helper_and_freeze_unchanged": True})
    verifier = CANDIDATE / "scripts/verify_package.py"
    config = str(CANDIDATE / "pyproject.toml")
    checked_command("maintained-lint-final", [sys.executable, "-m", "ruff", "check", "--config", config, str(router), str(verifier)])
    checked_command("maintained-format-final", [sys.executable, "-m", "ruff", "format", "--check", "--config", config, str(router), str(verifier)])
    baseline = ROOT.parent / "verify_package.py.original"
    original = baseline.read_text(encoding="utf-8")
    current = verifier.read_text(encoding="utf-8")
    previous_assertions = assertions(original)
    current_assertions = assertions(current)
    assert len(previous_assertions) == 39
    index = 0
    positions = []
    for prior in previous_assertions:
        while current_assertions[index] != prior:
            index += 1
        positions.append(index)
        index += 1
    def definition(raw, name):
        return next(node for node in ast.walk(ast.parse(raw))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    for name in ["execute", "environment", "preserve_failed_question_proof"]:
        assert ast.dump(definition(original, name)) == ast.dump(definition(current, name)), name
    def question_call(raw):
        return next(node for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "verify_installed_questions")
    assert ast.dump(question_call(original)) == ast.dump(question_call(current))
    shutil.copyfile(baseline, ROOT / "verify_package.pre-amendment.py")
    shutil.copyfile(verifier, ROOT / "verify_package.final.py")
    write("INSTALLED-INTEGRATION.json", {
        "prior_verifier_sha256": sha(baseline), "final_verifier_sha256": sha(verifier),
        "prior_assertions_retained_in_order": len(previous_assertions),
        "generic_assertions": 35, "prior_question_binding_assertions": 4,
        "current_total_assertions": len(current_assertions),
        "unchanged_question_helper_call_ast": True,
        "unchanged_execute_environment_question_diagnostics_ast": True,
        "manifest_pin": "53a59ffa4e0dbfded002cc505ad335062074321faf8f70d4a841b1f4c612e0ad",
        "new_installed_proof": "four unchanged cases after all prior generic/question checks",
        "real_installed_model_execution": "hosted pending; none locally",
    })
    cases = list(ET.parse(ROOT / "local-controls.xml").getroot().iter("testcase"))
    assert len(cases) == 3 and all(not list(case.iter("failure")) and not list(case.iter("error")) for case in cases)
    write("FINAL-RESULT.json", {
        "status": "READY for three-platform hosted installed qualification",
        "local_inert_controls": "3PASS0.40s; no model/install/helper product case executed",
        "maintained_router_v2": "same complete AST as passing v1; two naming comments only",
        "retained_style_failure": "router-lint.log: two N802 unittest naming errors; preserved",
        "final_lint_and_line100_format": "PASS router and scripts/verify_package.py",
        "original_witnesses": "five files byte-identical to historical originals",
        "installed_cases_pending": "2 production CLI +2 projection API on all3 hosted platforms",
        "all39_existing_verifier_assertions": "unchanged ordered subsequence",
        "prior_source_acceptance_seal_unchanged": sha(CANDIDATE / "plans/acceptance/managed-session-port/SEAL.json"),
        "limits": "no new features; native activation/custody unverified; full hosted qualification pending",
    })
    selected = [path for path in ROOT.rglob("*") if path.is_file()
                and path.suffix in {".py", ".json", ".md", ".xml", ".log"}
                and "runtime-local" not in path.relative_to(ROOT).parts
                and "__pycache__" not in path.relative_to(ROOT).parts]
    for source in selected:
        target = PUBLIC / source.relative_to(ROOT)
        if target.exists():
            assert sha(source) == sha(target), target
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    bindings = {file.relative_to(PUBLIC).as_posix(): sha(file) for file in PUBLIC.rglob("*") if file.is_file()}
    assert not any(name.endswith((".db", ".db-wal", ".db-shm", ".pyc")) for name in bindings)
    write("SEAL.json", {"files_sha256": bindings, "maintained_router_sha256": sha(router),
                        "installed_verifier_sha256": sha(verifier), "installed_execution_pending": True})
    shutil.copyfile(ROOT / "SEAL.json", PUBLIC / "SEAL.json")
    print(json.dumps({"seal_sha256": sha(ROOT / "SEAL.json"), "artifacts": len(bindings),
                      "router_v2_sha256": sha(router), "verifier_sha256": sha(verifier)}))


if __name__ == "__main__":
    main()
