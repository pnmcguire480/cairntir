"""Append public test evidence without changing any preceding sealed packet."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXTERNAL = HERE.parent
OLD = EXTERNAL / "acceptance"
ROOT = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-questions-work-20261003")
PUBLIC = ROOT / "plans/acceptance/questions-installed-ci-1.16-v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old_seal = json.loads((OLD / "SEAL.json").read_text())
    sealed = old_seal["files_sha256"]
    for relative, expected in sealed.items():
        if sha(OLD / relative) != expected:
            raise RuntimeError(f"old external seal changed: {relative}")
        if sha(ROOT / "plans/acceptance/questions-port-1.16" / relative) != expected:
            raise RuntimeError(f"old public seal changed: {relative}")
    source = json.loads((OLD / "FINAL-SOURCE-BINDING.json").read_text())["files_sha256"]
    matched = {}
    for relative, expected in source.items():
        if relative == "scripts/verify_package.py":
            continue
        actual = sha(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"product or package binding changed: {relative}")
        matched[relative] = actual
    v1 = (HERE / "originals/verify_installed_questions_v1.py").read_bytes()
    v2 = (HERE / "verify_installed_questions_v2.py").read_bytes()
    assertion_count = sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(v1)))
    receipt = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "status": "READY_FOR_ONE_DIAGNOSTIC_HOSTED_ATTEMPT",
        "original_cause": "UNRESOLVED",
        "product_fix": "none justified by available evidence",
        "old_sealed_artifacts_verified": len(sealed),
        "old_seal_sha256": sha(OLD / "SEAL.json"),
        "product_and_package_bindings_unchanged": matched,
        "original_helper_assertions_retained": assertion_count,
        "original_helper_byte_prefix_retained": v2.startswith(v1),
        "amended_helper_sha256": sha(HERE / "verify_installed_questions_v2.py"),
        "freeze_sha256": sha(HERE / "FROZEN.json"),
        "normal_pytest_router_sha256": sha(ROOT / "tests/unit/test_question_installed_diagnostic.py"),
        "bounded_diagnostic_controls": {"passed": 4, "seconds": 0.16},
        "normal_pytest_router": {"passed": 4, "seconds": 0.17,
                                 "local_warning": "asyncio_mode unknown; plugins deliberately off"},
        "actual_candidate_router_lint_and_line100_format": "PASS",
        "local_source_probe": {
            "attempts": 2,
            "v1": "taskkill denied at first exit; 4.20 seconds; no product failure claim",
            "v1_owned_pid": 17804,
            "v1_cleanup": "exact PID absent after driver exit; no broad cleanup performed",
            "v2": "unchanged original helper passed after two direct owned abrupt terminations",
            "v2_seconds": 9.078,
            "v2_cli_calls": 7, "v2_mcp_processes": 2, "v2_mcp_tool_calls": 5,
            "exact_installed_launcher_taskkill_path": "not reproduced locally",
        },
        "no_retries_delay_count_relocation_or_reader_substitution": True,
        "failure_behavior": "same original exception rethrown with diagnostic JSON note",
        "success_behavior": "same original return; separate question-proof-diagnostic.json",
        "runtime_models_installs_network_private_stores": "not used",
        "raw_external_probe_receipts_sha256": {
            name: sha(EXTERNAL / "ci-installed-investigation" / name)
            for name in ("FROZEN.json", "V2-FROZEN.json", "result-direct.json", "result-direct-owned.json")
        },
    }
    target = HERE / "RESULT.json"
    if target.exists():
        raise RuntimeError("append-only result already exists")
    target.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for path in HERE.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        relative = path.relative_to(HERE)
        destination = PUBLIC / relative
        if destination.exists():
            if destination.read_bytes() != path.read_bytes():
                raise RuntimeError(f"already copied artifact differs: {relative}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    print(json.dumps({"status": receipt["status"], "sealed_artifacts": len(sealed),
                      "original_helper_assertions": assertion_count,
                      "result_sha256": sha(target)}, indent=2))


if __name__ == "__main__":
    main()
