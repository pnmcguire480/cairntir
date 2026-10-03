"""Run actual Cairntir CLI in its own process with only synthetic loader APIs."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import socket
import sys
import traceback
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.load(sys.stdin)
    root = Path(fixture["root"]).resolve()
    packet = Path(__file__).resolve().parent
    if not root.is_relative_to((packet / "runs").resolve()):
        raise RuntimeError("synthetic CLI root escaped acceptance runs")
    cache = Path(fixture["cache"])
    calls = []
    faults = {"construct_faults": 0, "inference_faults": 0}
    sys.path.insert(0, str(args.source_root.resolve() / "src"))
    sys.dont_write_bytecode = True

    def forbidden(*args, **kwargs):
        raise AssertionError("network/acquisition disabled in synthetic CLI process")

    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden

    class FakeTextEmbedding:
        @staticmethod
        def list_supported_models():
            return [copy.deepcopy(fixture["description"])]

        @staticmethod
        def download_model(*args, **kwargs):
            forbidden()

        def __init__(self, model_name=None, cache_dir=None, **kwargs):
            calls.append({"model_name": model_name, "cache_dir": cache_dir, **kwargs})
            self.pinned = kwargs.get("specific_model_path")
            if fixture["fail_construct"]:
                faults["construct_faults"] += 1
                raise RuntimeError("synthetic constructor failure")
            if not self.pinned:
                raise AssertionError("unexpected acquisition or unpinned model construction")

        def embed(self, texts, **kwargs):
            texts = list(texts)
            marker = fixture["fail_inference_text"]
            if fixture["fail_inference"] or (marker and any(marker in text for text in texts)):
                faults["inference_faults"] += 1
                raise RuntimeError("synthetic inference failure")
            dimension = fixture["description"]["dim"]
            return [[1.0 / dimension ** 0.5] * dimension for _ in texts]

    def cached(repo_id, filename, cache_dir=None, revision=None, **kwargs):
        if repo_id != "synthetic/jina-artifacts":
            return None
        repo = Path(cache_dir) / "models--synthetic--jina-artifacts"
        ref = repo / "refs" / "main"
        selected = revision if revision and revision != "main" else ref.read_text() if ref.exists() else None
        result = repo / "snapshots" / selected / filename if selected else None
        if result and not result.resolve().is_relative_to(root):
            return None
        return str(result) if result and result.is_file() else None

    fastembed = types.ModuleType("fastembed")
    fastembed.TextEmbedding = FakeTextEmbedding
    hub = types.ModuleType("huggingface_hub")
    hub.try_to_load_from_cache = cached
    hub.snapshot_download = forbidden
    hub.hf_hub_download = forbidden
    sys.modules.update(fastembed=fastembed, huggingface_hub=hub)
    from cairntir.cli import app
    sys.argv = ["cairntir", *fixture["arguments"]]
    code = 0
    try:
        app()
    except SystemExit as error:
        code = int(error.code or 0)
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        receipt = Path(fixture["receipt"]).resolve()
        if not receipt.is_relative_to(root):
            raise RuntimeError("CLI receipt escaped synthetic root")
        receipt.write_text(json.dumps({"calls": calls, **faults}, indent=2) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
