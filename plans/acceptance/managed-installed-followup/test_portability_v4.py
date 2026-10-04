"""Finite caller canonicalization proof; restoration security remains unchanged."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKET = Path(__file__).resolve().parent
ROOT = PACKET / "originals/boundary/originals/portability"
CANDIDATE = (
    Path(os.environ["MANAGED_PORTABILITY_CANDIDATE"]).resolve()
    if os.environ.get("MANAGED_PORTABILITY_CANDIDATE")
    else PACKET.parents[2]
)

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "followup_amendment_support", PACKET / "amendment_support.py"
)
assert _SUPPORT_SPEC is not None and _SUPPORT_SPEC.loader is not None
_SUPPORT = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(_SUPPORT)

BASELINE = json.loads((ROOT / "BASELINE.json").read_bytes())
ROUTERS = BASELINE["routers"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def helper():
    name = "bounded_portability_restore"
    specification = importlib.util.spec_from_file_location(
        name, CANDIDATE / "scripts/restore_managed_evidence.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def expression(raw):
    tree = ast.parse(raw)
    assignments = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_EVIDENCE_ROOT"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    return compile(ast.Expression(assignments[0]), "<inert caller expression>", "eval")


@pytest.mark.parametrize("relative", ROUTERS)
def test_aliased_temp_parent_old_refuses_canonical_caller_passes(tmp_path, monkeypatch, relative):
    module = helper()
    alias = tmp_path / "platform-alias"
    canonical = tmp_path / "physical-temp"
    alias.mkdir()
    canonical.mkdir()
    original_lstat, original_resolve = Path.lstat, Path.resolve

    def modeled_lstat(path, *args, **kwargs):
        if path == alias:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        return original_lstat(path, *args, **kwargs)

    def modeled_resolve(path, *args, **kwargs):
        if path == alias:
            return canonical
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", modeled_lstat)
    monkeypatch.setattr(Path, "resolve", modeled_resolve)
    raw = (ROOT / "originals" / relative).read_bytes()
    scope = {
        "Path": Path,
        "_SOURCE": CANDIDATE,
        "_RESTORE": module,
        "_EVIDENCE_TEMP": SimpleNamespace(name=str(alias)),
    }
    with pytest.raises(ValueError, match="link or reparse point"):
        eval(expression(raw), scope)
    assert not (alias / "snapshot").exists()
    assert not (canonical / "snapshot").exists()
    revised = raw.replace(b"Path(_EVIDENCE_TEMP.name)", b"Path(_EVIDENCE_TEMP.name).resolve()")
    restored = eval(expression(revised), scope)
    assert restored == canonical / "snapshot"
    for relative_path, expected in module.FILES.items():
        assert digest(restored / relative_path) == expected
    assert not (alias / "snapshot").exists()


@pytest.mark.parametrize("unsafe", ["source", "archive"])
def test_security_guard_still_rejects_unsafe_source_or_archive(tmp_path, monkeypatch, unsafe):
    module = helper()
    target = CANDIDATE if unsafe == "source" else CANDIDATE / module.ARCHIVE_RELATIVE
    original_lstat = Path.lstat

    def modeled_lstat(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", modeled_lstat)
    destination = tmp_path / "must-remain-absent"
    with pytest.raises(ValueError, match="link or reparse point"):
        module.restore(CANDIDATE, destination)
    assert not destination.exists()


def test_only_four_caller_expressions_change_all_integrity_bodies_retained():
    for relative in ROUTERS:
        original = (ROOT / "originals" / relative).read_bytes()
        assert original.count(b"Path(_EVIDENCE_TEMP.name)") == 1
        expected = original.replace(
            b"Path(_EVIDENCE_TEMP.name)", b"Path(_EVIDENCE_TEMP.name).resolve()"
        )
        assert (CANDIDATE / relative).read_bytes() == expected, relative
    for relative, expected in BASELINE["unchanged"].items():
        if relative == "scripts/verify_package.py":
            original = (ROOT / "originals" / relative).read_bytes()
            original = _SUPPORT.expected_verifier(original)
            expected = hashlib.sha256(original).hexdigest()
        assert digest(CANDIDATE / relative) == expected, relative
    verifier = ast.parse((CANDIDATE / "scripts/verify_package.py").read_bytes())
    assignments = [ast.unparse(node) for node in ast.walk(verifier) if isinstance(node, ast.Assign)]
    assert (
        "wheel_path, output_path = (arguments.wheel.resolve(), arguments.output.resolve())"
        in assignments
    )
    assert any("directory = Path(temporary).resolve()" == node for node in assignments)
    source = (CANDIDATE / "scripts/verify_package.py").read_text()
    assert 'tempfile.TemporaryDirectory(prefix="installed-")' in source
