"""Install a built wheel in a disposable environment and exercise actual entrypoints."""

# ruff: noqa: S101 -- this executable verification gate intentionally uses assertions

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST = "  Resume my exact request: café 日本語 🌲\nKeep its evidence and history.\t"


def execute(args: list[str], cwd: Path, env: dict[str, str], timeout: int = 180) -> str:
    """Execute one bounded command and require a successful exit."""
    result = subprocess.run(  # noqa: S603 - explicit package verification commands
        args,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {args}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def environment(home: Path) -> dict[str, str]:
    """Give package processes a disposable store and disable registration and network hooks."""
    env = dict(os.environ)
    for key in ("PYTHONPATH", "CAIRNTIR_GRANT_FILE", "CAIRNTIR_ENABLE_EMBEDDER_WARMUP"):
        env.pop(key, None)
    env.update(
        CAIRNTIR_HOME=str(home),
        CAIRNTIR_DISABLE_AUTOREGISTER="1",
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    return env


class Peer:
    """A real stdio JSON-RPC client with bounded reads and explicit process interruption."""

    def __init__(self, executable: Path, home: Path, host: str) -> None:
        """Bind an installed executable to its disposable store."""
        self.executable, self.home, self.host = executable, home, host
        self.next_id = 0

    async def __aenter__(self):
        """Start only the installed MCP console script."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.log = (self.home / "mcp-stderr.txt").open("ab")
        self.process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "--host",
            self.host,
            cwd=self.home,
            env=environment(self.home),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=self.log,
        )
        return self

    async def __aexit__(self, *_):
        """Close the owned child, including on failed assertions."""
        if self.process.returncode is None:
            await self.interrupt()
        await asyncio.wait_for(self.process.wait(), timeout=10)
        self.log.close()

    async def interrupt(self) -> None:
        """Interrupt this test's MCP process, including the Windows launcher child."""
        if os.name == "nt":
            taskkill = shutil.which("taskkill")
            if taskkill is None:
                raise RuntimeError("taskkill is required for the Windows interruption test")
            execute(
                [taskkill, "/PID", str(self.process.pid), "/T", "/F"],
                self.home,
                environment(self.home),
                timeout=15,
            )
        else:
            self.process.kill()
        await asyncio.wait_for(self.process.wait(), timeout=10)

    async def request(self, method: str, params: dict) -> dict:
        """Wait for this request's response while permitting protocol notifications."""
        self.next_id += 1
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(
            (
                json.dumps(
                    {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
                )
                + "\n"
            ).encode()
        )
        await self.process.stdin.drain()
        async with asyncio.timeout(90):
            while True:
                line = await self.process.stdout.readline()
                assert line, (self.home / "mcp-stderr.txt").read_text(encoding="utf-8")
                response = json.loads(line)
                if response.get("id") == self.next_id:
                    assert "result" in response, response
                    return response["result"]

    async def initialize(self, version: str) -> None:
        """Check the installed version through the actual MCP handshake."""
        result = await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "package-verifier", "version": "1"},
            },
        )
        assert result["serverInfo"]["version"] == version
        assert self.process.stdin is not None
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await self.process.stdin.drain()

    async def tool(self, name: str, **arguments) -> dict:
        """Require success from the tool, not merely its JSON-RPC transport."""
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        assert not result.get("isError"), result
        return result

    async def json(self, name: str, **arguments) -> dict:
        """Decode a tool's documented JSON response."""
        return json.loads((await self.tool(name, **arguments))["content"][0]["text"])


def database_contents(database: Path) -> str:
    """Read physical SQLite tables independently of Cairntir's restore logic."""
    import sqlite_vec

    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        schema = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        tables = {}
        for kind, name, *_ in schema:
            if kind == "table":
                quoted = name.replace('"', '""')
                query = f'SELECT * FROM "{quoted}"'  # noqa: S608 - quoted SQLite table identifiers
                tables[name] = sorted(connection.execute(query).fetchall(), key=repr)
        return repr((schema, tables, connection.execute("PRAGMA user_version").fetchone()))


async def probe(wheel: Path, output: Path) -> dict:
    """Exercise this installed wheel through CLI, MCP, interruption and restoration."""
    import cairntir

    package = Path(cairntir.__file__).resolve().parent
    assert package.is_relative_to(Path(sys.prefix).resolve()), package
    assert not package.is_relative_to(ROOT / "src")
    with zipfile.ZipFile(wheel) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.startswith("cairntir/") and not name.endswith("/")
        ]
        for name in members:
            assert (package.parent / name).read_bytes() == archive.read(name), name
    binaries = Path(sys.executable).parent
    suffix = ".exe" if os.name == "nt" else ""
    cli, mcp = binaries / f"cairntir{suffix}", binaries / f"cairntir-mcp{suffix}"
    home = output / "owner"
    home.mkdir()

    def call(*args: str) -> str:
        return execute([str(cli), *args], home, environment(home))

    assert cairntir.__version__ in call("version")
    assert "checkpoint" in call("--help")
    state = {
        "expected_revision": 0,
        "idempotency_key": "installed-request",
        "status": "active",
        "completed": [],
        "outstanding": ["finish without rebriefing"],
        "next_action": "Continue the saved request.",
        "evidence_ids": [],
    }
    async with Peer(mcp, home, "codex") as first:
        await first.initialize(cairntir.__version__)
        tools = (await first.request("tools/list", {}))["tools"]
        assert len(tools) == len({tool["name"] for tool in tools}) == 21
        assert all(tool["inputSchema"].get("type") == "object" for tool in tools)
        created = await first.json(
            "cairntir_remember",
            wing="package",
            room="tasks",
            content=REQUEST,
            model="package-verifier",
            checkpoint=state,
        )
        assert created["revision"] == 1
        await first.interrupt()
    async with Peer(mcp, home, "claude-code") as second:
        await second.initialize(cairntir.__version__)
        resumed = await second.json(
            "cairntir_handoff", wing="package", resume=True, task_id=created["task_id"]
        )
        assert resumed["checkpoint"]["original_request"] == REQUEST
        assert resumed["checkpoint"]["outstanding"] == ["finish without rebriefing"]
        state.update(
            task_id=created["task_id"],
            expected_revision=1,
            idempotency_key="installed-progress",
            completed=["resumed in another host"],
            evidence_ids=[created["original_drawer_id"]],
        )
        payload = home / "progress.json"
        payload.write_text(
            json.dumps(
                {
                    "content": "Continue from this exact progress.",
                    "model": "package-verifier",
                    "checkpoint": state,
                }
            ),
            encoding="utf-8",
        )
        advanced = json.loads(
            call("checkpoint", "package", "--room", "tasks", "--input", str(payload))
        )
        assert advanced["revision"] == 2 and not advanced["replayed"]
        replay = json.loads(
            call("checkpoint", "package", "--room", "tasks", "--input", str(payload))
        )
        assert replay == advanced | {"replayed": True}
        expected = await second.json(
            "cairntir_handoff", wing="package", resume=True, task_id=created["task_id"]
        )
        assert expected["revision"] == 2
        call("backup", "configure", str(output / "backups"))
        before = database_contents(home / "cairntir.db")
        snapshot = json.loads(call("backup", "run"))
        assert snapshot["status"] == "created"
        path = Path(snapshot["snapshot"]["path"])
        assert database_contents(path) == before
        assert database_contents(home / "cairntir.db") == before
    restored_home = output / "restored"
    restored_home.mkdir()
    shutil.copyfile(path, restored_home / "cairntir.db")
    async with Peer(mcp, restored_home, "codex") as restored:
        await restored.initialize(cairntir.__version__)
        assert (
            await restored.json(
                "cairntir_handoff", wing="package", resume=True, task_id=created["task_id"]
            )
            == expected
        )
        assert database_contents(restored_home / "cairntir.db") == before
        recalled = await restored.tool(
            "cairntir_recall", query=REQUEST, wing="package", full_content=5
        )
        assert "café 日本語 🌲" in json.dumps(recalled, ensure_ascii=False)
    return {
        "version": cairntir.__version__,
        "package_files": len(members),
        "mcp_tools": len(tools),
        "installed_module": str(package),
        "cli_and_mcp": "PASS",
        "abrupt_host_resumption": "PASS",
        "checkpoint_revision": 2,
        "all_table_restoration": "PASS",
        "restored_semantic_recall": "PASS",
    }


def install_and_verify(wheel: Path, output: Path) -> dict:
    """Install only into a new environment using the repository's locked runtime requirements."""
    output.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to install the package under verification")
    with tempfile.TemporaryDirectory(prefix="installed-", dir=output) as temporary:
        directory = Path(temporary)
        env = environment(directory / "home")
        requirements = directory / "requirements.txt"
        execute(
            [
                uv,
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            ROOT,
            env,
        )
        (output / "requirements.txt").write_text(
            requirements.read_text(encoding="utf-8"), encoding="utf-8"
        )
        venv = directory / "venv"
        execute([uv, "venv", "--python", sys.executable, str(venv)], directory, env)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        execute(
            [
                uv,
                "pip",
                "install",
                "--link-mode",
                "copy",
                "--python",
                str(python),
                "-r",
                str(requirements),
                str(wheel),
            ],
            directory,
            env,
        )
        probe_script = directory / "verify_package.py"
        shutil.copyfile(Path(__file__), probe_script)
        result = execute(
            [
                str(python),
                str(probe_script),
                "--probe",
                "--wheel",
                str(wheel),
                "--output",
                str(directory / "proof"),
            ],
            directory,
            env,
            timeout=300,
        )
        receipt = json.loads(result)
        receipt.update(
            wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
            requirements_sha256=hashlib.sha256(requirements.read_bytes()).hexdigest(),
        )
        (output / "package.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    arguments = parser.parse_args()
    wheel_path, output_path = arguments.wheel.resolve(), arguments.output.resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    result = (
        asyncio.run(probe(wheel_path, output_path))
        if arguments.probe
        else install_and_verify(wheel_path, output_path)
    )
    print(json.dumps(result, indent=2))
