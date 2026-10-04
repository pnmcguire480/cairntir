"""Freeze independent repair controls and original evidence before candidate runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifests = [
        "managed-session-port/FREEZE.json", "managed-session-port/marker-amendment-v2/FREEZE.json",
        "managed-session-port/raw-projection-amendment-v3/FREEZE.json",
        "managed-session-port/visibility-v1/FREEZE.json", "managed-session-port/visibility-v2/FREEZE.json",
        "managed-session-port/SEAL.json", "managed-installed-qualification/FROZEN.json",
        "managed-installed-qualification/SEAL.json", "v2-managed-projection/FROZEN.json",
        "v2-managed-projection/PACKAGE-FROZEN.json", "v2-managed-runtime/PACKAGE-FROZEN.json",
        "v2-managed-runtime/STATE-FOLLOWUP.json",
    ]
    baseline = {}
    for relative in manifests:
        source = BASE / "plans/acceptance" / relative
        raw = source.read_bytes()
        destination = ROOT / "originals/plans/acceptance" / (relative + ".raw")
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert not destination.exists()
        destination.write_bytes(raw)
        parsed = json.loads(raw)
        baseline[relative] = {"sha256": sha(source), "entries": len(parsed.get("files_sha256", parsed.get("files", {})))}
    (ROOT / "MANIFEST-BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    path = ROOT / "test_managed_archive_acceptance.py"
    result = subprocess.run([sys.executable, "-m", "ruff", "format", "--config", str(BASE / "pyproject.toml"), str(path)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    originals = json.loads((ROOT / "RESOURCE-MAP.json").read_bytes())
    assert len(originals) == 8
    for value in originals.values():
        assert sha(ROOT / value["input"]) == value["sha256"]
        assert (ROOT / value["input"]).stat().st_size == value["size"]
    selected = [file for file in ROOT.rglob("*") if file.is_file()
                and "__pycache__" not in file.relative_to(ROOT).parts
                and file.name != "FROZEN.json"]
    manifest = {
        "version": 1,
        "files_sha256": {file.relative_to(ROOT).as_posix(): sha(file) for file in selected},
        "structural_archive_controls": 15,
        "same_behavior_active_cases": "25 durable/visibility plus11 original projection cases",
        "eight_exact_resource_paths": list(originals),
        "original_manifest_entry_checks": sum(value["entries"] for value in baseline.values()),
        "archive_api": "restore(source_root:Path,destination_root:Path)->Path; new disposable destination only",
        "runtime_or_tests_executed": False,
        "runtime_change_authorized": False,
        "hosted_codeql_outcome": "pending; no exclusions/dismissals/query changes",
    }
    freeze = ROOT / "FROZEN.json"
    assert not freeze.exists()
    freeze.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"freeze_sha256": sha(freeze), "artifacts": len(selected),
                      "original_manifest_entries": manifest["original_manifest_entry_checks"]}))


if __name__ == "__main__":
    main()
