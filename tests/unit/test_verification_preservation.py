from __future__ import annotations

import hashlib
import json
import runpy
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECKER = runpy.run_path(str(REPO / "scripts/check_verification_preservation.py"))
MANIFESTS = CHECKER["COUNCIL_MANIFESTS"]
ARTIFACTS = (
    "tests/acceptance/test_codex_unicode_council.py",
    "tests/acceptance/test_mcp_notifications_council.py",
    "tests/acceptance/test_timeline_council.py",
    "tests/acceptance/test_registration_council.py",
    "tests/acceptance/test_store_identity_council.py",
)


@pytest.fixture
def frozen_copy(tmp_path: Path) -> Path:
    for name in (*MANIFESTS, *ARTIFACTS):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    return tmp_path


@pytest.mark.parametrize("line_ending", [b"\n", b"\r\n"])
def test_preserves_manifests_across_git_line_endings(frozen_copy: Path, line_ending: bytes) -> None:
    for name in MANIFESTS:
        path = frozen_copy / name
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", line_ending))
    assert CHECKER["check_council"](frozen_copy) == []


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_rejects_changed_or_deleted_acceptance(frozen_copy: Path, artifact: str) -> None:
    path = frozen_copy / artifact
    path.write_bytes(path.read_bytes() + b"\n")
    assert CHECKER["check_council"](frozen_copy) == [
        f"frozen council artifact differs from accepted hash: {artifact}"
    ]
    path.unlink()
    assert CHECKER["check_council"](frozen_copy) == [
        f"frozen council artifact differs from accepted hash: {artifact}"
    ]


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_rejects_changed_or_deleted_manifest(frozen_copy: Path, manifest: str) -> None:
    path = frozen_copy / manifest
    path.write_bytes(path.read_bytes() + b" ")
    assert CHECKER["check_council"](frozen_copy) == [
        f"frozen council manifest differs from accepted hash: {manifest}"
    ]
    path.unlink()
    assert CHECKER["check_council"](frozen_copy) == [
        f"frozen council manifest is missing: {manifest}"
    ]


def test_resealing_modified_acceptance_cannot_bypass_manifest_pin(frozen_copy: Path) -> None:
    artifact = frozen_copy / "tests/acceptance/test_mcp_notifications_council.py"
    artifact.write_text("def test_always_passes(): pass\n", encoding="utf-8")
    name = "plans/council-mcp.freeze.json"
    manifest_path = frozen_copy / name
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["tests/acceptance/test_mcp_notifications_council.py"] = hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert CHECKER["check_council"](frozen_copy) == [
        f"frozen council manifest differs from accepted hash: {name}"
    ]
