from pathlib import Path
from typing import ClassVar

from cairntir.errors import ProjectionError
from cairntir.ideation_angles import OllamaAnglesAdapter, generate_angle_set

from . import test_i02 as fixture


class ClaimedLocal(fixture.FixtureAdapter):
    identity: ClassVar[dict[str, str]] = {
        "kind": "ollama",
        "model_id": "qwen2.5-coder:7b",
        "prompt_version": "cairntir-angles-v1",
    }

    def generate(self, bundle):
        envelope = super().generate(bundle)
        envelope["actual_model"] = "qwen2.5-coder:7b"
        body = {
            "actual_model": envelope["actual_model"],
            "done": envelope["done"],
            "candidates": envelope["candidates"],
        }
        envelope["raw_response_sha256"] = fixture._sha(fixture._canonical(body))
        return envelope


class ClaimedSubclass(OllamaAnglesAdapter):
    identity = ClaimedLocal.identity

    def __init__(self):
        pass

    def generate(self, bundle):
        return ClaimedLocal().generate(bundle)


def test_caller_controlled_adapter_cannot_claim_verified_local_model(tmp_path):
    for label, adapter_type in (("plain", ClaimedLocal), ("subclass", ClaimedSubclass)):
        home = tmp_path / label
        home.mkdir()
        prepared = fixture.prepared.__wrapped__(home)
        adapter = adapter_type()
        try:
            result = generate_angle_set(**fixture._request(prepared, adapter))
        except ProjectionError:
            assert fixture._angle_rows(prepared["store"]) == 0
        else:
            assert result["generation_provenance"] == "fixture_unverified"
            note = Path(result["current_note_path"])
            if note.exists():
                assert "verified_local_adapter" not in note.read_text(encoding="utf-8")
