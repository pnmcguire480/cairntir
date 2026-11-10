"""Ordinary temporary isolation for the original inert R17 unittest cases."""

import builtins
import os
import socket
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch, request):
    module = request.module
    repo = Path(__file__).resolve().parents[3]
    assert Path(module.API.__file__).resolve() == repo / "src/cairntir/procedures.py"
    monkeypatch.setattr(module, "ROOT", tmp_path)
    for name in (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "CAIRNTIR_HOME",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "TMP",
        "TEMP",
    ):
        target = tmp_path / "isolation" / name.lower()
        target.mkdir(parents=True)
        monkeypatch.setenv(name, str(target))
    for name in (
        "CAIRNTIR_DISABLE_AUTOREGISTER",
        "CAIRNTIR_DISABLE_UPDATE_CHECK",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("PYTHONPATH", str(repo / "src"))
    importer = builtins.__import__

    def safe_import(name, *args, **kwargs):
        if name.split(".")[0] in {
            "fastembed",
            "onnxruntime",
            "sentence_transformers",
            "transformers",
            "torch",
            "huggingface_hub",
        }:
            raise AssertionError("Model dependency import denied")
        return importer(name, *args, **kwargs)

    def deny(*args, **kwargs):
        raise AssertionError("Network or process launch denied")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(os, "system", deny)
    monkeypatch.setattr(builtins, "__import__", safe_import)
