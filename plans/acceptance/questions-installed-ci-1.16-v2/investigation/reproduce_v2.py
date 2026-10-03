"""Additive directly-owned process variant of the preserved source-only diagnostic."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-questions-work-20261003")
OUT = Path(__file__).resolve().parent
HELPER = ROOT / "plans/acceptance/questions-port-1.16/process/verify_installed_questions.py"
VERIFIER = ROOT / "scripts/verify_package.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run():
    verifier = load("source_verifier", VERIFIER)
    helper = load("frozen_question_helper", HELPER)
    shim = OUT / "shim"
    original_environment = verifier.environment

    def environment(home):
        env = original_environment(home)
        env["PYTHONPATH"] = str(shim) + os.pathsep + str(ROOT / "src")
        return env

    verifier.environment = environment
    events = []

    def state(home):
        return {name: path.stat().st_size for name in (
            "cairntir.db", "cairntir.db-wal", "cairntir.db-shm"
        ) if (path := home / name).exists()}

    class Peer(verifier.Peer):
        async def __aenter__(self):
            self.home.mkdir(parents=True, exist_ok=True)
            self.log = (self.home / "mcp-stderr.txt").open("ab")
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "cairntir.mcp.server", "--host", self.host,
                cwd=self.home, env=self.env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=self.log,
            )
            return self

        async def interrupt(self):
            events.append({"phase": "before_kill", "host": self.host,
                           "pid": self.process.pid, "files": state(self.home)})
            self.process.kill()
            await asyncio.wait_for(self.process.wait(), timeout=10)
            events.append({"phase": "after_kill", "host": self.host,
                           "pid": self.process.pid, "returncode": self.process.returncode,
                           "files": state(self.home)})

    def execute(args, cwd, env, timeout=60):
        if args[0] == "synthetic-cli":
            args = [sys.executable, "-m", "cairntir", *args[1:]]
        return verifier.execute(args, cwd, env, timeout=timeout)

    home = OUT / "home-direct-owned"
    started = time.monotonic()
    receipt = {"source_only": True, "termination": "direct owned TerminateProcess handle",
               "exact_installed_launcher_tree": "not reproduced", "events": events,
               "helper_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest()}
    try:
        receipt["result"] = await helper.verify_installed_questions(
            cli=Path("synthetic-cli"), mcp=Path("synthetic-mcp"), home=home,
            peer_factory=Peer, execute=execute, environment=environment, version="1.16.0",
        )
    except Exception as error:
        receipt["failure"] = {"type": type(error).__name__, "message": str(error),
                              "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                              "sqlite_errorname": getattr(error, "sqlite_errorname", None)}
    receipt["final_files"] = state(home)
    receipt["elapsed"] = time.monotonic() - started
    (OUT / "result-direct-owned.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
