"""Install a built wheel in a disposable environment and exercise actual entrypoints."""

# ruff: noqa: S101 -- this executable verification gate intentionally uses assertions

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST = "  Resume my exact request: café 日本語 🌲\nKeep its evidence and history.\t"
RECALL_QUERY = "Resume the saved request and preserve its supporting evidence and history."


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

    def __init__(self, executable: Path, home: Path, host: str, *, updates: bool = False) -> None:
        """Bind an installed executable to its disposable store."""
        self.executable, self.home, self.host = executable, home, host
        self.next_id = 0
        self.env = environment(home)
        if updates:
            self.env["CAIRNTIR_DISABLE_UPDATE_CHECK"] = "0"

    async def __aenter__(self):
        """Start only the installed MCP console script."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.log = (self.home / "mcp-stderr.txt").open("ab")
        self.process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "--host",
            self.host,
            cwd=self.home,
            env=self.env,
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


def require_recalled_drawer(result: dict, drawer_id: int, content: str) -> None:
    """Require the retrieved evidence itself to contain the exact expected drawer."""
    text = result["content"][0]["text"]
    _, opening, body = text.partition("<cairntir-memory-evidence>\n")
    payload, closing, _ = body.partition("\n</cairntir-memory-evidence>")
    assert opening and closing, "PACKAGE_RECALL: response contains no complete evidence block"
    records = [json.loads(line) for line in payload.splitlines() if line.strip()]
    assert any(
        record["drawer_id"] == drawer_id and record["content"] == content for record in records
    ), "PACKAGE_RECALL: retrieved evidence is missing the exact expected drawer"


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


async def rejected_write_and_retry(peer: Peer) -> None:
    """Require a failed late SQLite write to report failure, roll back and permit retry."""
    database = peer.home / "cairntir.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "CREATE TRIGGER reject_probe BEFORE INSERT ON portable_records "
            "BEGIN SELECT RAISE(ABORT, 'package probe rejected late write'); END"
        )
        connection.commit()
    before = database_contents(database)
    arguments = {
        "wing": "package",
        "room": "retry",
        "content": "Exact memory after a failed write.",
    }
    rejected = await peer.request(
        "tools/call", {"name": "cairntir_remember", "arguments": arguments}
    )
    assert "package probe rejected late write" in rejected["content"][0]["text"], rejected
    assert database_contents(database) == before, "MCP_WRITE: failed write left partial data"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("DROP TRIGGER reject_probe")
        connection.commit()
    await peer.tool("cairntir_remember", **arguments)
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute("SELECT id,content FROM drawers WHERE room='retry'").fetchall()
    assert len(rows) == 1 and rows[0][1] == arguments["content"], rows
    recovered = await peer.json("cairntir_get", drawer_id=rows[0][0])
    assert recovered["content"] == arguments["content"]
    assert rejected.get("isError") is True, "MCP_WRITE: failed write reported success"


async def probe(
    wheel: Path, output: Path, question_proof: Path, question_proof_sha256: str
) -> dict:
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
        await rejected_write_and_retry(second)
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
            "cairntir_recall", query=RECALL_QUERY, wing="package", full_content=5
        )
        require_recalled_drawer(recalled, created["original_drawer_id"], REQUEST)
    (restored_home / ".update_check").write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "999.0.0"}),
        encoding="utf-8",
    )
    async with Peer(mcp, restored_home, "codex", updates=True) as notified:
        await notified.initialize(cairntir.__version__)
        result = await notified.tool("cairntir_get", drawer_id=created["original_drawer_id"])
        assert json.loads(result["content"][0]["text"])["content"] == REQUEST
        assert any("999.0.0" in block["text"] for block in result["content"][1:])
    assert hashlib.sha256(question_proof.read_bytes()).hexdigest() == question_proof_sha256
    specification = importlib.util.spec_from_file_location(
        "frozen_installed_questions", question_proof
    )
    assert specification is not None and specification.loader is not None
    question_module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(question_module)
    question_result = await question_module.verify_installed_questions(
        cli=cli,
        mcp=mcp,
        home=output / "questions",
        peer_factory=Peer,
        execute=execute,
        environment=environment,
        version=cairntir.__version__,
    )
    question_diagnostics = json.loads(
        (output / "questions" / "question-proof-diagnostic.json").read_text(encoding="utf-8")
    )
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
        "failed_write_rollback_and_retry": "PASS",
        "update_notice_preserves_json": "PASS",
        "explicit_question_lifecycle": question_result,
        "explicit_question_diagnostics": question_diagnostics,
        "question_proof_sha256": question_proof_sha256,
    }


def preserve_failed_question_proof(proof: Path, output: Path) -> dict:
    """Retain only this fixture's synthetic files, not a consistent database backup."""
    destination = Path(tempfile.mkdtemp(prefix="failed-question-proof-", dir=output))
    files = {}
    for name in (
        "cairntir.db",
        "cairntir.db-wal",
        "cairntir.db-shm",
        "cairntir.db-journal",
        "question-proof-diagnostic.json",
    ):
        source = proof / name
        if source.is_symlink() or not source.resolve().is_relative_to(proof.resolve()):
            raise OSError(f"Refusing an external fixture diagnostic path: {name}")
        if source.is_file():
            target = destination / name
            shutil.copyfile(source, target)
            files[name] = {
                "bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
    receipt = {
        "directory": str(destination),
        "files": files,
        "synthetic_fixture_only": True,
        "consistent_backup_claimed": False,
    }
    (destination / "manifest.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


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
        proof_directory = ROOT / "plans/acceptance/questions-installed-ci-1.16-v2"
        relative = "verify_installed_questions_v2.py"
        frozen = proof_directory / "FROZEN.json"
        assert hashlib.sha256(frozen.read_bytes()).hexdigest() == (
            "e2bdc7b33901223f38f1460b339ebdf484a73ca743ec7c1ad59dfab44ba0c534"
        )
        proof_hash = json.loads(frozen.read_bytes())["files_sha256"][relative]
        proof_source = proof_directory / relative
        assert hashlib.sha256(proof_source.read_bytes()).hexdigest() == proof_hash
        proof_copy = directory / "question_proof.py"
        shutil.copyfile(proof_source, proof_copy)
        try:
            result = execute(
                [
                    str(python),
                    str(probe_script),
                    "--probe",
                    "--wheel",
                    str(wheel),
                    "--output",
                    str(directory / "proof"),
                    "--question-proof",
                    str(proof_copy),
                    "--question-proof-sha256",
                    proof_hash,
                ],
                directory,
                env,
                timeout=300,
            )
        except (RuntimeError, subprocess.TimeoutExpired) as failure:
            try:
                retained = preserve_failed_question_proof(directory / "proof" / "questions", output)
                failure.add_note("Synthetic question diagnostics: " + json.dumps(retained))
            except OSError as preservation_error:
                failure.add_note(f"Synthetic diagnostic preservation failed: {preservation_error}")
            raise
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
    parser.add_argument("--question-proof", type=Path)
    parser.add_argument("--question-proof-sha256")
    arguments = parser.parse_args()
    wheel_path, output_path = arguments.wheel.resolve(), arguments.output.resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if arguments.probe:
        if arguments.question_proof is None or arguments.question_proof_sha256 is None:
            parser.error("--probe requires a bound --question-proof and --question-proof-sha256")
        result = asyncio.run(
            probe(
                wheel_path,
                output_path,
                arguments.question_proof.resolve(),
                arguments.question_proof_sha256,
            )
        )
    else:
        result = install_and_verify(wheel_path, output_path)
    print(json.dumps(result, indent=2))
