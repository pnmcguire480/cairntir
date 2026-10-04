"""Independent actual CLI check for post-ack configuration replacement."""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import unittest
from copy import deepcopy
from pathlib import Path

import test_managed_process


class ManagedConfigurationAcceptance(unittest.TestCase):
    def test_cli_changed_config_cannot_launch_using_previous_ack(self):
        fixture = test_managed_process.ManagedProcessAcceptance()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cache = os.environ.get("MANAGED_ACCEPTANCE_MODEL_CACHE")
        self.assertTrue(cache and Path(cache).is_dir(), "qualified offline cache is required")
        copied_cache = fixture.root / "cli-cache"
        shutil.copytree(cache, copied_cache)
        home = fixture.root / "cli-home"
        home.mkdir()
        config = deepcopy(fixture.config)
        config["profiles"]["check"]["argv"] = fixture.argv(home / "cairntir.db")
        path = fixture.root / "cli-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        log = (fixture.root / "cli.stderr").open("w", encoding="utf-8")
        fixture.handles.append(log)
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "cairntir",
                "managed",
                "--config",
                str(path),
                "--session-id",
                fixture.session,
            ],
            cwd=fixture.project,
            env={
                **fixture.environment(),
                "CAIRNTIR_HOME": str(home),
                "FASTEMBED_CACHE_PATH": str(copied_cache),
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        fixture.processes.append(process)
        fixture.handles.extend([process.stdin, process.stdout])
        replies = queue.Queue()

        def read_lines():
            for line in process.stdout:
                replies.put(line)

        threading.Thread(target=read_lines, daemon=True).start()

        def reply():
            return json.loads(replies.get(timeout=30))

        def command(operation, request):
            process.stdin.write(
                json.dumps(
                    {
                        "schema": "cairntir.managed-command.v1",
                        "operation": operation,
                        "request": request,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            process.stdin.flush()
            return reply()

        self.assertEqual(reply()["status"], "none")
        captured = command("capture", fixture.event())
        self.assertEqual(captured["status"], "committed")
        brief = command("brief", {})
        ack = command(
            "acknowledge",
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            },
        )
        self.assertEqual(ack["status"], "committed")
        config["profiles"]["check"]["output_limit_bytes"] -= 1
        path.write_text(json.dumps(config), encoding="utf-8")
        fixture.release.touch()
        result = command(
            "dispatch",
            {
                "schema": "cairntir.managed-action.v1",
                "action_id": fixture.action_id,
                "ack_id": ack["ack_id"],
                "profile": "check",
                "claim": "A replaced configuration must invalidate readiness",
                "predicted_outcome": "No child is launched",
                "event_ids": [captured["event_id"]],
            },
        )
        self.assertEqual(result["schema"], "cairntir.managed-error.v1")
        self.assertEqual(result["status"], "error")
        self.assertEqual(fixture.markers(), [])
        process.stdin.close()
        self.assertNotEqual(process.wait(timeout=15), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
