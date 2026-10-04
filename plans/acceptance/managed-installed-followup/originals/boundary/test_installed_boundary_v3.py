"""Owned installed-proof temp routing without tools, installations or models."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent
if os.environ.get("MANAGED_PORTABILITY_CANDIDATE"):
    CANDIDATE = Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve()
else:
    CANDIDATE = ROOT.parents[2]


def load(path, name):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


_PORTABILITY = load(ROOT / "test_portability_v3.py", "installed_portability_v3")
for _name, _value in vars(_PORTABILITY).items():
    if _name.startswith("test_"):
        globals()[_name] = _value


class FirstToolBoundary(Exception):
    """The inert sentinel prevents every real tool invocation."""


@pytest.fixture
def synthetic_checkout(tmp_path):
    helper = load(CANDIDATE / "scripts/restore_managed_evidence.py", "boundary_restore")
    source = helper.restore(CANDIDATE, tmp_path / "checkout")
    (source / "scripts").mkdir()
    shutil.copyfile(
        CANDIDATE / "scripts/restore_managed_evidence.py",
        source / "scripts/restore_managed_evidence.py",
    )
    archive = source / helper.ARCHIVE_RELATIVE
    archive.parent.mkdir(parents=True)
    shutil.copyfile(CANDIDATE / helper.ARCHIVE_RELATIVE, archive)
    shim = tmp_path / "inert_uv.py"
    shim.write_text('raise AssertionError("this inert tool must never execute")\n')
    return source, helper, shim


def wire(module, source, helper, shim, monkeypatch):
    observations = []
    module.ROOT = source
    monkeypatch.setattr(module.shutil, "which", lambda name: str(shim) if name == "uv" else None)

    def first_tool(arguments, cwd, environment, timeout=180):
        assert arguments[0] == str(shim) and arguments[1] == "export"
        assert cwd == source
        requirements = Path(arguments[arguments.index("--output-file") + 1])
        owned = requirements.parent
        assert not owned.is_relative_to(source)
        assert owned == owned.resolve()
        restored = owned / "managed-source"
        for relative, expected in helper.FILES.items():
            assert hashlib.sha256((restored / relative).read_bytes()).hexdigest() == expected
        assert environment["CAIRNTIR_HOME"] == str(owned / "home")
        observations.append(owned)
        raise FirstToolBoundary("No real uv/tool/install call permitted")

    monkeypatch.setattr(module, "execute", first_tool)
    return observations


def historical_verifier():
    return ROOT / "originals/portability/originals/scripts/verify_package.py"


def test_output_inside_checkout_keeps_owned_execution_temp_outside_before_tool(
    synthetic_checkout, tmp_path, monkeypatch
):
    source, helper, shim = synthetic_checkout
    output = source / "build-verification"
    old = load(historical_verifier(), "historical_output_routing")
    old_calls = wire(old, source, helper, shim, monkeypatch)
    with pytest.raises(ValueError, match="outside the source"):
        old.install_and_verify(tmp_path / "never-installed.whl", output)
    assert old_calls == []
    assert list(output.iterdir()) == [], "Old refusal left tool/install artifacts"
    current = load(CANDIDATE / "scripts/verify_package.py", "candidate_output_routing")
    current_calls = wire(current, source, helper, shim, monkeypatch)
    with pytest.raises(FirstToolBoundary):
        current.install_and_verify(tmp_path / "never-installed.whl", output)
    assert len(current_calls) == 1
    assert not current_calls[0].exists(), "Owned temp context did not clean up after tool sentinel"
    assert list(output.iterdir()) == []


def test_installed_caller_canonicalizes_modeled_platform_temp_alias(
    synthetic_checkout, tmp_path, monkeypatch
):
    source, helper, shim = synthetic_checkout
    output = tmp_path / "requested-reports"
    alias, physical = tmp_path / "platform-temp-alias", tmp_path / "physical-owned-temp"
    alias.mkdir()
    physical.mkdir()
    original_lstat, original_resolve = Path.lstat, Path.resolve
    exits = []

    def modeled_lstat(path, *args, **kwargs):
        if path == alias:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        return original_lstat(path, *args, **kwargs)

    def modeled_resolve(path, *args, **kwargs):
        if path == alias:
            return physical
        return original_resolve(path, *args, **kwargs)

    @contextmanager
    def owned_temporary(*, prefix, dir=None):
        assert prefix == "installed-"
        assert dir is None or dir == output
        try:
            yield str(alias)
        finally:
            exits.append("closed")

    monkeypatch.setattr(Path, "lstat", modeled_lstat)
    monkeypatch.setattr(Path, "resolve", modeled_resolve)
    old = load(historical_verifier(), "historical_alias_routing")
    monkeypatch.setattr(old.tempfile, "TemporaryDirectory", owned_temporary)
    old_calls = wire(old, source, helper, shim, monkeypatch)
    with pytest.raises(ValueError, match="link or reparse point"):
        old.install_and_verify(tmp_path / "never-installed.whl", output)
    assert old_calls == []
    assert not (physical / "managed-source").exists()
    current = load(CANDIDATE / "scripts/verify_package.py", "candidate_alias_routing")
    current_calls = wire(current, source, helper, shim, monkeypatch)
    with pytest.raises(FirstToolBoundary):
        current.install_and_verify(tmp_path / "never-installed.whl", output)
    assert current_calls == [physical]
    assert exits == ["closed", "closed"]
    assert list(output.iterdir()) == []


def test_only_owned_temp_location_and_canonicalization_change_all_44_assertions_remain():
    original = historical_verifier().read_bytes()
    expected = original.replace(
        b'TemporaryDirectory(prefix="installed-", dir=output)',
        b'TemporaryDirectory(prefix="installed-")',
    )
    expected = expected.replace(
        b"directory = Path(temporary)\n", b"directory = Path(temporary).resolve()\n"
    )
    current = (CANDIDATE / "scripts/verify_package.py").read_bytes()
    assert current == expected
    assertions = lambda raw: [
        ast.dump(node) for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Assert)
    ]
    assert assertions(current) == assertions(original)
    assert len(assertions(current)) == 44
    assert (CANDIDATE / "scripts/restore_managed_evidence.py").read_bytes() == (
        ROOT / "originals/portability/originals/scripts/restore_managed_evidence.py"
    ).read_bytes()
