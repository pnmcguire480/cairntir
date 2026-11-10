import hashlib
import json
import zipfile
from email.feedparser import BytesFeedParser
from email.parser import BytesParser
from pathlib import Path

from cairntir.paladin_resources import PaladinResourcesRun

from .acceptance import fixture

PRIMARY = Path(__file__).resolve().parent
FIXTURE_SHA256 = "e57bd1c0221cdc1b6233361ed691a296d8476b87f3b4f35b9b1a13a6e659b002"


def _fixture_module():
    path = PRIMARY / "acceptance/fixture.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise RuntimeError("Q05 primary fixture changed")
    return fixture


def test_actual_metadata_description_budget_avoids_accumulating_overbudget_parser_feed(
    tmp_path, monkeypatch
):
    module = _fixture_module()
    fixture = module.ResourceFixture(tmp_path / "metadata-description-budget")
    try:
        payload = (b"0" * 127 + b"\n") * 2048
        assert len(payload) == 256 * 1024
        (fixture.snapshot / "README.md").write_bytes(payload)
        project = fixture.snapshot / "pyproject.toml"
        project.write_text(
            project.read_text(encoding="utf-8").replace(
                'version = "0.0.1"', 'version = "0.0.1"\nreadme = "README.md"', 1
            ),
            encoding="utf-8",
        )
        fixture.contract["inputs"] = module.inventory(fixture.snapshot)
        budget = fixture.contract["policy"]["bundle_uncompressed_bytes"]
        attempted = []
        fed_bytes = {}
        original_feed = BytesFeedParser.feed

        def bounded_feed(parser, data):
            previous = fed_bytes.get(parser, 0)
            candidate = previous + len(data)
            if candidate > budget:
                attempted.append({"accepted_bytes": previous, "refused_bytes": len(data)})
                raise RuntimeError(
                    "independent guard refused accumulating metadata beyond bundle budget"
                )
            fed_bytes[parser] = candidate
            return original_feed(parser, data)

        with monkeypatch.context() as patcher:
            patcher.setattr(BytesFeedParser, "feed", bounded_feed)
            receipt = PaladinResourcesRun(fixture.runtime, contract=fixture.contract).execute(
                "bundle", fixture.action("bundle")
            )
        wheel = fixture.output / "bundle/q05_notes-0.0.1-py3-none-any.whl"
        with zipfile.ZipFile(wheel) as archive:
            raw_metadata = archive.read("q05_notes-0.0.1.dist-info/METADATA")
            metadata = BytesParser().parsebytes(raw_metadata)
            assert metadata.get_payload().encode("utf-8") == payload
            assert metadata["Name"] == "q05-notes"
            assert metadata["Version"] == "0.0.1"
            assert not metadata.defects
            assert archive.testzip() is None
            uncompressed = sum(item.file_size for item in archive.infolist() if not item.is_dir())
        observed = {
            "receipt": receipt,
            "forbidden_parser_feeds": attempted,
            "maximum_accepted_parser_bytes": max(fed_bytes.values(), default=0),
            "compressed_bytes": wheel.stat().st_size,
            "uncompressed_bytes": uncompressed,
            "metadata_bytes": len(raw_metadata),
            "description_bytes": len(payload),
            "description_sha256": hashlib.sha256(payload).hexdigest(),
            "metadata_sha256": hashlib.sha256(raw_metadata).hexdigest(),
            "actual_wheel_crc_verified_after_guard": True,
            "actual_metadata_description_verified_after_guard": True,
        }
        (fixture.root / "independent-metadata-observation.json").write_text(
            json.dumps(observed, indent=2) + "\n", encoding="utf-8"
        )
        assert receipt["managed_result"]["outcome_drawer_id"] > 0
        assert receipt["managed_result"]["exit_code"] == 0
        assert wheel.stat().st_size <= fixture.contract["policy"]["bundle_compressed_bytes"]
        assert uncompressed > budget
        assert receipt["status"] == "FAIL", observed
        assert "BUNDLE_UNCOMPRESSED_BUDGET" in receipt["diagnostics"]
        assert receipt["metrics"]["compressed_bytes"] == wheel.stat().st_size
        assert receipt["metrics"]["uncompressed_bytes"] == uncompressed
        assert attempted == []
        assert (
            PaladinResourcesRun(fixture.runtime, contract=fixture.contract).report()["disposition"]
            == "BLOCKED"
        )
    finally:
        fixture.close()
