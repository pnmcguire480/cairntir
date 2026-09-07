from __future__ import annotations

import builtins
import os
import sys
from types import SimpleNamespace

import pytest

from cairntir.errors import EmbeddingError
from cairntir.memory.embeddings import (
    FastEmbedProvider,
    SentenceTransformerProvider,
    embed_query_readonly,
)


@pytest.mark.parametrize(
    ("factory", "module", "hint"),
    [
        (FastEmbedProvider, "fastembed", "core dependencies"),
        (SentenceTransformerProvider, "sentence_transformers", "legacy-embeddings"),
    ],
)
def test_missing_embedding_dependency_reports_the_installation_needed(
    tmp_cairntir_home, monkeypatch, factory, module, hint
):
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == module:
            raise ImportError("dependency is absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    (tmp_cairntir_home / "mcp.log").touch()
    files = set(tmp_cairntir_home.iterdir())
    provider = factory()
    with pytest.raises(EmbeddingError, match=hint):
        provider.embed(["memory"])
    assert set(tmp_cairntir_home.iterdir()) == files


@pytest.mark.parametrize("offline", ["0", "1"])
def test_unavailable_model_names_its_cache_and_correct_download_advice(
    tmp_cairntir_home, monkeypatch, offline
):
    monkeypatch.setenv("HF_HUB_OFFLINE", offline)
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)

    def unavailable(**kwargs):
        raise OSError("model files unavailable")

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=unavailable))
    with pytest.raises(EmbeddingError) as raised:
        FastEmbedProvider("missing/model").embed(["memory"])
    message = str(raised.value)
    assert "missing/model" in message and str(tmp_cairntir_home / "models") in message
    assert ("offline mode is on" if offline == "1" else "network allows") in message
    assert isinstance(raised.value.__cause__, OSError)


@pytest.mark.parametrize("factory", [FastEmbedProvider, SentenceTransformerProvider])
@pytest.mark.parametrize("fail", [False, True])
def test_native_model_output_cannot_corrupt_stdio_and_streams_recover_after_failure(
    tmp_cairntir_home, monkeypatch, capfd, factory, fail
):
    class NoisyModel:
        def __init__(self, *args, **kwargs):
            os.write(1, b"native model startup\n")
            print("python model startup")

        def get_sentence_embedding_dimension(self):
            return 2

        def embed(self, texts):
            os.write(2, b"native model inference\n")
            print("python inference")
            if texts != ["dimension probe"] and fail:
                raise RuntimeError("inference failed")
            return [[0.6, 0.8] for _ in texts]

        def encode(self, texts, **kwargs):
            assert kwargs == {"normalize_embeddings": True, "convert_to_numpy": True}
            return self.embed(texts)

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=NoisyModel))
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=NoisyModel)
    )
    provider = factory()
    assert provider.dimension == 2
    if fail:
        with pytest.raises(EmbeddingError, match="encode failed: inference failed"):
            provider.embed(["query"])
    else:
        assert provider.embed(["first", "second"]) == [[0.6, 0.8], [0.6, 0.8]]
    print("protocol output restored", flush=True)
    os.write(2, b"diagnostics restored\n")
    captured = capfd.readouterr()
    assert captured.out == "protocol output restored\n"
    assert captured.err == "diagnostics restored\n"


@pytest.mark.parametrize("factory", [FastEmbedProvider, SentenceTransformerProvider])
def test_model_without_dimension_is_rejected_before_accepting_memory(
    tmp_cairntir_home, monkeypatch, factory
):
    class MissingDimension:
        def __init__(self, *args, **kwargs):
            pass

        def get_sentence_embedding_dimension(self):
            return None

        def embed(self, texts):
            return []

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=MissingDimension))
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=MissingDimension)
    )
    with pytest.raises(EmbeddingError, match=r"no (probe vectors|embedding dimension)"):
        _ = factory().dimension


def test_readonly_query_never_creates_a_missing_cache(tmp_cairntir_home, monkeypatch):
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    before = set(tmp_cairntir_home.rglob("*"))
    with pytest.raises(EmbeddingError, match="existing local model cache"):
        embed_query_readonly(FastEmbedProvider(), "query")
    assert set(tmp_cairntir_home.rglob("*")) == before
    with pytest.raises(EmbeddingError, match="requires FastEmbed"):
        embed_query_readonly(SentenceTransformerProvider(), "query")
    assert set(tmp_cairntir_home.rglob("*")) == before


@pytest.mark.parametrize("directory", ["example", "fast-example"])
def test_readonly_model_uses_existing_assets_and_never_rewrites_them(
    tmp_cairntir_home, monkeypatch, directory
):
    cache = tmp_cairntir_home / "models"
    assets = cache / directory
    assets.mkdir(parents=True)
    model = assets / "model.onnx"
    model.write_bytes(b"external model loader fixture")
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(cache))
    calls = []

    class LocalModel:
        @staticmethod
        def list_supported_models():
            return [{"model": "test/example", "model_file": "model.onnx", "sources": {}}]

        def __init__(self, **kwargs):
            calls.append(kwargs)

        def embed(self, texts):
            assert texts == ["query"]
            return [[0.6, 0.8]]

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=LocalModel))
    before = {path: path.read_bytes() for path in cache.rglob("*") if path.is_file()}
    provider = FastEmbedProvider("test/example")
    assert embed_query_readonly(provider, "query") == [0.6, 0.8]
    assert embed_query_readonly(provider, "query") == [0.6, 0.8]
    assert calls == [
        {
            "model_name": "test/example",
            "cache_dir": str(cache),
            "specific_model_path": str(assets),
            "local_files_only": True,
        }
    ]
    assert {path: path.read_bytes() for path in cache.rglob("*") if path.is_file()} == before
    assert provider.dimension == 2


@pytest.mark.parametrize("vectors", [[], [[1.0], [2.0]]])
def test_readonly_inference_rejects_wrong_result_count(tmp_cairntir_home, vectors):
    provider = FastEmbedProvider()
    provider._model = SimpleNamespace(embed=lambda texts: vectors)
    with pytest.raises(EmbeddingError, match="invalid vector count"):
        embed_query_readonly(provider, "query")


def test_readonly_inference_surfaces_failure_without_writing_diagnostics(tmp_cairntir_home):
    def failed(texts):
        raise OSError("inference unavailable")

    provider = FastEmbedProvider()
    provider._model = SimpleNamespace(embed=failed)
    before = set(tmp_cairntir_home.rglob("*"))
    with pytest.raises(EmbeddingError, match="local task embedding failed: inference unavailable"):
        embed_query_readonly(provider, "query")
    assert set(tmp_cairntir_home.rglob("*")) == before
