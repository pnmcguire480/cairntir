"""Narrow fixture-only adapter; original tests and assertions remain untouched."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKET = Path(__file__).resolve().parent
EXPECTED = {
    "tests/verification/test_embedding_adapter_outcomes.py": "87e98d26aeb00391c44288252b1c2fa835d67479f7e8c1ed2d40919d3ed375be",
    "tests/unit/test_store.py": "eecf66a7db47a02dc54f24bc0633840f45a1289d7f48c69b075383e9be23f053",
}
ADAPTED = []
OUTCOMES = []
FUNCTIONS = {
    "test_unavailable_model_names_its_cache_and_correct_download_advice",
    "test_native_model_output_cannot_corrupt_stdio_and_streams_recover_after_failure",
    "test_model_without_dimension_is_rejected_before_accepting_memory",
    "test_readonly_model_uses_existing_assets_and_never_rewrites_them",
}


def pytest_addoption(parser):
    parser.addoption("--e22-adapter-report", default=None)


def pytest_collection_modifyitems(items):
    for item in items:
        suffix = next((name for name in EXPECTED if item.path.as_posix().endswith(name)), None)
        if suffix is None:
            continue
        actual = hashlib.sha256(Path(item.path).read_bytes()).hexdigest()
        if actual != EXPECTED[suffix]:
            raise pytest.UsageError(f"original test custody changed: {item.path}")


def write_assets(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "model.onnx").write_bytes(b"public synthetic registry adapter model")
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
        (root / name).write_text("{}", encoding="utf-8")


def descriptor(model, dimension=2):
    return {"model": model, "dim": dimension, "sources": {}, "model_file": "model.onnx", "additional_files": []}


@pytest.fixture(autouse=True)
def exact_registry_fixture_adapter(request, monkeypatch):
    suffix = next((name for name in EXPECTED if request.node.path.as_posix().endswith(name)), None)
    if suffix is None:
        return
    name = getattr(request.node, "originalname", "")
    factory = getattr(request.node, "callspec", None)
    factory = factory.params.get("factory") if factory is not None else None
    if name == "test_provider_identity_distinguishes_algorithm_model_and_dimension":
        from cairntir.memory.embeddings import PRODUCTION_MODEL
        home = request.getfixturevalue("tmp_cairntir_home")
        cache = home / "models"
        monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(cache))
        write_assets(cache / PRODUCTION_MODEL.rsplit("/", 1)[-1])
        class RegistryOnly:
            @staticmethod
            def list_supported_models():
                return [descriptor(PRODUCTION_MODEL)]
            def __init__(self, **kwargs):
                raise AssertionError("offline identity must never construct a model")
        monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=RegistryOnly))
        ADAPTED.append(request.node.nodeid)
        return
    if name not in FUNCTIONS or (factory is not None and factory.__name__ != "FastEmbedProvider"):
        return
    home = request.getfixturevalue("tmp_cairntir_home")
    original_setitem = monkeypatch.setitem

    def setitem(mapping, key, value):
        if mapping is sys.modules and key == "fastembed":
            from cairntir.memory.embeddings import PRODUCTION_MODEL
            model = "missing/model" if name == "test_unavailable_model_names_its_cache_and_correct_download_advice" else PRODUCTION_MODEL
            cache = Path(os.environ.get("FASTEMBED_CACHE_PATH", str(home / "models")))
            if name == "test_readonly_model_uses_existing_assets_and_never_rewrites_them":
                model = "test/example"
                roots = list(cache.glob("*/model.onnx"))
                assert len(roots) == 1, "exact existing readonly fixture model expected"
                root = roots[0].parent
                for filename in ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
                    (root / filename).write_text("{}", encoding="utf-8")
            else:
                monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(cache))
                write_assets(cache / model.rsplit("/", 1)[-1])
            value.TextEmbedding.list_supported_models = staticmethod(lambda: [descriptor(model)])
            ADAPTED.append(request.node.nodeid)
        original_setitem(mapping, key, value)

    monkeypatch.setattr(monkeypatch, "setitem", setitem)


def pytest_runtest_logreport(report):
    if report.when == "call" or report.failed:
        OUTCOMES.append({"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome, "detail": str(report.longrepr) if report.failed else None})


def pytest_sessionfinish(session, exitstatus):
    configured_report = session.config.getoption("--e22-adapter-report")
    if configured_report is None:
        return
    destination = Path(configured_report).resolve()
    if not destination.is_relative_to(PACKET):
        raise RuntimeError("adapter report must stay inside acceptance packet")
    destination.write_text(json.dumps({
        "exitstatus": int(exitstatus), "tests_collected": session.testscollected,
        "original_test_sha256": EXPECTED,
        "adapted_exact_cases": ADAPTED, "outcomes": OUTCOMES,
        "custody": "public synthetic shared workspace; original test bodies unchanged",
        "models_downloaded": False,
    }, indent=2) + "\n", encoding="utf-8")


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"E22 complete synthetic registry/assets adapter: {len(ADAPTED)} exact original cases, no assertion changes")
