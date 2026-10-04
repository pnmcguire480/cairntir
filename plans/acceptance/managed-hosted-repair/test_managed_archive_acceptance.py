"""Independent finite resource reconstruction and active-control preservation proof."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import stat
import sys
import tomllib
import warnings
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if os.environ.get("MANAGED_REPAIR_CANDIDATE"):
    CANDIDATE = Path(os.environ["MANAGED_REPAIR_CANDIDATE"]).resolve()
elif ROOT.parent.name == "acceptance" and ROOT.parent.parent.name == "plans":
    CANDIDATE = ROOT.parents[2]
else:
    raise pytest.UsageError("Set MANAGED_REPAIR_CANDIDATE for external acceptance execution")
MAP = json.loads((ROOT / "RESOURCE-MAP.json").read_bytes())
PACKETS = {
    "plans/acceptance/managed-session-port",
    "plans/acceptance/managed-installed-qualification",
    "plans/acceptance/v2-managed-projection",
    "plans/acceptance/v2-managed-runtime",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def helper():
    path = CANDIDATE / "scripts/restore_managed_evidence.py"
    specification = importlib.util.spec_from_file_location("independent_managed_archive", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def physical_tree(root):
    return {
        file.relative_to(root).as_posix(): file.read_bytes()
        for file in root.rglob("*")
        if file.is_file()
    }


def resources():
    return {relative: (ROOT / value["input"]).read_bytes() for relative, value in MAP.items()}


def make_archive(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data, symbolic in entries:
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 3, 0, 0, 0))
                info.create_system = 3
                info.external_attr = ((stat.S_IFLNK if symbolic else stat.S_IFREG) | 0o600) << 16
                archive.writestr(info, data)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    module = helper()
    source = tmp_path / "source"
    source.mkdir()
    for packet in PACKETS:
        directory = source / packet
        directory.mkdir(parents=True)
        (directory / "independent-capsule-sentinel.json").write_bytes(
            json.dumps({"packet": packet, "original_human_bytes": "caf\u00e9\r\n"}).encode()
        )
    archive = source / module.ARCHIVE_RELATIVE
    contents = resources()
    make_archive(archive, [(name, data, False) for name, data in contents.items()])
    monkeypatch.setattr(module, "ARCHIVE_SHA256", sha(archive.read_bytes()))
    return module, source, archive, tmp_path / "restored", contents


def refused(fixture):
    module, source, _archive, destination, _contents = fixture
    before = physical_tree(source)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        module.restore(source, destination)
    assert not destination.exists(), "Invalid resource input produced a partial destination"
    assert physical_tree(source) == before, "Resource reconstruction wrote into the checkout"


def test_archive_exact_eight_resource_identity_and_sizes():
    module = helper()
    assert module.ARCHIVE_RELATIVE == "plans/acceptance/managed-evidence-archive/resources.zip"
    assert module.FILES == {relative: value["sha256"] for relative, value in MAP.items()}
    assert module.SIZES == {relative: value["size"] for relative, value in MAP.items()}
    assert len(module.FILES) == 8
    for relative, raw in resources().items():
        assert sha(raw) == MAP[relative]["sha256"] and len(raw) == MAP[relative]["size"]


def test_archive_roundtrip_all_original_bytes_source_unchanged(fixture):
    module, source, archive, destination, contents = fixture
    before = physical_tree(source)
    returned = module.restore(source, destination)
    assert returned == destination
    expected = {
        name: raw
        for name, raw in before.items()
        if any(name.startswith(packet + "/") for packet in PACKETS)
    }
    expected.update(contents)
    assert physical_tree(destination) == expected
    assert physical_tree(source) == before
    assert not (destination / module.ARCHIVE_RELATIVE).exists()
    assert sha(archive.read_bytes()) == module.ARCHIVE_SHA256


def test_archive_tampered_transport_cannot_restore(fixture):
    _module, _source, archive, _destination, _contents = fixture
    raw = bytearray(archive.read_bytes())
    raw[len(raw) // 2] ^= 1
    archive.write_bytes(raw)
    refused(fixture)


@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "traversal", "extra", "symlink", "content"]
)
def test_archive_structural_defects_reject_after_independent_transport_binding(
    fixture, monkeypatch, defect
):
    module, _source, archive, _destination, contents = fixture
    entries = [(name, raw, False) for name, raw in contents.items()]
    if defect == "missing":
        entries.pop()
    elif defect == "duplicate":
        entries.append(entries[0])
    elif defect == "traversal":
        entries.append(("../outside-proof.py", b"forbidden", False))
    elif defect == "extra":
        entries.append(("plans/acceptance/extra-proof.py", b"forbidden", False))
    elif defect == "symlink":
        name, raw, _ = entries[0]
        entries[0] = (name, raw, True)
    else:
        name, raw, _ = entries[0]
        entries[0] = (name, raw[:-1] + bytes([raw[-1] ^ 1]), False)
    make_archive(archive, entries)
    # Exercise member validation without weakening any of the eight source bindings.
    monkeypatch.setattr(module, "ARCHIVE_SHA256", sha(archive.read_bytes()))
    refused(fixture)


def test_archive_missing_transport_refuses_new_destination(fixture):
    _module, _source, archive, _destination, _contents = fixture
    archive.unlink()
    refused(fixture)


def test_archive_existing_destination_is_not_overwritten(fixture):
    module, source, _archive, destination, _contents = fixture
    destination.mkdir()
    protected = destination / "independent-human-proof.txt"
    protected.write_bytes(b"original human proof\r\n")
    before = physical_tree(destination)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        module.restore(source, destination)
    assert physical_tree(destination) == before


def test_archive_conflicting_source_resource_cannot_be_silently_replaced(fixture):
    _module, source, _archive, _destination, contents = fixture
    path = source / next(iter(contents))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unreviewed source resource change")
    refused(fixture)


def assert_nodes(raw):
    return [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(ast.parse(raw))
        if isinstance(node, ast.Assert)
    ]


def test_active_control_amendments_keep_every_frozen_behavior_oracle():
    baseline = resources()
    durable_old = baseline[
        "plans/acceptance/managed-session-port/raw-projection-amendment-v3/test_managed_durable_boundaries_v3.py"
    ].decode()
    durable = (ROOT / "active/test_managed_durable_boundaries_v4.py").read_text(encoding="utf-8")
    assert assert_nodes(durable) == assert_nodes(durable_old)
    visibility_old = baseline[
        "plans/acceptance/managed-session-port/visibility-v2/test_hidden_event_v2.py"
    ].decode()
    visibility = (ROOT / "active/test_hidden_event_v3.py").read_text(encoding="utf-8")
    normalized = visibility.replace("    owner_closed = full.close(last_sequence=2)\n", "").replace(
        'assert owner_closed["capture_complete"] is True',
        'assert full.close(last_sequence=2)["capture_complete"] is True',
    )
    assert assert_nodes(normalized) == assert_nodes(visibility_old)
    assert visibility.count("owner_closed = full.close(last_sequence=2)") == 1
    assert "test_managed_durable_boundaries_v4.py" in visibility
    for file in (ROOT / "active").glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assert):
                assert not any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr
                    in {
                        "close",
                        "start",
                        "capture",
                        "brief",
                        "acknowledge",
                        "dispatch",
                        "checkpoint",
                    }
                    for call in ast.walk(node)
                ), (file.name, node.lineno)
    projection_old = baseline[
        "plans/acceptance/v2-managed-projection/test_managed_projection.py"
    ].decode()
    projection = (ROOT / "active/test_managed_projection_v2.py").read_text(encoding="utf-8")
    normalized_projection = projection.replace(
        "self.assertLessEqual(expected_ids, sources.keys())",
        "self.assertTrue(expected_ids <= sources.keys())",
    )
    assert ast.dump(ast.parse(normalized_projection)) == ast.dump(ast.parse(projection_old))


def test_original_consumer_integrity_and_loader_bodies_are_retained():
    consumers = json.loads((ROOT / "CONSUMER-BASELINE.json").read_bytes())
    for relative in [
        "tests/unit/test_managed_runtime.py",
        "tests/unit/test_last_session_projection.py",
        "tests/unit/test_managed_port_acceptance.py",
        "tests/unit/test_managed_installed_qualification.py",
    ]:
        prior = (ROOT / "originals" / (relative + ".raw")).read_text(encoding="utf-8")
        current = (CANDIDATE / relative).read_text(encoding="utf-8")
        assert assert_nodes(current) == assert_nodes(prior), relative
        old_definitions = {
            node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(prior).body
            if isinstance(node, ast.FunctionDef)
        }
        new_definitions = {
            node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(current).body
            if isinstance(node, ast.FunctionDef)
        }
        for name, previous in old_definitions.items():
            assert new_definitions[name] == previous, (relative, name)
    unchanged = "scripts/check_verification_preservation.py"
    assert sha((CANDIDATE / unchanged).read_bytes()) == consumers[unchanged]
    assert (
        tomllib.loads((CANDIDATE / "pyproject.toml").read_text())["tool"]["coverage"]
        == tomllib.loads((ROOT / "originals/pyproject.toml.raw").read_text())["tool"]["coverage"]
    )
    old_verifier = (ROOT / "originals/scripts/verify_package.py.raw").read_text(encoding="utf-8")
    current_verifier = (CANDIDATE / "scripts/verify_package.py").read_text(encoding="utf-8")
    expected = assert_nodes(old_verifier)
    actual = iter(assert_nodes(current_verifier))
    assert all(any(item == old for item in actual) for old in expected)


def test_actual_snapshot_retains_every_original_manifest_and_seal_entry(tmp_path):
    module = helper()
    before = {packet: physical_tree(CANDIDATE / packet) for packet in PACKETS}
    destination = tmp_path / "actual-restored"
    returned = module.restore(CANDIDATE, destination)
    assert returned == destination
    for packet in PACKETS:
        assert physical_tree(CANDIDATE / packet) == before[packet]
    for relative, raw in resources().items():
        assert (destination / relative).read_bytes() == raw
    manifests = json.loads((ROOT / "MANIFEST-BASELINE.json").read_bytes())
    checked = 0
    for relative, baseline in manifests.items():
        source = CANDIDATE / "plans/acceptance" / relative
        restored = destination / "plans/acceptance" / relative
        assert restored.read_bytes() == source.read_bytes()
        assert sha(restored.read_bytes()) == baseline["sha256"]
        manifest = json.loads(restored.read_bytes())
        for filename, digest in manifest.get("files_sha256", manifest.get("files", {})).items():
            assert sha((restored.parent / filename).read_bytes()) == digest, (relative, filename)
            checked += 1
    assert checked == sum(value["entries"] for value in manifests.values())
