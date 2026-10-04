"""Create an additive, fixed-identity installed qualification capsule."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\ct-j1004")
PREVIOUS = ROOT.parents[1] / "cairntir-managed-installed-boundary-20261004/acceptance"
OLD_MANAGED = "31452b541883edae15687dc8587234ff38ef97d5b9500ab5f985dbcc94c2866b"
NEW_MANAGED = "7d1c1bfb8ebee9ee3eff89b5bdd5b87c9108830a98091c02d54cdd4dff652a93"
OLD_FREEZE = "53a59ffa4e0dbfded002cc505ad335062074321faf8f70d4a841b1f4c612e0ad"
OLD_SEAL = "48ef2fd354504a401fa95a19888aef908c5a537a8c153c6c6b2bf28f4fc2289e"
ARCHIVE_SHA = "1edcbfc15631a0803aa79b6b2cee7cc0524abab7681040b686bd73e5cd9f9735"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(relative, raw):
    path = ROOT / relative
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main():
    installed = CANDIDATE / "plans/acceptance/managed-installed-qualification"
    raw = (installed / "FROZEN.json").read_bytes()
    assert digest(raw) == OLD_FREEZE
    frozen = json.loads(raw)
    assert frozen["installed_source_sha256"]["managed.py"] == OLD_MANAGED
    assert digest((CANDIDATE / "src/cairntir/managed.py").read_bytes()) == NEW_MANAGED
    write("HISTORICAL-INSTALLED-FROZEN.json", raw)
    replacement = raw.replace(OLD_MANAGED.encode(), NEW_MANAGED.encode())
    assert replacement != raw and raw.count(OLD_MANAGED.encode()) == 1
    write("FROZEN.json", replacement)
    archive = CANDIDATE / "plans/acceptance/managed-evidence-archive/resources.zip"
    assert digest(archive.read_bytes()) == ARCHIVE_SHA
    with zipfile.ZipFile(archive) as resources:
        for relative, expected in frozen["files_sha256"].items():
            path = installed / relative
            content = (
                path.read_bytes()
                if path.exists()
                else resources.read(f"plans/acceptance/managed-installed-qualification/{relative}")
            )
            assert digest(content) == expected, relative
            write(relative, content)
    sealed = (PREVIOUS / "SEAL.json").read_bytes()
    assert digest(sealed) == OLD_SEAL
    for relative, expected in json.loads(sealed)["files_sha256"].items():
        content = (PREVIOUS / relative).read_bytes()
        assert digest(content) == expected, relative
        write(f"originals/boundary/{relative}", content)
    write("originals/boundary/SEAL.json", sealed)
    new_hash = digest(replacement)
    metadata = {
        "historical_installed_freeze_sha256": OLD_FREEZE,
        "installed_freeze_sha256": new_hash,
        "historical_boundary_seal_sha256": OLD_SEAL,
        "reviewed_runtime_change": {"managed.py": {"before": OLD_MANAGED, "after": NEW_MANAGED}},
        "helper_and_original_case_bytes_changed": False,
        "authorized_verifier_changes": [
            'TemporaryDirectory(prefix="installed-", dir=output) '
            '-> TemporaryDirectory(prefix="installed-")',
            "directory = Path(temporary) -> directory = Path(temporary).resolve()",
            "managed_source -> ROOT / plans/acceptance/managed-installed-followup",
            f"managed_hash -> {new_hash}",
            "managed_copy = directory / managed_proof -> restored.parent / managed_proof",
        ],
        "local_install_or_model_execution": False,
        "windows_sqlite_diagnostics": "separate lane; no cause claim",
    }
    write("AMENDMENT.json", (json.dumps(metadata, indent=2) + "\n").encode())
    print(json.dumps({"installed_freeze_sha256": new_hash, "historical_boundary_files": 44}))


if __name__ == "__main__":
    main()
