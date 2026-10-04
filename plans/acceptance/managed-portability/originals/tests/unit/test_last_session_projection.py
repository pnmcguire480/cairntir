"""Run independently frozen public Last Session projection acceptance."""

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[2]
_RESTORE_SPEC = importlib.util.spec_from_file_location(
    "managed_evidence_restore", _SOURCE / "scripts/restore_managed_evidence.py"
)
if _RESTORE_SPEC is None or _RESTORE_SPEC.loader is None:
    raise RuntimeError("managed evidence reconstruction helper is unavailable")
_RESTORE = importlib.util.module_from_spec(_RESTORE_SPEC)
_RESTORE_SPEC.loader.exec_module(_RESTORE)
_EVIDENCE_TEMP = tempfile.TemporaryDirectory(prefix="cairntir-managed-evidence-")
_EVIDENCE_ROOT = _RESTORE.restore(_SOURCE, Path(_EVIDENCE_TEMP.name) / "snapshot")
ACCEPTANCE = _EVIDENCE_ROOT / "plans/acceptance/v2-managed-projection"


def _verify():
    raw = (ACCEPTANCE / "PACKAGE-FROZEN.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "1ecdeb684e803f450304a641a14150328efdf5798433a13e290f048bfc03e67a"
    )
    for name, digest in json.loads(raw)["files"].items():
        assert hashlib.sha256((ACCEPTANCE / name).read_bytes()).hexdigest() == digest, name
    for name in ("FROZEN.json", "CORRUPTION-FROZEN.json", "OUTCOME-FROZEN.json"):
        for child, digest in json.loads((ACCEPTANCE / name).read_bytes())["files"].items():
            assert hashlib.sha256((ACCEPTANCE / child).read_bytes()).hexdigest() == digest, child


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ACCEPTANCE / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_verify()
_original = _load("test_managed_projection")
_corruption = _load("test_projection_corruption")
_outcome = _load("test_projection_outcome_binding")


class TestManagedProjection(_original.ManagedProjectionAcceptance):
    pass


class TestProjectionCorruption(_corruption.ProjectionCorruptionAcceptance):
    pass


class TestProjectionOutcome(_outcome.ProjectionOutcomeAcceptance):
    pass
