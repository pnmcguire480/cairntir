from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

import cairntir.cli as cli
from cairntir.daemon import CaptureDaemon, spool_dir, write_capture
from cairntir.errors import CairntirError, PortableFormatError, ProjectionError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.obsidian import project_to_obsidian
from cairntir.portable import (
    content_hash,
    decode_drawer,
    encode_drawer,
    export_drawers,
    read_jsonl,
    write_jsonl,
)
from cairntir.provenance import TrustLevel


@pytest.fixture()
def isolated_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database = tmp_path / "memory.db"
    monkeypatch.setattr(cli, "db_path", lambda: database)
    monkeypatch.setattr(
        cli, "production_embedding_provider", lambda: HashEmbeddingProvider(dimension=16)
    )
    return database


def _drawer(content: str = "A portable fact.", **kwargs: object) -> Drawer:
    return Drawer(wing="shipping", room="evidence", content=content, **kwargs)


def test_unsigned_import_is_untrusted_and_retries_preserve_one_drawer(
    tmp_path: Path, isolated_cli: Path
) -> None:
    bundle = tmp_path / "bundle.jsonl"
    export_drawers([_drawer()], bundle)
    cli.import_cmd(bundle, idempotency_key=None)
    cli.import_cmd(bundle, idempotency_key=None)
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        drawers = store.list_by()
        assert len(drawers) == 1
        assert drawers[0].content == "A portable fact."
        assert drawers[0].id is not None
        receipt = store.get_provenance(drawers[0].id)
        assert receipt is not None
        assert receipt.capture_path == "cli.import"
        assert receipt.trust is TrustLevel.UNTRUSTED


def test_import_never_binds_foreign_local_ids_to_destination_history(
    tmp_path: Path, isolated_cli: Path
) -> None:
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        unrelated = store.add(_drawer("An unrelated local prediction."))
        assert unrelated.id == 1
    bundle = tmp_path / "linked.jsonl"
    write_jsonl([encode_drawer(_drawer("An imported successor.", supersedes_id=1))], bundle)
    rejected = False
    try:
        cli.import_cmd(bundle, idempotency_key=None)
    except CairntirError:
        rejected = True
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        successors = [item for item in store.list_by() if item.content == "An imported successor."]
        if rejected:
            assert successors == []
        for successor in successors:
            assert successor.supersedes_id != unrelated.id


def test_failed_import_batch_rolls_back_preceding_drawers(
    tmp_path: Path, isolated_cli: Path
) -> None:
    bundle = tmp_path / "invalid-batch.jsonl"
    export_drawers(
        [_drawer("The first fact."), _drawer("Invalid anchor.", metadata={"anchors": 42})],
        bundle,
    )
    with pytest.raises(CairntirError):
        cli.import_cmd(bundle, idempotency_key=None)
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        assert store.list_by() == []


@pytest.mark.parametrize(
    "foreign_reference",
    [
        {"evidence_drawer_ids": [1]},
        {"counterexample_drawer_ids": [1]},
        {"walkthrough_id": 1},
        {"derived_from": [1]},
    ],
)
def test_import_rejects_unresolvable_foreign_metadata_references(
    tmp_path: Path, isolated_cli: Path, foreign_reference: dict[str, object]
) -> None:
    bundle = tmp_path / "foreign-evidence.jsonl"
    export_drawers([_drawer(metadata=foreign_reference)], bundle)
    with pytest.raises(CairntirError):
        cli.import_cmd(bundle, idempotency_key=None)
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        assert store.list_by() == []


def test_import_rejects_foreign_local_drawer_uri(tmp_path: Path, isolated_cli: Path) -> None:
    bundle = tmp_path / "foreign-uri.jsonl"
    export_drawers([_drawer("Evidence is cairntir://drawer/1 in the exporting store.")], bundle)
    with pytest.raises(CairntirError):
        cli.import_cmd(bundle, idempotency_key=None)
    with DrawerStore(isolated_cli, HashEmbeddingProvider(dimension=16)) as store:
        assert store.list_by() == []


def test_jsonl_failed_stream_preserves_existing_backup(tmp_path: Path) -> None:
    backup = tmp_path / "backup.jsonl"
    original = b"Existing user backup; preserve these exact bytes.\n"
    backup.write_bytes(original)

    def interrupted_stream() -> Iterator[dict[str, object]]:
        yield {"first": "a complete record"}
        raise OSError("The source failed while exporting the next record.")

    with pytest.raises((OSError, PortableFormatError)):
        write_jsonl(interrupted_stream(), backup)
    assert backup.read_bytes() == original
    assert list(tmp_path.iterdir()) == [backup]


def test_portable_invalid_utf8_is_a_typed_format_error(tmp_path: Path) -> None:
    bundle = tmp_path / "corrupt.jsonl"
    bundle.write_bytes(b"\xff\xfe\x80")
    with pytest.raises(PortableFormatError):
        read_jsonl(bundle)


@pytest.mark.parametrize("field", ["content", "metadata"])
def test_hash_valid_import_cannot_bypass_the_external_url_boundary(field: str) -> None:
    drawer = (
        _drawer("A reference to https://example.invalid/evidence")
        if field == "content"
        else _drawer(metadata={"source": "file:///private/evidence"})
    )
    envelope = encode_drawer(_drawer())
    envelope["drawer"] = drawer.model_dump(mode="json", exclude={"id"})
    envelope["content_hash"] = content_hash(drawer)
    with pytest.raises(CairntirError):
        decode_drawer(envelope)


@pytest.mark.parametrize(
    "bad_payload",
    [
        b"\xff\xfe\x80",
        b'{"wing":"shipping","room":"evidence","content":null}',
        b'{"wing":"shipping","room":"evidence","content":["not", "verbatim"]}',
        b'{"wing":123,"room":"evidence","content":"Bad wing type"}',
        b'{"wing":"shipping","room":123,"content":"Bad room type"}',
    ],
    ids=["invalid-utf8", "null-content", "array-content", "numeric-wing", "numeric-room"],
)
def test_bad_spool_input_is_quarantined_and_does_not_block_next_request(
    tmp_path: Path, bad_payload: bytes
) -> None:
    spool = spool_dir(tmp_path)
    malformed = spool / "00000000000000000001-invalid.json"
    malformed.write_bytes(bad_payload)
    request = "The next user's request must survive exactly."
    write_capture(spool, wing="shipping", room="evidence", content=request)
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=16)) as store:
        daemon = CaptureDaemon(store, spool)
        assert daemon.tick() == 1
        assert daemon.stats.failed == 1
        assert [drawer.content for drawer in store.list_by()] == [request]
    quarantined = spool / "failed" / malformed.name
    assert quarantined.read_bytes() == bad_payload
    assert quarantined.with_suffix(".json.error").read_text(encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("linked_dir", ["cairntir-sync", "cairntir-sync/codeglass"])
def test_obsidian_projection_does_not_write_through_output_directory_links(
    tmp_path: Path, linked_dir: str
) -> None:
    vault = _vault(tmp_path)
    outside = tmp_path / "outside-vault"
    outside.mkdir()
    sentinel = outside / "user.md"
    sentinel.write_bytes(b"Original user note\r\n")
    link = vault / linked_dir
    link.parent.mkdir(parents=True, exist_ok=True)
    _directory_link(link, outside)
    with DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=16)) as store:
        store.add(
            Drawer(
                wing="shipping",
                room="codeglass",
                content="A walkthrough that must stay in the selected vault.",
                metadata={
                    "kind": "codeglass.walkthrough",
                    "target": "Bounded projection",
                    "evidence_drawer_ids": [],
                },
            )
        )
        with pytest.raises(ProjectionError):
            project_to_obsidian(store, vault=vault)
    assert list(outside.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"Original user note\r\n"


def test_obsidian_rejects_ambiguous_markers_without_erasing_user_text(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    note = vault / "cairntir-sync" / "learning-log.md"
    note.parent.mkdir()
    original = (
        b"<!-- cairntir:generated:begin -->\n"
        b"A user copied a marker as part of this introduction.\n"
        b"<!-- cairntir:generated:begin -->\nOld generated content.\n"
        b"<!-- cairntir:generated:end -->\nMy notes must remain.\n"
    )
    note.write_bytes(original)
    with (
        DrawerStore(tmp_path / "memory.db", HashEmbeddingProvider(dimension=16)) as store,
        pytest.raises(ProjectionError),
    ):
        project_to_obsidian(store, vault=vault)
    assert note.read_bytes() == original
