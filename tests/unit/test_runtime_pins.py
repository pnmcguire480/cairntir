"""Installed embedding runtimes are part of a store's identity, so installs must not float.

An unpinned install resolves whatever is newest, which gives a store a different
identity from a locked build and refuses semantic reads and writes until a reindex.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIMES = ("fastembed", "numpy", "onnxruntime", "tokenizers")


def _exact_pins() -> dict[str, str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pins = {}
    for requirement in project["dependencies"]:
        name, separator, version = requirement.partition("==")
        if separator:
            pins[name] = version
    return pins


def _locked_versions() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package.get("version", "") for package in lock["package"]}


def test_every_identity_runtime_is_pinned_exactly() -> None:
    pins = _exact_pins()
    assert {name: name in pins for name in RUNTIMES} == dict.fromkeys(RUNTIMES, True)


def test_pins_match_the_locked_build() -> None:
    pins = _exact_pins()
    locked = _locked_versions()
    assert {name: pins[name] for name in RUNTIMES} == {name: locked[name] for name in RUNTIMES}
