"""Bounded source-only Windows lifetime diagnosis; no installation or model inference."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
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


async def run(shape):
    verifier = load("source_verifier", VERIFIER)
    helper = load("frozen_question_helper", HELPER)
    shim = OUT / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "sitecustomize.py").write_text(
        "from cairntir.memory import embeddings\n"
        "embeddings.production_embedding_provider = lambda: "
        "embeddings.HashEmbeddingProvider(dimension=16)\n"
        "import cairntir.cli as cli\n"
        "cli.production_embedding_provider = embeddings.production_embedding_provider\n",
        encoding="utf-8",
    )
    launcher = OUT / "launcher.py"
    launcher.write_text(
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "p = subprocess.Popen([sys.executable, '-m', 'cairntir.mcp.server', *sys.argv[1:]])\n"
        "Path('descendant.pid').write_text(str(p.pid))\n"
        "sys.exit(p.wait())\n",
        encoding="utf-8",
    )
    original_environment = verifier.environment

    def environment(home):
        env = original_environment(home)
        env["PYTHONPATH"] = str(shim) + os.pathsep + str(ROOT / "src")
        return env

    verifier.environment = environment
    events = []

    def state(home):
        return {
            name: path.stat().st_size
            for name in ("cairntir.db", "cairntir.db-wal", "cairntir.db-shm")
            if (path := home / name).exists()
        }

    class Peer(verifier.Peer):
        async def __aenter__(self):
            self.home.mkdir(parents=True, exist_ok=True)
            self.log = (self.home / "mcp-stderr.txt").open("ab")
            args = (
                [sys.executable, str(launcher)]
                if shape == "launcher"
                else [sys.executable, "-m", "cairntir.mcp.server"]
            )
            self.process = await asyncio.create_subprocess_exec(
                *args, "--host", self.host, cwd=self.home, env=self.env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.log,
            )
            return self

        async def __aexit__(self, *exc):
            start = time.monotonic()
            events.append({"phase": "before_exit", "host": self.host,
                           "pid": self.process.pid, "files": state(self.home)})
            await super().__aexit__(*exc)
            events.append({"phase": "after_exit", "host": self.host,
                           "pid": self.process.pid, "returncode": self.process.returncode,
                           "elapsed": time.monotonic() - start, "files": state(self.home),
                           "descendant_pid": (self.home / "descendant.pid").read_text()
                           if (self.home / "descendant.pid").exists() else None})

    def execute(args, cwd, env, timeout=60):
        if args[0] == "synthetic-cli":
            args = [sys.executable, "-m", "cairntir", *args[1:]]
        return verifier.execute(args, cwd, env, timeout=timeout)

    home = OUT / ("home-" + shape)
    started = time.monotonic()
    receipt = {"shape": shape, "source_only": True, "events": events,
               "helper_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
               "verifier_sha256": hashlib.sha256(VERIFIER.read_bytes()).hexdigest()}
    try:
        receipt["result"] = await helper.verify_installed_questions(
            cli=Path("synthetic-cli"), mcp=Path("synthetic-mcp"), home=home,
            peer_factory=Peer, execute=execute, environment=environment, version="1.16.0",
        )
    except Exception as error:
        receipt["failure"] = {"type": type(error).__name__, "message": str(error),
                              "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                              "sqlite_errorname": getattr(error, "sqlite_errorname", None)}
        # Separate post-failure diagnostic, never converted into a helper PASS.
        try:
            receipt["post_failure_physical_snapshot"] = verifier.database_contents(home / "cairntir.db")
        except Exception as recovery:
            receipt["post_failure_physical_error"] = {
                "type": type(recovery).__name__, "message": str(recovery),
                "sqlite_errorcode": getattr(recovery, "sqlite_errorcode", None),
                "sqlite_errorname": getattr(recovery, "sqlite_errorname", None),
            }
    receipt["final_files"] = state(home)
    receipt["elapsed"] = time.monotonic() - started
    (OUT / ("result-" + shape + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
