"""Public isolated driver for real managed-runtime process/crash/concurrency probes."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def wait(path):
    deadline = time.monotonic() + 25
    while not Path(path).exists():
        if time.monotonic() > deadline:
            raise TimeoutError("independent driver barrier not released")
        time.sleep(0.02)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("name")
    parser.add_argument("mode", choices=["run", "before-spawn", "recover", "outcome-fault"])
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    root = Path(args.plan).parent
    with DrawerStore(Path(plan["database"]), HashEmbeddingProvider(32)) as store:
        runtime = ManagedRuntime(store, config=plan["config"])
        started = runtime.start(plan["session_id"], task_id=plan["task_id"])
        if args.mode == "recover":
            previous = json.loads((root / "action.json").read_text(encoding="utf-8"))
            write(
                root / (args.name + ".json"),
                {
                    "start": started,
                    "status": runtime.status(plan["action_id"]),
                    "replay": runtime.dispatch(previous),
                },
            )
            return
        ack = runtime.acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": started["brief_id"],
                "brief_sha256": started["brief_sha256"],
            }
        )
        action = {
            "schema": "cairntir.managed-action.v1",
            "action_id": plan["action_id"],
            "ack_id": ack["ack_id"],
            "profile": "check",
            "claim": "  The child sees committed intent café\r\n",
            "predicted_outcome": "The child verifies committed prediction before its marker.",
            "event_ids": [plan["event_id"]],
        }
        write(root / (args.name + ".ready.json"), action)
        if args.name == "primary":
            write(root / "action.json", action)
        wait(root / "dispatch.release")
        original_popen = subprocess.Popen
        original_execute = store.execute_once

        def spawn(argv, *positional, **keywords):
            if (
                args.mode == "before-spawn"
                and list(argv) == plan["config"]["profiles"]["check"]["argv"]
            ):
                write(root / "before-spawn.json", {"argv": list(argv), "witness": True})
                wait(root / "spawn.release")
            return original_popen(argv, *positional, **keywords)

        def execute(**kwargs):
            if args.mode == "outcome-fault" and kwargs.get("operation") == "managed.outcome.v1":
                from cairntir.errors import MemoryStoreError

                write(root / "outcome-fault.json", {"witness": True})
                raise MemoryStoreError("independent post-effect outcome persistence failure")
            return original_execute(**kwargs)

        try:
            with (
                patch("subprocess.Popen", side_effect=spawn),
                patch.object(store, "execute_once", side_effect=execute),
            ):
                result = runtime.dispatch(action)
            write(root / (args.name + ".json"), {"result": result})
        except ManagedRuntimeError as exc:
            write(root / (args.name + ".json"), {"error": str(exc)})


if __name__ == "__main__":
    main()
