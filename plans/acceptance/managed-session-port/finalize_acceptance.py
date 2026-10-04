"""Seal bounded independent managed acceptance, preserving every prior version."""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

PACKET = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
PUBLIC = CANDIDATE / "plans/acceptance/managed-session-port"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    destination = PACKET / name
    assert not destination.exists(), destination
    destination.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def cases(name):
    root = ET.parse(PACKET / name).getroot()
    return list(root.iter("testcase"))


def main():
    prior = json.loads((PACKET / "candidate-repair2-source.json").read_text())
    cli_raw = (CANDIDATE / "src/cairntir/cli.py").read_bytes()
    restored_import = b"from typing import Annotated, Any, cast"
    assert cli_raw.count(restored_import) == 1
    original_cli = cli_raw.replace(restored_import, b"from typing import Any, cast")
    assert hashlib.sha256(original_cli).hexdigest() == prior["files_sha256"]["src/cairntir/cli.py"]
    for relative, digest in prior["files_sha256"].items():
        if relative != "src/cairntir/cli.py":
            assert sha(CANDIDATE / relative) == digest, relative
    write("CLI-IMPORT-AMENDMENT-BINDING.json", {
        "prior_cli_sha256": prior["files_sha256"]["src/cairntir/cli.py"],
        "final_cli_sha256": sha(CANDIDATE / "src/cairntir/cli.py"),
        "independent_byte_proof": "Removing only Annotated from the typing import reproduces exact prior CLI hash",
        "prior_source_evidence_unchanged": "candidate-repair2-source.json",
        "scope": "mechanical port omission restored after two managed behavioral repairs",
        "runtime_projection_files_unchanged": True,
        "existing_cli_oracle": "root-reports/importR08.log:48PASS51subtests",
    })
    frozen_count = 0
    for relative in ["FREEZE.json", "marker-amendment-v2/FREEZE.json",
                     "raw-projection-amendment-v3/FREEZE.json", "visibility-v1/FREEZE.json",
                     "visibility-v2/FREEZE.json"]:
        manifest_path = PACKET / relative
        manifest = json.loads(manifest_path.read_text())
        for filename, digest in manifest["files_sha256"].items():
            assert sha(manifest_path.parent / filename) == digest, filename
            frozen_count += 1
        for filename, digest in manifest.get("fixture_dependency_sha256", {}).items():
            assert sha(PACKET / filename) == digest, filename
    final = cases("router-v4-final25.xml")
    assert len(final) == 25
    assert all(not list(case.iter("failure")) and not list(case.iter("error"))
               and not list(case.iter("skipped")) for case in final)
    negative = cases("ambient-guard-wrong-control.xml")
    assert len(negative) == 1 and len(list(negative[0].iter("failure"))) == 1
    assert not list(negative[0].iter("error"))
    assert "DID NOT RAISE" in (negative[0].find("failure").text or "")
    replay = json.loads((PACKET / "replay-wrong-control-result.json").read_text())
    assert replay["meaningful_detection"] is True and replay["errors"] == 0
    assert replay["failures"] == 1 and len(replay["external_markers"][0]) == 2
    oracle = json.loads((PACKET / "pre-action-oracle-controls.log").read_text(encoding="utf-8"))
    assert oracle["status"] == "PASS" and oracle["uncommitted_control"]["exit_code"] == 23
    assert oracle["committed_control"]["markers"] == 1
    execution = json.loads((PACKET / "pre-action-oracle-controls-execution.json").read_text())
    assert execution["exit_code"] == 0
    write("ORACLE-HARNESS-PRINT-LIMITATION.json", {
        "type": "owned console harness error after successful control execution",
        "error": "UnicodeEncodeError: cp1252 cannot print U+1F9ED",
        "original_subprocess_exit": 0,
        "raw_result_preserved": "pre-action-oracle-controls.log",
        "control_rerun": False,
        "product_failure": False,
    })
    root_reports = PACKET / "root-reports"
    root_reports.mkdir()
    names = ["WORK-COPY.json", "PORT-BASELINE.json", "REPAIR-1.json", "REPAIR-2.json",
             "baseline24-source.json", "baseline24.json", "baseline24.log",
             "baseline24routing2-source.json", "baseline24routing2.json", "baseline24routing2.log",
             "repair1-source.json", "repair1.json", "repair1.log",
             "repair1routing2-source.json", "repair1routing2.json", "repair1routing2.log",
             "repair2-source.json", "historical1-source.json", "historical1.json", "historical1.log",
             "CLI-IMPORT-AMENDMENT.md", "retainedR08-source.json", "retainedR08.json", "retainedR08.log",
             "importR08.json", "importR08.log", "staticlint.json", "staticlint.log",
             "staticformat.json", "staticformat.log", "integrationfinal-source.json",
             "importlint.json", "importlint.log", "importformat.json", "importformat.log"]
    for name in names:
        shutil.copyfile(PACKET.parent / name, root_reports / name)
    runtime_files = dict(prior["files_sha256"])
    runtime_files["src/cairntir/cli.py"] = sha(CANDIDATE / "src/cairntir/cli.py")
    metadata = {relative: sha(CANDIDATE / relative) for relative in [
        "src/cairntir/__init__.py", "pyproject.toml", "scripts/verify_package.py"]}
    router_path = CANDIDATE / "tests/unit/test_managed_port_acceptance.py"
    router = json.loads((PACKET / "ROUTER-v4-FROZEN.json").read_text())
    assert sha(router_path) == router["maintained_router_sha256"]
    write("FINAL-SOURCE-BINDINGS.json", {
        "base": "c71abb6808dffe75d9c303734f80f667d5c81cba",
        "runtime_files_sha256": runtime_files,
        "metadata_and_existing_installed_verifier_sha256": metadata,
        "maintained_router_path": "tests/unit/test_managed_port_acceptance.py",
        "maintained_router_sha256": sha(router_path),
        "managed_and_projection_unchanged_since_final_repair2_run": True,
        "separate_mechanical_cli_import_amendment": "CLI-IMPORT-AMENDMENT-BINDING.json",
        "checked_frozen_artifact_entries": frozen_count,
        "freeze_sha256": {relative: sha(PACKET / relative) for relative in [
            "FREEZE.json", "marker-amendment-v2/FREEZE.json",
            "raw-projection-amendment-v3/FREEZE.json", "visibility-v1/FREEZE.json",
            "visibility-v2/FREEZE.json"]},
    })
    write("FINAL-RESULT.json", {
        "status": "PASS bounded source qualification; hosted/installed qualification pending",
        "fresh_normal_router": {"passed": 25, "failed": 0, "seconds": 2.33,
                                "version": 4, "receipt": "router-v4-final25.xml"},
        "historical_repair2": {"passed": 56, "skipped": 3, "subtests_passed": 9,
                              "receipt": "candidate-repair2-final.xml"},
        "distinct_passed_cases": 81,
        "retained_combined_repair2_run": {"passed": 80, "skipped": 3,
            "fixture_failure": "visibility-v1 sqlite3.Row compared directly to tuple",
            "subtests_passed": 9, "seconds": 16.35},
        "fixture_amendments": ["v2 correct generated markers", "v3 raw caller transaction fixture avoids nested public checkpoint BEGIN",
                               "visibility-v2 tuple normalization preserves exact raw content oracle"],
        "product_repairs_used": 2,
        "separate_mechanical_port_correction": "CLI Annotated import restored; exact prior bytes reconstructed independently; unchanged retained R08 route48PASS51subtests",
        "negative_controls": {
            "ambient_guard_bypass": "unchanged DID NOT RAISE assertion: 1 failure,0 errors,1.04s",
            "pre_action_oracle": "uncommitted child denied exit23/no marker; committed child exit0/one marker",
            "replay_bypass": "unchanged uncertain-status assertion: 1 failure,0 errors,2.202s; two external markers"},
        "skips": ["two historical CLI production-model prerequisites explicitly deferred",
                  "Windows symlink privilege fixture unavailable"],
        "limits": ["synthetic disposable stores/processes only", "no native automatic activation or user-host custody claim",
                   "no live hooks/auth/installs/models/API inference/full local suite or coverage",
                   "fresh hosted and installed/model qualification remains pending"],
        "warnings": ["pytest asyncio_mode unknown because plugin autoload disabled; all selected controls ran"],
        "source_binding": "FINAL-SOURCE-BINDINGS.json",
        "native_gui_or_operator_acceptance": "unverified",
    })
    allowed = {".py", ".json", ".md", ".log", ".xml", ".txt"}
    selected = [path for path in PACKET.rglob("*") if path.is_file()
                and path.suffix in allowed and "runtime-final" not in path.relative_to(PACKET).parts
                and "__pycache__" not in path.relative_to(PACKET).parts]
    for file in selected:
        relative = file.relative_to(PACKET)
        destination = PUBLIC / relative
        if destination.exists():
            assert sha(destination) == sha(file), relative
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)
    bindings = {file.relative_to(PUBLIC).as_posix(): sha(file) for file in PUBLIC.rglob("*")
                if file.is_file() and "__pycache__" not in file.relative_to(PUBLIC).parts}
    assert not any(name.endswith((".db", ".db-wal", ".db-shm", ".pyc")) for name in bindings)
    write("SEAL.json", {
        "sealed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "public_folder": "plans/acceptance/managed-session-port",
        "files_sha256": dict(sorted(bindings.items())),
        "result": "FINAL-RESULT.json",
        "maintained_router_sha256": sha(router_path),
        "runtime_receipts_final": True,
    })
    shutil.copyfile(PACKET / "SEAL.json", PUBLIC / "SEAL.json")
    print(json.dumps({"seal_sha256": sha(PACKET / "SEAL.json"), "artifacts": len(bindings),
                      "router_sha256": sha(router_path), "source_binding_sha256": sha(PACKET / "FINAL-SOURCE-BINDINGS.json")}))


if __name__ == "__main__":
    main()
