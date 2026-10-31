"""Independent controls for metadata refusal and published receipt identity."""

import json
import shutil
import sys
from pathlib import Path

from cairntir import paladin_bootstrap as bootstrap

from . import inputs

if sys.flags.optimize:
    raise RuntimeError("Q07 acceptance requires Python assertions")

HERE = Path(__file__).resolve().parent

BASE = HERE

LOCK = BASE / "approved-pytest.lock"

LOCK_SHA256 = "f5f398537450c12c66aee3bb76d2e773bcad55f421568305beeb2bdb251be99d"


def _settings() -> dict:
    inputs.observed_versions()
    return inputs.settings()


def test_replay_refuses_each_misreported_published_path_or_origin(tmp_path: Path) -> None:
    project = Path(shutil.copytree(BASE / "fixtures/clean", tmp_path / "project"))
    output = tmp_path / "output"
    first = bootstrap.prepare_test_bootstrap(project, output, **_settings())
    assert first["status"] == "PREPARED"
    manifest = Path(first["manifest_path"])
    original = manifest.read_bytes()
    for field in (
        "snapshot_path",
        "venv_path",
        "manifest_path",
        "python_origin",
        "pytest_origin",
    ):
        modified = json.loads(original)
        modified[field] = str(tmp_path / "false-provenance" / field)
        tampered = (json.dumps(modified, sort_keys=True) + "\n").encode()
        manifest.write_bytes(tampered)
        try:
            refused = bootstrap.prepare_test_bootstrap(project, output, **_settings())
            assert refused["status"] == "BLOCKED", field
            assert refused["blocker"]["code"] == "SNAPSHOT_TAMPERED", field
            assert manifest.read_bytes() == tampered
        finally:
            manifest.write_bytes(original)
