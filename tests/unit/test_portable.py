"""Unit tests for the v0.5 portable signed drawer format."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cairntir.errors import ExternalUrlError, PortableFormatError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.portable import (
    FORMAT_VERSION,
    decode_drawer,
    encode_drawer,
    ensure_no_external_urls,
    export_drawers,
    import_drawers,
    read_jsonl,
    write_jsonl,
)

KEY: bytes = b"test-signing-key-do-not-use-in-prod"


def _d(**overrides: object) -> Drawer:
    base: dict[str, object] = {
        "wing": "cairntir",
        "room": "portable",
        "content": "the cairn sees across time",
        "layer": Layer.ON_DEMAND,
        "metadata": {"source": "test"},
        "created_at": datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return Drawer(**base)  # type: ignore[arg-type]


# --------- encode / decode ---------------------------------------------


def test_encode_decode_round_trip_preserves_drawer() -> None:
    original = _d(
        claim="v0.5 lands the format first",
        predicted_outcome="content hashes are deterministic",
        delta="no surprise",
        belief_mass=2.5,
    )
    envelope = encode_drawer(original)
    assert envelope["format_version"] == FORMAT_VERSION
    assert envelope["content_hash"].startswith("sha256:")
    assert envelope["signature"] is None
    recovered = decode_drawer(envelope)
    # Everything portable survives; id/access tracking does not and is
    # not compared — portable drawers are born without a local id.
    for field in (
        "wing",
        "room",
        "content",
        "layer",
        "metadata",
        "created_at",
        "claim",
        "predicted_outcome",
        "observed_outcome",
        "delta",
        "supersedes_id",
        "belief_mass",
    ):
        assert getattr(recovered, field) == getattr(original, field)


def test_content_hash_is_deterministic_across_encodes() -> None:
    a = encode_drawer(_d())
    b = encode_drawer(_d())
    assert a["content_hash"] == b["content_hash"]


def test_content_hash_changes_when_content_changes() -> None:
    a = encode_drawer(_d(content="one"))
    b = encode_drawer(_d(content="two"))
    assert a["content_hash"] != b["content_hash"]


def test_tampered_envelope_fails_hash_verification() -> None:
    envelope = encode_drawer(_d())
    envelope["drawer"]["content"] = "tampered"
    with pytest.raises(PortableFormatError, match="content hash mismatch"):
        decode_drawer(envelope)


def test_signed_envelope_verifies_with_matching_key() -> None:
    envelope = encode_drawer(_d(), signing_key=KEY)
    assert envelope["signature"] is not None
    assert envelope["signature"].startswith("hmac-sha256:")
    recovered = decode_drawer(envelope, verify_key=KEY)
    assert recovered.content == "the cairn sees across time"


def test_signed_envelope_rejects_wrong_key() -> None:
    envelope = encode_drawer(_d(), signing_key=KEY)
    with pytest.raises(PortableFormatError, match="signature mismatch"):
        decode_drawer(envelope, verify_key=b"wrong-key")


def test_verification_requested_on_unsigned_envelope_fails() -> None:
    envelope = encode_drawer(_d())
    with pytest.raises(PortableFormatError, match="unsigned"):
        decode_drawer(envelope, verify_key=KEY)


def test_unsupported_format_version_is_rejected() -> None:
    envelope = encode_drawer(_d())
    envelope["format_version"] = 999
    with pytest.raises(PortableFormatError, match="unsupported format_version"):
        decode_drawer(envelope)


def test_missing_drawer_payload_is_rejected() -> None:
    with pytest.raises(PortableFormatError, match="missing a drawer payload"):
        decode_drawer({"format_version": FORMAT_VERSION})


# --------- external URL prohibition ------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "see http://example.com for details",
        "HTTPS://foo.bar/baz",
        "ftp://old-server/file.zip",
        "file:///etc/passwd",
        "ssh://user@host",
    ],
)
def test_external_urls_are_rejected_at_export(content: str) -> None:
    with pytest.raises(ExternalUrlError):
        ensure_no_external_urls(_d(content=content))


def test_cairntir_scheme_is_allowed() -> None:
    ensure_no_external_urls(_d(content="see cairntir://sha256:abc for context"))


def test_external_url_in_metadata_is_rejected() -> None:
    with pytest.raises(ExternalUrlError):
        ensure_no_external_urls(_d(metadata={"see": "https://rotprone.example"}))


def test_encode_fails_closed_on_external_url() -> None:
    with pytest.raises(ExternalUrlError):
        encode_drawer(_d(content="visit https://example.com"))


# --------- JSONL + bulk export/import ----------------------------------


def test_write_and_read_jsonl_round_trips(tmp_path: Path) -> None:
    envelopes = [encode_drawer(_d(content=f"fact {i}")) for i in range(3)]
    path = tmp_path / "out.jsonl"
    count = write_jsonl(envelopes, path)
    assert count == 3
    assert [e["content_hash"] for e in read_jsonl(path)] == [e["content_hash"] for e in envelopes]


def test_export_import_across_stores_preserves_drawers(tmp_path: Path) -> None:
    src_db = tmp_path / "src.db"
    dst_db = tmp_path / "dst.db"
    out = tmp_path / "bundle.jsonl"

    with DrawerStore(src_db, HashEmbeddingProvider(dimension=32)) as src:
        src.add(_d(content="alpha"))
        src.add(_d(content="beta", claim="beta holds", predicted_outcome="yes"))
        src.add(_d(content="gamma", belief_mass=3.0))
        exported = export_drawers(
            src.list_by(wing="cairntir", limit=100),
            out,
            signing_key=KEY,
        )
    assert exported == 3

    imported = import_drawers(out, verify_key=KEY)
    assert {d.content for d in imported} == {"alpha", "beta", "gamma"}

    with DrawerStore(dst_db, HashEmbeddingProvider(dimension=32)) as dst:
        for drawer in imported:
            dst.add(drawer)
        landed = dst.list_by(wing="cairntir", limit=100)
    assert {d.content for d in landed} == {"alpha", "beta", "gamma"}
    beta = next(d for d in landed if d.content == "beta")
    assert beta.claim == "beta holds"
    assert beta.predicted_outcome == "yes"
    gamma = next(d for d in landed if d.content == "gamma")
    assert gamma.belief_mass == pytest.approx(3.0)


def test_read_jsonl_rejects_non_object_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(PortableFormatError, match="not a JSON object"):
        read_jsonl(path)


def test_read_jsonl_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(PortableFormatError, match="invalid JSON"):
        read_jsonl(path)


@pytest.fixture()
def _unused() -> Iterator[None]:
    yield None
