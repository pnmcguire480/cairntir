"""Create the additive installed proof capsule without executing product cases."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

PACKET = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
HISTORICAL = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-final-0930")
PUBLIC = CANDIDATE / "plans/acceptance/managed-installed-qualification"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    assert not path.exists(), path
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    originals = PACKET / "originals"
    originals.mkdir()
    paths = {name: "v2-managed-runtime" for name in ["test_managed_process.py", "test_managed_config.py", "process_child.py", "process_driver.py"]}
    paths["test_managed_projection.py"] = "v2-managed-projection"
    custody = {}
    for filename, folder in paths.items():
        inherited = CANDIDATE / "plans/acceptance" / folder / filename
        raw_original = HISTORICAL / "plans/acceptance" / folder / filename
        assert inherited.read_bytes() == raw_original.read_bytes(), filename
        shutil.copyfile(inherited, originals / filename)
        custody[filename] = sha(raw_original)
    config = str(CANDIDATE / "pyproject.toml")
    for filename in ["verify_installed_managed.py", "test_managed_installed_qualification.py"]:
        result = subprocess.run([sys.executable, "-m", "ruff", "format", "--config", config, str(PACKET / filename)], capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
    sources = ["managed.py", "managed_projection.py", "memory/store.py", "access.py", "cli.py", "tasks.py", "obsidian.py"]
    files = [PACKET / "verify_installed_managed.py", PACKET / "CONTRACT.md", *originals.iterdir()]
    frozen = {
        "version": 1,
        "production_cli_cases": 2,
        "projection_api_cases": 2,
        "originals_byte_identical": True,
        "originals_sha256": custody,
        "files_sha256": {file.relative_to(PACKET).as_posix(): sha(file) for file in files},
        "installed_source_sha256": {name: sha(CANDIDATE / "src/cairntir" / name) for name in sources},
        "case_selection": [
            "test_real_cli_jsonl_start_capture_brief_ack_dispatch_close",
            "test_cli_changed_config_cannot_launch_using_previous_ack",
            "test_exact_checkpoint_descriptions_and_source_links",
            "test_read_only_restart_and_exact_human_bytes",
        ],
        "hosted_only": True,
        "local_installed_or_model_execution": False,
        "historical_generic_verifier_sha256": sha(HISTORICAL / "scripts/verify_package.py"),
        "prior_managed_seal_sha256": sha(CANDIDATE / "plans/acceptance/managed-session-port/SEAL.json"),
    }
    write(PACKET / "FROZEN.json", frozen)
    router = PACKET / "test_managed_installed_qualification.py"
    raw = router.read_text(encoding="utf-8")
    assert raw.count("REPLACE_FREEZE_HASH") == 1
    router.write_text(raw.replace("REPLACE_FREEZE_HASH", sha(PACKET / "FROZEN.json")), encoding="utf-8", newline="\n")
    result = subprocess.run([sys.executable, "-m", "ruff", "format", "--config", config, str(router)], capture_output=True, timeout=20)
    assert result.returncode == 0
    write(PACKET / "ROUTER-FROZEN.json", {"router_sha256": sha(router), "freeze_sha256": sha(PACKET / "FROZEN.json"), "local_synthetic_cases": 3})
    PUBLIC.mkdir(parents=True)
    for file in [*files, PACKET / "FROZEN.json", PACKET / "ROUTER-FROZEN.json", router]:
        destination = PUBLIC / file.relative_to(PACKET)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, destination)
        assert sha(file) == sha(destination)
    target = CANDIDATE / "tests/unit/test_managed_installed_qualification.py"
    assert not target.exists()
    shutil.copyfile(router, target)
    print(json.dumps({"public_folder": str(PUBLIC), "helper_sha256": sha(PACKET / "verify_installed_managed.py"), "freeze_sha256": sha(PACKET / "FROZEN.json"), "router_sha256": sha(router)}))


if __name__ == "__main__":
    main()
