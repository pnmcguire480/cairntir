"""Freeze caller-only portability scope before the scoped repair or execution."""

import hashlib
import json
import shutil
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    candidate = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-hosted-repair-20261003")
    routers = ["tests/unit/" + name for name in (
        "test_managed_runtime.py", "test_last_session_projection.py",
        "test_managed_port_acceptance.py", "test_managed_installed_qualification.py",
    )]
    unchanged = ["scripts/restore_managed_evidence.py", "scripts/verify_package.py"]
    for relative in routers + unchanged:
        destination = root / "originals" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / relative, destination)
    baseline = {"routers": routers, "unchanged": {
        relative: hashlib.sha256((candidate / relative).read_bytes()).hexdigest()
        for relative in unchanged}, "input_head": "ca96e787"}
    (root / "BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n")
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*")) if path.is_file() and path.name != "FROZEN.json"}
    frozen = {"files_sha256": files, "cases": 7,
              "contract": "Only four caller expressions canonicalize their owned TemporaryDirectory parent; security helper, verifier and all original integrity bodies remain unchanged",
              "evidence_limits": "Mocked filesystem alias; actual macOS collection validated by future hosted CI; no privileged symlinks, model loads or installs"}
    (root / "FROZEN.json").write_text(json.dumps(frozen, indent=2) + "\n")
    print(hashlib.sha256((root / "FROZEN.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
