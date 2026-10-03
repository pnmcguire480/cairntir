"""Execute independently frozen R17 assertions from a byte-preserving archive."""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import socket
import subprocess
import unittest
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cairntir import procedures
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.reason import model

_FREEZE_SHA256 = "11a824fefb828dbd705342495c39057a869826b5d20aac21fe8a38c9877dec2b"
_CONTROLS_SHA256 = "b64fe7108f291ddf0b54f897989b028fb99ea556416c85584b610b23b333823c"
_CASES = (
    "test_01_legacy_wire_content_hash_exact",
    "test_02_legacy_reopen_history_remains_identical",
    "test_03_governance_frozen_verbatim_without_execution",
    "test_04_each_field_changes_hash",
    "test_05_invalid_complete_primitive_strings_atomic",
    "test_06_version_outer_whitespace_atomic",
    "test_07_dates_exact_real_past_allowed",
    "test_08_unicode_encoding_failures_typed_atomic",
    "test_09_exact_type_and_mutated_frozen_revalidated",
    "test_10_revision_durable_immutable_history_list",
    "test_11_governance_strip_atomic",
    "test_12_reused_version_current_and_historical_atomic",
    "test_13_versions_family_local_and_legacy_optin",
    "test_14_stale_and_interleaved_revision_atomic",
    "test_15_evaluate_promote_withdraw_metadata_history",
    "test_16_owner_does_not_authorize_promotion",
    "test_17_revision_invalidates_evaluation",
    "test_18_holdout_independence_remains_required",
    "test_19_malformed_stored_metadata_typed_all_exposing_reads",
    "test_20_hash_tamper_old_and_current_typed",
    "test_21_false_approval_and_reentrancy_remain_atomic",
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _controls_module() -> ModuleType:
    repository = Path(__file__).resolve().parents[2]
    archive_path = repository / "plans/acceptance/practice-governance-r17/controls.zip"
    # An owned packet can qualify this adapter before copying it into the repo.
    if not archive_path.exists():
        archive_path = Path(__file__).resolve().with_name("controls.zip")
    with zipfile.ZipFile(archive_path) as archive:
        frozen_bytes = archive.read("freeze.json")
        assert _sha256(frozen_bytes) == _FREEZE_SHA256, "Frozen manifest drift"
        frozen = json.loads(frozen_bytes)
        for record in frozen["artifacts"]:
            assert _sha256(archive.read(record["path"])) == record["sha256"], (
                f"Frozen artifact drift: {record['path']}"
            )
        controls_bytes = archive.read("controls.py")
        assert _sha256(controls_bytes) == _CONTROLS_SHA256, "Frozen assertion drift"
    module = ModuleType("cairntir_r17_frozen_controls")
    # Execution is restricted to the separately authored, hash-bound test source.
    exec(compile(controls_bytes, "frozen-r17/controls.py", "exec"), module.__dict__)  # noqa: S102
    collected = tuple(unittest.defaultTestLoader.getTestCaseNames(module.FreshR17))
    assert collected == _CASES, "Frozen test collection drift"
    return module


@pytest.mark.parametrize("case_name", _CASES, ids=_CASES)
def test_frozen_r17_control(
    case_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run one unchanged independent control with isolated inert fixtures."""
    for name in (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "CAIRNTIR_HOME",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "TMP",
        "TEMP",
    ):
        isolated = tmp_path / "isolation" / name.lower()
        isolated.mkdir(parents=True)
        monkeypatch.setenv(name, str(isolated))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_AUTOREGISTER", "1")
    monkeypatch.setenv("CAIRNTIR_DISABLE_UPDATE_CHECK", "1")

    def deny(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Frozen R17 fixture attempted network or process execution")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(os, "system", deny)
    importer = builtins.__import__

    def safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", 1)[0] in {
            "fastembed",
            "onnxruntime",
            "sentence_transformers",
            "transformers",
            "torch",
            "huggingface_hub",
        }:
            pytest.fail("Frozen R17 fixture attempted model dependency import")
        return importer(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", safe_import)
    controls = _controls_module()
    controls.API = procedures
    controls.STORE = DrawerStore
    controls.DRAWER = Drawer
    controls.EMBEDDER = HashEmbeddingProvider
    controls.MODEL = model
    controls.ROOT = tmp_path
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.TestSuite((controls.FreshR17(case_name),))
    )
    assert result.testsRun == 1, stream.getvalue()
    assert not result.skipped, stream.getvalue()
    assert result.wasSuccessful(), stream.getvalue()
