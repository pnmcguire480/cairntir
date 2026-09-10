"""Independent store/config continuity acceptance; frozen before product repair."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cairntir.access import issue_grant
from cairntir.config import cairntir_home, db_path
from cairntir.errors import ConfigError
from cairntir.hosts import HostName, HostScope, configure_host, inspect_host
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer

ROOT = Path(__file__).resolve().parents[2]
REQUEST = "  Keep the café request verbatim.\nNo production changes.\tVerify continuity.\n"
JSON_HOSTS = [
    ("claude", "project", ".mcp.json"),
    ("cursor", "project", ".cursor/mcp.json"),
    ("cursor", "user", ".cursor/mcp.json"),
    ("qwen", "project", ".qwen/settings.json"),
    ("qwen", "user", ".qwen/settings.json"),
    ("gemini", "project", ".gemini/settings.json"),
    ("gemini", "user", ".gemini/settings.json"),
    ("copilot", "project", ".github/mcp.json"),
    ("copilot", "user", ".copilot/mcp-config.json"),
    ("opencode", "project", "opencode.json"),
    ("opencode", "user", ".config/opencode/opencode.json"),
    ("cline", "user", ".cline/data/settings/cline_mcp_settings.json"),
]


def _entry(host: str, home: Path, grant: Path) -> dict[str, Any]:
    entry: dict[str, Any]
    if host == "opencode":
        entry = {
            "type": "local",
            "command": ["cairntir-mcp", "--host", host],
            "enabled": True,
        }
    else:
        entry = {"command": "cairntir-mcp", "args": ["--host", host]}
        if host == "copilot":
            entry.update(type="local", tools=["*"])
    entry["env"] = {"CAIRNTIR_HOME": str(home), "CAIRNTIR_GRANT_FILE": str(grant)}
    return entry


def _child(
    mode: str, arguments: list[str], cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("CAIRNTIR_GRANT_FILE", None)
    env.pop("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", None)
    env.update(
        PYTHONPATH=str(ROOT / "src"),
        PYTHONIOENCODING="utf-8",
        CAIRNTIR_DISABLE_AUTOREGISTER="1",
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
    )
    env.update(environment)
    return subprocess.run(  # noqa: S603 - fixed independent helper and disposable stores
        [sys.executable, str(Path(__file__).resolve()), mode, *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=25,
        check=False,
    )


@pytest.mark.parametrize(("host", "scope", "relative_path"), JSON_HOSTS)
def test_nonforce_init_preserves_existing_store_and_grant_environment(
    tmp_path: Path, host: HostName, scope: HostScope, relative_path: str
) -> None:
    project, user = tmp_path / "project", tmp_path / "user"
    target = (user if scope == "user" else project) / relative_path
    target.parent.mkdir(parents=True)
    key = "mcp" if host == "opencode" else "mcpServers"
    expected = {
        "unrelated_preferences": {"keep": "verbatim value"},
        key: {
            "cairntir": _entry(host, tmp_path / "canonical store", tmp_path / "grant.txt"),
            "unrelated": {"command": "other-server", "env": {"DO_NOT_LOSE": "value"}},
        },
    }
    target.write_text(json.dumps(expected), encoding="utf-8")
    configure_host(host, scope=scope, root=project, home=user, install_policy=False)
    actual = json.loads(target.read_text(encoding="utf-8"))
    assert actual[key]["cairntir"].get("env") == expected[key]["cairntir"]["env"]
    assert actual[key]["unrelated"] == expected[key]["unrelated"]
    assert actual["unrelated_preferences"] == expected["unrelated_preferences"]
    assert inspect_host(host, scope=scope, root=project, home=user).mcp_configured is True
    repeated = configure_host(host, scope=scope, root=project, home=user, install_policy=False)
    assert repeated.registration == "unchanged"


def test_nonforce_init_cannot_widen_a_restarted_scoped_connection(tmp_path: Path) -> None:
    home = tmp_path / "canonical-store"
    home.mkdir()
    grant = tmp_path / "reader-grant.txt"
    with DrawerStore(home / "cairntir.db", HashEmbeddingProvider(dimension=32)) as store:
        private = store.add(
            Drawer(wing="private-wing", room="records", content="PRIVATE COUNCIL CANARY")
        )
        token = issue_grant(store, scopes=[{"wing": "allowed-wing"}], capabilities=["read"])
        grant.write_text(token, encoding="utf-8")
    project = tmp_path / "project"
    target = project / ".cursor" / "mcp.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({"mcpServers": {"cairntir": _entry("cursor", home, grant)}}),
        encoding="utf-8",
    )

    def start() -> dict[str, Any]:
        configured = json.loads(target.read_text(encoding="utf-8"))
        environment = {"CAIRNTIR_HOME": str(home)}
        environment.update(configured["mcpServers"]["cairntir"].get("env", {}))
        result = _child("--access", [str(private.id)], project, environment)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    assert start()["denied"] is True
    configure_host("cursor", scope="project", root=project, home=tmp_path / "user")
    restarted = start()
    assert restarted["denied"] is True, restarted
    assert "PRIVATE COUNCIL CANARY" not in json.dumps(restarted)


@pytest.mark.parametrize("override", ["memory", "./memory", "../memory"])
@pytest.mark.parametrize("create", [False, True])
def test_relative_home_override_fails_before_creating_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str, create: bool
) -> None:
    cwd = tmp_path / "host-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("CAIRNTIR_HOME", override)
    before = set(tmp_path.rglob("*"))
    with pytest.raises(ConfigError, match=r"(?i)CAIRNTIR_HOME.*(absolute|relative)"):
        db_path(create=create)
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("create", [False, True])
def test_tilde_home_override_expands_to_platform_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, create: bool
) -> None:
    user = tmp_path / "platform user"
    user.mkdir()
    cwd = tmp_path / "host-cwd"
    cwd.mkdir()
    monkeypatch.setenv("USERPROFILE", str(user))
    monkeypatch.setenv("HOME", str(user))
    monkeypatch.setenv("CAIRNTIR_HOME", "~/council-store")
    monkeypatch.chdir(cwd)
    assert cairntir_home(create=create) == user / "council-store"
    assert db_path(create=False) == user / "council-store" / "cairntir.db"
    assert not (cwd / "~").exists()
    assert (user / "council-store").exists() is create


def test_absolute_store_survives_another_cwd_without_rebrief(tmp_path: Path) -> None:
    origin, receiver = tmp_path / "origin", tmp_path / "receiver"
    origin.mkdir()
    receiver.mkdir()
    home = tmp_path / "canonical store"
    request = tmp_path / "checkpoint.json"
    request.write_text(
        json.dumps(
            {
                "content": REQUEST,
                "checkpoint": {
                    "expected_revision": 0,
                    "idempotency_key": "independent-store-identity",
                    "status": "active",
                    "completed": [],
                    "outstanding": ["verify continuity"],
                    "next_action": "Resume in the receiver",
                    "evidence_ids": [],
                },
            }
        ),
        encoding="utf-8",
    )
    env = {"CAIRNTIR_HOME": str(home)}
    written = _child(
        "--cli",
        ["checkpoint", "council-store", "--room", "requests", "--input", str(request)],
        origin,
        env,
    )
    assert written.returncode == 0, written.stdout + written.stderr
    receipt = json.loads(written.stdout)
    resumed = _child(
        "--cli",
        ["handoff", "council-store", "--resume", "--task-id", receipt["task_id"]],
        receiver,
        env,
    )
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    result = json.loads(resumed.stdout)
    assert result["status"] == "ready" and result["revision"] == 1
    assert result["checkpoint"]["original_request"] == REQUEST
    assert list(tmp_path.rglob("cairntir.db")) == [home / "cairntir.db"]


def test_setup_relative_home_is_absolute_before_host_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cairntir import cli

    class RegistrationBoundaryError(Exception):
        pass

    captured: list[str] = []

    def boundary(*, force: bool) -> None:
        captured.append(os.environ["CAIRNTIR_HOME"])
        raise RegistrationBoundaryError

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAIRNTIR_GRANT_FILE", raising=False)
    monkeypatch.setenv("CAIRNTIR_HOME", str(tmp_path / "initial-store"))
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(cli, "_setup_wire_user_hosts", boundary)
    result = CliRunner().invoke(cli.app, ["setup", "--yes", "--home", "relative-store"])
    assert isinstance(result.exception, RegistrationBoundaryError), result.output
    assert captured == [str(tmp_path / "relative-store")]


if __name__ == "__main__":
    mode = sys.argv.pop(1)
    if mode == "--cli":
        from cairntir import cli

        cli.production_embedding_provider = lambda: HashEmbeddingProvider(dimension=32)
        cli.app()
    elif mode == "--access":
        from cairntir.access import bind_grant, startup_token
        from cairntir.errors import CairntirError
        from cairntir.mcp.backend import CairntirBackend

        with DrawerStore(db_path(), HashEmbeddingProvider(dimension=32)) as owner:
            supplied = startup_token()
            scoped = bind_grant(owner, supplied) if supplied is not None else owner
            try:
                response = CairntirBackend(scoped).get(drawer_id=int(sys.argv[1]))
            except CairntirError as exc:
                print(json.dumps({"denied": True, "error": str(exc)}))
            else:
                print(json.dumps({"denied": False, "drawer": json.loads(response)}))
    else:
        raise SystemExit(f"Unknown independent helper mode: {mode}")
