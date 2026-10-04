"""Run four unchanged frozen cases exclusively in the installed wheel interpreter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def _run_suite(suite: unittest.TestSuite) -> dict:
    """Require every selected case to execute and preserve failure/skip diagnostics."""
    expected = suite.countTestCases()
    result = unittest.TestResult()
    suite.run(result)
    assert not result.errors, "\n".join(detail for _, detail in result.errors)
    assert not result.failures, "\n".join(detail for _, detail in result.failures)
    assert not result.skipped, result.skipped
    assert result.testsRun == expected and expected > 0
    return {"passed": result.testsRun, "failed": 0, "errors": 0, "skipped": 0}


def _load(name: str, filename: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / "originals" / filename)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def verify_installed_managed(*, model_cache: Path, version: str) -> dict:
    """Use the existing provisioned cache, original CLI cases, and original projection API cases."""
    import cairntir
    import cairntir.managed
    import cairntir.managed_projection

    package = Path(cairntir.__file__).resolve().parent
    assert package.is_relative_to(Path(sys.prefix).resolve()), package
    assert not package.is_relative_to(ROOT), package
    assert not os.environ.get("PYTHONPATH"), "installed proof cannot inherit source PYTHONPATH"
    assert cairntir.__version__ == version
    frozen = json.loads((ROOT / "FROZEN.json").read_bytes())
    for relative, digest in frozen["files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    for relative, digest in frozen["installed_source_sha256"].items():
        assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == digest, relative
    assert Path(cairntir.managed.__file__).resolve().is_relative_to(package)
    assert Path(cairntir.managed_projection.__file__).resolve().is_relative_to(package)
    cache = model_cache.resolve()
    assert cache.is_dir(), "qualified offline production cache is required; no skip or download"
    process = _load("test_managed_process", "test_managed_process.py")
    config = _load("frozen_installed_managed_config", "test_managed_config.py")
    projection = _load("frozen_installed_managed_projection", "test_managed_projection.py")
    selected = [
        process.ManagedProcessAcceptance(
            "test_real_cli_jsonl_start_capture_brief_ack_dispatch_close"
        ),
        config.ManagedConfigurationAcceptance(
            "test_cli_changed_config_cannot_launch_using_previous_ack"
        ),
        projection.ManagedProjectionAcceptance(
            "test_exact_checkpoint_descriptions_and_source_links"
        ),
        projection.ManagedProjectionAcceptance("test_read_only_restart_and_exact_human_bytes"),
    ]
    identities = [case.id() for case in selected]
    with patch.dict(
        os.environ,
        {
            "MANAGED_ACCEPTANCE_MODEL_CACHE": str(cache),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
            "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    ):
        result = _run_suite(unittest.TestSuite(selected))
    assert result["passed"] == 4
    return {
        **result,
        "cases": identities,
        "production_cli_cases": 2,
        "projection_api_cases": 2,
        "installed_interpreter": str(Path(sys.executable).resolve()),
        "installed_package": str(package),
        "version": version,
        "source_pythonpath": False,
        "offline_production_cache": True,
        "original_assertions_changed": False,
        "native_automatic_activation": "unverified",
    }
