import copy
import os
import sqlite3
from pathlib import Path

import pytest

from cairntir.errors import ProjectionError
from cairntir.ideation_audience import (
    get_audience_revision,
    publish_audience_revision,
    scan_legacy_audience,
)


@pytest.fixture
def audience(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    fields = ("audience", "channels", "pain", "sophistication", "desired_outcome")
    return {
        "store_path": tmp_path / "memory.db",
        "vault_path": vault,
        "wing": "project-alpha",
        "profile": {
            field: {"value": f"chosen {field}", "source_ids": ["statement-1"]} for field in fields
        },
        "evidence": {
            "statement-1": {
                "kind": "user_statement",
                "content": "I chose these audience details.",
                "supports": list(fields),
                "values": {field: f"chosen {field}" for field in fields},
            }
        },
        "idempotency_key": "first",
    }


def _snapshots(vault):
    return {path: path.read_bytes() for path in vault.rglob("*.md")}


@pytest.mark.parametrize(
    "damage",
    [
        "evidence_not_mapping",
        "evidence_item_not_mapping",
        "unsafe_evidence_id",
        "unknown_evidence_kind",
        "blank_evidence_content",
        "unsupported_evidence_dimension",
        "missing_evidence_dimensions",
        "repeated_evidence_dimension",
        "missing_human_value_binding",
        "extra_human_value_binding",
        "profile_not_mapping",
        "profile_missing_dimension",
        "profile_extra_dimension",
        "profile_item_not_mapping",
        "profile_blank_value",
        "profile_source_ids_not_list",
        "profile_source_wrong_dimension",
        "invalid_status",
        "confirmation_on_provisional",
        "invalid_confirmation_id",
    ],
)
def test_malformed_audience_request_cannot_create_store_or_vault_output(audience, damage):
    request = copy.deepcopy(audience)
    evidence = request["evidence"]
    profile = request["profile"]
    item = evidence["statement-1"]
    if damage == "evidence_not_mapping":
        request["evidence"] = []
    elif damage == "evidence_item_not_mapping":
        evidence["statement-1"] = "I chose these audience details."
    elif damage == "unsafe_evidence_id":
        evidence["../escape"] = evidence.pop("statement-1")
    elif damage == "unknown_evidence_kind":
        item["kind"] = "model_confirmation"
    elif damage == "blank_evidence_content":
        item["content"] = "   "
    elif damage == "unsupported_evidence_dimension":
        item["supports"].append("budget")
    elif damage == "missing_evidence_dimensions":
        item["supports"] = []
    elif damage == "repeated_evidence_dimension":
        item["supports"].append("audience")
    elif damage == "missing_human_value_binding":
        del item["values"]["pain"]
    elif damage == "extra_human_value_binding":
        item["values"]["budget"] = "cheap"
    elif damage == "profile_not_mapping":
        request["profile"] = []
    elif damage == "profile_missing_dimension":
        del profile["pain"]
    elif damage == "profile_extra_dimension":
        profile["budget"] = {"value": "cheap", "source_ids": ["statement-1"]}
    elif damage == "profile_item_not_mapping":
        profile["pain"] = "lost context"
    elif damage == "profile_blank_value":
        profile["pain"]["value"] = "\t"
    elif damage == "profile_source_ids_not_list":
        profile["pain"]["source_ids"] = "statement-1"
    elif damage == "profile_source_wrong_dimension":
        item["supports"].remove("pain")
        del item["values"]["pain"]
    elif damage == "invalid_status":
        request["status"] = "approved"
    elif damage == "confirmation_on_provisional":
        request["confirmation_source_id"] = "statement-1"
    else:
        request["confirmation_source_id"] = "../escape"
    with pytest.raises(ProjectionError):
        publish_audience_revision(**request)
    assert not request["store_path"].exists()
    assert list(request["vault_path"].iterdir()) == []


@pytest.mark.parametrize("part", ["cairntir-sync", "project-alpha", "audience", "versions"])
def test_non_directory_generated_path_is_rejected_before_store_write(audience, part):
    cursor = audience["vault_path"]
    for name in ("cairntir-sync", "project-alpha", "audience", "versions"):
        cursor /= name
        if name == part:
            cursor.write_bytes(b"human-owned path; do not replace")
            break
        cursor.mkdir()
    with pytest.raises(ProjectionError, match="not a directory"):
        publish_audience_revision(**audience)
    assert cursor.read_bytes() == b"human-owned path; do not replace"
    assert not audience["store_path"].exists()


def test_symlinked_store_parent_inside_vault_is_rejected_before_write(audience, tmp_path):
    linked_parent = tmp_path / "store-alias"
    try:
        linked_parent.symlink_to(audience["vault_path"], target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("host cannot create directory symlinks")
    store = linked_parent / "memory.db"
    with pytest.raises(ProjectionError, match="outside the vault"):
        publish_audience_revision(**{**audience, "store_path": store})
    assert not store.exists()
    assert list(audience["vault_path"].iterdir()) == []


def test_vault_file_is_rejected_without_touching_it_or_the_store(audience, tmp_path):
    vault_file = tmp_path / "human-vault-file"
    vault_file.write_bytes(b"Human material; not a directory.\n")
    with pytest.raises(ProjectionError, match="vault path must be a directory"):
        publish_audience_revision(**{**audience, "vault_path": vault_file})
    assert vault_file.read_bytes() == b"Human material; not a directory.\n"
    assert not audience["store_path"].exists()


def test_missing_store_parent_does_not_create_vault_or_database(audience, tmp_path):
    store = tmp_path / "uncreated-parent" / "memory.db"
    with pytest.raises(ProjectionError, match="store parent is missing"):
        publish_audience_revision(**{**audience, "store_path": store})
    assert not store.parent.exists()
    assert list(audience["vault_path"].iterdir()) == []


@pytest.mark.parametrize("target", ["vault", "store"])
def test_symlinked_root_input_is_rejected_before_publishing(audience, tmp_path, target):
    if target == "vault":
        link = tmp_path / "vault-alias"
        original = audience["vault_path"]
    else:
        original = tmp_path / "existing-store"
        original.write_bytes(b"human-owned store-shaped file")
        link = tmp_path / "store-alias"
    try:
        link.symlink_to(original, target_is_directory=target == "vault")
    except (OSError, NotImplementedError):
        pytest.skip("host cannot create symlinks")
    key = "vault_path" if target == "vault" else "store_path"
    with pytest.raises(ProjectionError, match="cannot be a symlink"):
        publish_audience_revision(**{**audience, key: link})
    assert not audience["store_path"].exists()
    assert list(audience["vault_path"].iterdir()) == []
    if target == "store":
        assert original.read_bytes() == b"human-owned store-shaped file"


def test_snapshot_collision_at_link_boundary_preserves_human_bytes_and_pending_revision(
    audience, monkeypatch
):
    marker = b"Human file appeared at the snapshot path during publication.\n"

    def concurrent_writer(_source, target):
        Path(target).write_bytes(marker)
        raise FileExistsError(target)

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", concurrent_writer)
        with pytest.raises(ProjectionError, match="conflict"):
            publish_audience_revision(**audience)
    with sqlite3.connect(audience["store_path"]) as conn:
        assert conn.execute(
            "SELECT revision, projection_status FROM cairntir_audience_revisions"
        ).fetchall() == [(1, "pending")]
    path = next(audience["vault_path"].rglob("revision-*.md"))
    assert path.read_bytes() == marker
    with pytest.raises(ProjectionError, match=r"changed|conflict"):
        publish_audience_revision(**audience)
    assert path.read_bytes() == marker
    path.unlink()
    retry = publish_audience_revision(**audience)
    assert retry["revision"] == 1
    assert retry["projection_status"] == "ready"
    assert Path(retry["snapshot_path"]).read_bytes() != marker


def test_identical_snapshot_created_by_a_racer_is_accepted_without_new_revision(
    audience, monkeypatch
):
    def concurrent_writer(source, target):
        Path(target).write_bytes(Path(source).read_bytes())
        raise FileExistsError(target)

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", concurrent_writer)
        first = publish_audience_revision(**audience)
    assert first["revision"] == 1 and first["projection_status"] == "ready"
    assert publish_audience_revision(**audience)["revision"] == 1
    with sqlite3.connect(audience["store_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cairntir_audience_revisions").fetchone()[0] == 1


def test_snapshot_replaced_by_a_directory_is_a_typed_conflict(audience):
    first = publish_audience_revision(**audience)
    snapshot = Path(first["snapshot_path"])
    snapshot.unlink()
    snapshot.mkdir()
    human_file = snapshot / "human-note.md"
    human_file.write_bytes(b"Human contents inside a conflicting directory.\n")
    with pytest.raises(ProjectionError, match="cannot read audience snapshot"):
        publish_audience_revision(**audience)
    assert human_file.read_bytes() == b"Human contents inside a conflicting directory.\n"
    with sqlite3.connect(audience["store_path"]) as conn:
        assert conn.execute(
            "SELECT revision, projection_status FROM cairntir_audience_revisions"
        ).fetchall() == [(1, "ready")]


def test_temporary_snapshot_failure_keeps_committed_revision_pending_for_retry(
    audience, monkeypatch
):
    from cairntir import ideation_audience

    def denied_temporary_file(**_kwargs):
        raise PermissionError("snapshot directory temporarily denied")

    with monkeypatch.context() as patch:
        patch.setattr(ideation_audience.tempfile, "NamedTemporaryFile", denied_temporary_file)
        with pytest.raises(ProjectionError, match="cannot materialize audience snapshot"):
            publish_audience_revision(**audience)
    with sqlite3.connect(audience["store_path"]) as conn:
        assert conn.execute(
            "SELECT revision, projection_status FROM cairntir_audience_revisions"
        ).fetchall() == [(1, "pending")]
    assert not list(audience["vault_path"].rglob("revision-*.md"))
    assert publish_audience_revision(**audience)["revision"] == 1


def test_wrong_vault_read_rejects_without_mutating_either_vault(audience, tmp_path):
    first = publish_audience_revision(**audience)
    original = _snapshots(audience["vault_path"])
    other = tmp_path / "another-vault"
    other.mkdir()
    human_note = other / "SPEC.md"
    human_note.write_bytes(b"# Another human's specification\r\n")
    with pytest.raises(ProjectionError, match="another vault"):
        get_audience_revision(audience["store_path"], other, audience["wing"])
    assert _snapshots(audience["vault_path"]) == original
    assert list(other.iterdir()) == [human_note]
    assert human_note.read_bytes() == b"# Another human's specification\r\n"
    assert (
        get_audience_revision(audience["store_path"], audience["vault_path"], audience["wing"])[
            "revision"
        ]
        == first["revision"]
    )


def test_read_with_no_revision_is_typed_and_leaves_human_file_untouched(audience):
    human_note = audience["vault_path"] / "SPEC.md"
    human_note.write_bytes(b"# Unrelated human note\n")
    with sqlite3.connect(audience["store_path"]) as conn:
        conn.execute("CREATE TABLE cairntir_audience_revisions (wing TEXT, revision INTEGER)")
    with pytest.raises(ProjectionError, match="no audience revision"):
        get_audience_revision(audience["store_path"], audience["vault_path"], audience["wing"])
    assert human_note.read_bytes() == b"# Unrelated human note\n"
    assert list(audience["vault_path"].iterdir()) == [human_note]


def test_read_with_missing_store_does_not_create_one(audience):
    with pytest.raises(ProjectionError, match="audience store does not exist"):
        get_audience_revision(audience["store_path"], audience["vault_path"], audience["wing"])
    assert not audience["store_path"].exists()
    assert list(audience["vault_path"].iterdir()) == []


def test_read_with_wrong_store_schema_is_typed_without_changing_human_note(audience):
    human_note = audience["vault_path"] / "SPEC.md"
    human_note.write_bytes(b"# Human note\n")
    with sqlite3.connect(audience["store_path"]) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    with pytest.raises(ProjectionError, match="cannot read audience revision"):
        get_audience_revision(audience["store_path"], audience["vault_path"], audience["wing"])
    assert human_note.read_bytes() == b"# Human note\n"


@pytest.mark.parametrize(
    ("content", "state"),
    [
        (None, "absent"),
        (b"# Human-owned note\r\nNo Cairntir block.\r\n", "none"),
        (b"<!-- cairntir:audience:begin -->\nno end\n", "ambiguous"),
        (b"<!-- cairntir:audience:end -->\nno begin\n", "ambiguous"),
    ],
)
def test_legacy_scan_classifies_without_promoting_or_editing_human_file(audience, content, state):
    spec = audience["vault_path"] / "SPEC.md"
    if content is not None:
        spec.write_bytes(content)
    result = scan_legacy_audience(spec)
    assert result == {"state": state, "spec_path": str(spec)}
    assert (spec.read_bytes() if spec.exists() else None) == content
    assert not audience["store_path"].exists()


def test_legacy_scan_invalid_utf8_is_typed_and_preserves_original_bytes(audience):
    spec = audience["vault_path"] / "SPEC.md"
    spec.write_bytes(b"# Human note\n\xff\xfe")
    with pytest.raises(ProjectionError, match="cannot read legacy audience note"):
        scan_legacy_audience(spec)
    assert spec.read_bytes() == b"# Human note\n\xff\xfe"
    assert not audience["store_path"].exists()


def test_legacy_scan_invalid_path_is_typed_without_vault_change(audience):
    with pytest.raises(ProjectionError, match="invalid legacy audience path"):
        scan_legacy_audience(1)
    assert list(audience["vault_path"].iterdir()) == []
