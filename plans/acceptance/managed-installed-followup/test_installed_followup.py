"""Finite fixed-source amendment and inert installed-origin qualification."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent
CANDIDATE = (
    Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve()
    if os.environ.get("MANAGED_PORTABILITY_CANDIDATE")
    else ROOT.parents[2]
)
NEW_FREEZE = "4553f721df2f9beebbe68ae72df75c47f587655e77bd4923fb94b700c4ccd71b"
OLD_MANAGED = "31452b541883edae15687dc8587234ff38ef97d5b9500ab5f985dbcc94c2866b"
NEW_MANAGED = "7d1c1bfb8ebee9ee3eff89b5bdd5b87c9108830a98091c02d54cdd4dff652a93"


def load(path, name):
    import importlib.util

    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


_BOUNDARY = load(ROOT / "test_installed_boundary_v4.py", "followup_boundary_v4")
for _name, _value in vars(_BOUNDARY).items():
    if _name.startswith("test_"):
        globals()[_name] = _value
synthetic_checkout = _BOUNDARY.synthetic_checkout


class CaseLoadBoundary(Exception):
    """Stop before importing or executing any production/model cases."""


class ProbeBoundary(Exception):
    """Stop before starting any installed interpreter."""


@pytest.fixture
def installed_identity(tmp_path, monkeypatch):
    capsule = tmp_path / "proof"
    capsule.mkdir()
    frozen = json.loads((ROOT / "FROZEN.json").read_bytes())
    for relative in ["FROZEN.json", *frozen["files_sha256"]]:
        target = capsule / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    helper = load(capsule / "verify_installed_managed.py", "inert_installed_identity")
    prefix = tmp_path / "owned-prefix"
    package = prefix / "site-packages/cairntir"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Inert identity fixture."""\n')
    for relative in frozen["installed_source_sha256"]:
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANDIDATE / "src/cairntir" / relative, target)
    top = ModuleType("cairntir")
    top.__file__ = str(package / "__init__.py")
    top.__path__ = [str(package)]
    top.__version__ = "1.17.0"
    for short in ["managed", "managed_projection"]:
        child = ModuleType(f"cairntir.{short}")
        child.__file__ = str(package / f"{short}.py")
        setattr(top, short, child)
        monkeypatch.setitem(sys.modules, child.__name__, child)
    monkeypatch.setitem(sys.modules, "cairntir", top)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.delenv("PYTHONPATH", raising=False)
    cache = tmp_path / "empty-owned-cache"
    cache.mkdir()
    calls = []

    def no_case_load(name, filename):
        calls.append((name, filename))
        raise CaseLoadBoundary("Identity validated; no production case or model imported")

    monkeypatch.setattr(helper, "_load", no_case_load)
    return SimpleNamespace(
        helper=helper, capsule=capsule, package=package, top=top, cache=cache, calls=calls
    )


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "stale_pin",
        "wrong_source",
        "outside_prefix",
        "managed_origin",
        "projection_origin",
        "source_pythonpath",
        "version",
    ],
)
def test_installed_identity_rejects_wrong_binding_before_case_import(
    installed_identity, tmp_path, monkeypatch, fault
):
    fixture = installed_identity
    if fault == "stale_pin":
        path = fixture.capsule / "FROZEN.json"
        frozen = json.loads(path.read_bytes())
        frozen["installed_source_sha256"]["managed.py"] = OLD_MANAGED
        path.write_text(json.dumps(frozen), encoding="utf-8")
    elif fault == "wrong_source":
        (fixture.package / "managed.py").write_bytes(b"# wrong installed artifact\n")
    elif fault == "outside_prefix":
        monkeypatch.setattr(sys, "prefix", str(tmp_path / "unrelated-prefix"))
    elif fault == "managed_origin":
        fixture.top.managed.__file__ = str(tmp_path / "external/managed.py")
    elif fault == "projection_origin":
        fixture.top.managed_projection.__file__ = str(tmp_path / "external/managed_projection.py")
    elif fault == "source_pythonpath":
        monkeypatch.setenv("PYTHONPATH", str(CANDIDATE / "src"))
    elif fault == "version":
        fixture.top.__version__ = "0.0.0"
    if fault == "none":
        with pytest.raises(CaseLoadBoundary):
            fixture.helper.verify_installed_managed(model_cache=fixture.cache, version="1.17.0")
        assert fixture.calls == [("test_managed_process", "test_managed_process.py")]
    else:
        with pytest.raises(AssertionError):
            fixture.helper.verify_installed_managed(model_cache=fixture.cache, version="1.17.0")
        assert fixture.calls == [], "Invalid source or installed identity reached production cases"


@pytest.mark.parametrize("outcome", ["success", "failure", "error", "skip", "empty"])
def test_original_suite_requires_execution_without_failure_error_or_skip(outcome):
    helper = load(ROOT / "verify_installed_managed.py", "original_suite_boundary")

    def exercise():
        if outcome == "failure":
            raise AssertionError("deliberate failed case")
        if outcome == "error":
            raise RuntimeError("deliberate case error")
        if outcome == "skip":
            raise unittest.SkipTest("deliberate skipped case")

    cases = [] if outcome == "empty" else [unittest.FunctionTestCase(exercise)]
    suite = unittest.TestSuite(cases)
    if outcome == "success":
        result = helper._run_suite(suite)
        assert result == {"passed": 1, "failed": 0, "errors": 0, "skipped": 0}
        validate_single_pin_and_preserved_originals()
    else:
        with pytest.raises(AssertionError):
            helper._run_suite(suite)


def validate_single_pin_and_preserved_originals():
    old = json.loads((ROOT / "HISTORICAL-INSTALLED-FROZEN.json").read_bytes())
    current = json.loads((ROOT / "FROZEN.json").read_bytes())
    assert hashlib.sha256((ROOT / "FROZEN.json").read_bytes()).hexdigest() == NEW_FREEZE
    assert old["installed_source_sha256"]["managed.py"] == OLD_MANAGED
    expected = json.loads(json.dumps(old))
    expected["installed_source_sha256"]["managed.py"] = NEW_MANAGED
    assert current == expected, "Only the fixed, reviewed managed.py digest may change"
    for relative, expected_sha in old["files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected_sha, relative
    boundary = ROOT / "originals/boundary"
    seal = json.loads((boundary / "SEAL.json").read_bytes())
    for relative, expected_sha in seal["files_sha256"].items():
        assert hashlib.sha256((boundary / relative).read_bytes()).hexdigest() == expected_sha, (
            relative
        )
    selection = current["case_selection"]
    assert selection == [
        "test_real_cli_jsonl_start_capture_brief_ack_dispatch_close",
        "test_cli_changed_config_cannot_launch_using_previous_ack",
        "test_exact_checkpoint_descriptions_and_source_links",
        "test_read_only_restart_and_exact_human_bytes",
    ]
    calls = [
        node
        for node in ast.walk(ast.parse((ROOT / "verify_installed_managed.py").read_bytes()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr
        in {
            "ManagedProcessAcceptance",
            "ManagedConfigurationAcceptance",
            "ManagedProjectionAcceptance",
        }
    ]
    assert [node.args[0].value for node in calls] == selection


def test_actual_verifier_copies_fixed_capsule_before_inert_installed_probe(
    synthetic_checkout, tmp_path, monkeypatch
):
    source, helper, shim = synthetic_checkout
    question = source / "plans/acceptance/questions-installed-ci-1.16-v2"
    question.mkdir(parents=True)
    for relative in ["FROZEN.json", "verify_installed_questions_v2.py"]:
        shutil.copyfile(CANDIDATE / question.relative_to(source) / relative, question / relative)
    followup = source / "plans/acceptance/managed-installed-followup"
    followup.mkdir(parents=True)
    frozen = json.loads((ROOT / "FROZEN.json").read_bytes())
    for relative in ["FROZEN.json", *frozen["files_sha256"]]:
        target = followup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    module = load(CANDIDATE / "scripts/verify_package.py", "full_inert_followup_routing")
    module.ROOT = source
    monkeypatch.setattr(module.shutil, "which", lambda name: str(shim) if name == "uv" else None)
    stages = []
    owned = []

    def inert_execute(arguments, cwd, environment, timeout=180):
        if len(stages) == 0:
            assert arguments[:2] == [str(shim), "export"]
            assert cwd == source
            requirements = Path(arguments[arguments.index("--output-file") + 1])
            owned.append(requirements.parent)
            assert not owned[0].is_relative_to(source)
            requirements.write_text("# inert requirements; no package installation\n")
            stages.append("export")
        elif len(stages) == 1:
            assert arguments[:2] == [str(shim), "venv"]
            assert cwd == owned[0]
            stages.append("venv")
        elif len(stages) == 2:
            assert arguments[:3] == [str(shim), "pip", "install"]
            assert cwd == owned[0]
            stages.append("install")
        else:
            assert "--probe" in arguments and timeout == 300
            assert cwd == owned[0] and environment["CAIRNTIR_HOME"] == str(owned[0] / "home")
            proof = Path(arguments[arguments.index("--managed-proof") + 1])
            assert proof == owned[0] / "managed_proof"
            assert proof == (owned[0] / "managed-source").parent / "managed_proof"
            assert arguments[arguments.index("--managed-proof-sha256") + 1] == NEW_FREEZE
            assert (proof / "FROZEN.json").read_bytes() == (ROOT / "FROZEN.json").read_bytes()
            for relative, expected_sha in frozen["files_sha256"].items():
                assert hashlib.sha256((proof / relative).read_bytes()).hexdigest() == expected_sha
            assert hashlib.sha256((proof / "FROZEN.json").read_bytes()).hexdigest() == NEW_FREEZE
            stages.append("probe")
            raise ProbeBoundary("No interpreter, installation or model executes")
        return ""

    monkeypatch.setattr(module, "execute", inert_execute)
    output = source / "build-verification"
    with pytest.raises(ProbeBoundary):
        module.install_and_verify(tmp_path / "not-installed.whl", output)
    assert stages == ["export", "venv", "install", "probe"]
    assert len(owned) == 1 and not owned[0].exists(), "Owned temp was not cleaned after sentinel"
    assert sorted(path.name for path in output.iterdir()) == ["requirements.txt"]
