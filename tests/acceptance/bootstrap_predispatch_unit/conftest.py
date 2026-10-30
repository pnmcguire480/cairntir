"""Supply local inputs for refusals that must precede tool execution."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

collect_ignore = ["fixtures"]


@pytest.fixture(autouse=True)
def predispatch_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    executable = shutil.which("uv")
    assert executable is not None, "Predispatch controls require the available uv executable"
    wheelhouse = tmp_path / "empty-wheelhouse"
    wheelhouse.mkdir()
    for name, value in {
        "Q07_REPO": Path(__file__).resolve().parents[3],
        "Q07_PYTHON": Path(sys.executable).resolve(strict=True),
        "Q07_UV": Path(executable).resolve(strict=True),
        "Q07_WHEELHOUSE": wheelhouse,
    }.items():
        monkeypatch.setenv(name, str(value))

    def no_process(*args: object, **kwargs: object) -> None:
        pytest.fail("Predispatch refusal invoked a subprocess")

    def no_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Predispatch refusal attempted network access")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    yield
    assert not list(wheelhouse.iterdir())
