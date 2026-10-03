"""Independent real-process witnesses for managed dispatch and crash recovery."""

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant
from cairntir.managed import ManagedRuntime, ManagedRuntimeError
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

PACKET = Path(__file__).resolve().parent


class ManagedProcessAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.database = self.root / "memory.db"
        self.marker = self.root / "external-marker.jsonl"
        self.release = self.root / "child.release"
        self.done = self.root / "child.done"
        self.action_id = str(uuid4())
        self.session = str(uuid4())
        self.processes = []
        self.handles = []
        self.addCleanup(self.cleanup_processes)
        self.config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "managed",
            "room": "requests",
            "project_root": str(self.project),
            "brief_budget_chars": 16384,
            "profiles": {
                "check": {
                    "argv": self.argv(self.database),
                    "cwd": str(self.project),
                    "timeout_seconds": 30,
                    "output_limit_bytes": 4096,
                }
            },
        }
        with DrawerStore(self.database, HashEmbeddingProvider(32)) as store:
            runtime = ManagedRuntime(store, config=self.config)
            runtime.start(self.session)
            receipt = runtime.capture(self.event())
        self.plan = {
            "database": str(self.database),
            "config": self.config,
            "session_id": self.session,
            "task_id": receipt["task_id"],
            "event_id": receipt["event_id"],
            "action_id": self.action_id,
        }
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")

    def argv(self, database):
        return [
            sys.executable,
            "-X",
            "utf8",
            str(PACKET / "process_child.py"),
            "--database",
            str(database),
            "--action-id",
            self.action_id,
            "--marker",
            str(self.marker),
            "--release",
            str(self.release),
            "--done",
            str(self.done),
        ]

    def event(self):
        return {
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()),
            "session_id": self.session,
            "sequence": 1,
            "task_id": None,
            "expected_revision": 0,
            "content": "  Actual process commitment café 🧭\r\n",
        }

    def environment(self):
        return {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CAIRNTIR_HOME": str(self.root / "home"),
            "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
            "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
            "HF_HUB_OFFLINE": "1",
        }

    def cleanup_processes(self):
        for name in ("child.release", "dispatch.release", "spawn.release"):
            (self.root / name).write_text("release", encoding="utf-8")
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        if self.marker.exists():
            deadline = time.monotonic() + 5
            while not self.done.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
        for stream in self.handles:
            stream.close()

    def launch(self, name="primary", mode="run"):
        log = (self.root / (name + ".log")).open("w", encoding="utf-8")
        self.handles.append(log)
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                str(PACKET / "process_driver.py"),
                str(self.plan_path),
                name,
                mode,
            ],
            cwd=self.project,
            env=self.environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.processes.append(process)
        return process

    def wait_file(self, path, process=None):
        deadline = time.monotonic() + 15
        while not path.exists():
            if process is not None and process.poll() is not None:
                self.fail(
                    f"driver exited before witness {path.name}: {list(self.root.glob('*.log'))}"
                )
            if time.monotonic() >= deadline:
                self.fail(f"missing process witness: {path.name}")
            time.sleep(0.02)

    def finish(self, process, name):
        self.assertEqual(
            process.wait(timeout=20), 0, (self.root / (name + ".log")).read_text(encoding="utf-8")
        )
        return json.loads((self.root / (name + ".json")).read_text(encoding="utf-8"))

    def markers(self):
        return (
            [json.loads(line) for line in self.marker.read_text(encoding="utf-8").splitlines()]
            if self.marker.exists()
            else []
        )

    def intent(self):
        with closing(sqlite3.connect(self.database)) as conn:
            values = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT result FROM workflow_runs WHERE operation='managed.dispatch.v1' AND state='committed'"
                )
            ]
        return [value for value in values if value["action_id"] == self.action_id]

    def assert_uncertain_recovery(self, expected_markers):
        recovery = self.launch("recovery", "recover")
        result = self.finish(recovery, "recovery")
        for key in ("status", "replay"):
            self.assertEqual(result[key]["status"], "uncertain")
            self.assertIsNone(result[key]["outcome_drawer_id"])
            self.assertIsNone(result[key]["exit_code"])
        self.assertIs(result["replay"]["replayed"], True)
        self.assertEqual(len(self.markers()), expected_markers)
        self.assertEqual(len(self.intent()), 1)
        self.assertTrue(
            any(
                item["action_id"] == self.action_id for item in result["start"]["uncertain_actions"]
            )
        )

    def test_actual_child_observes_commit_before_effect_and_completed_retry_does_not_launch(self):
        self.release.touch()
        (self.root / "dispatch.release").touch()
        process = self.launch()
        receipt = self.finish(process, "primary")["result"]
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertIn("actual child café 🧭", receipt["stdout"])
        markers = self.markers()
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["prediction_drawer_id"], receipt["prediction_drawer_id"])
        self.assertEqual(
            self.intent()[0]["request"],
            json.loads((self.root / "action.json").read_text(encoding="utf-8")),
        )
        recovery = self.launch("recovery", "recover")
        replay = self.finish(recovery, "recovery")["replay"]
        self.assertEqual(replay, {**receipt, "replayed": True})
        self.assertEqual(len(self.markers()), 1)

    def test_kill_after_committed_intent_before_spawn_stays_uncertain_without_replay(self):
        (self.root / "dispatch.release").touch()
        process = self.launch(mode="before-spawn")
        self.wait_file(self.root / "before-spawn.json", process)
        self.assertEqual(
            len(self.intent()), 1, "intent is not independently committed before Popen"
        )
        self.assertEqual(self.markers(), [])
        process.kill()
        process.wait(timeout=10)
        self.assert_uncertain_recovery(0)

    def test_kill_after_external_effect_preserves_prediction_and_never_relaunches(self):
        (self.root / "dispatch.release").touch()
        process = self.launch()
        self.wait_file(self.marker, process)
        self.assertEqual(len(self.intent()), 1)
        process.kill()
        process.wait(timeout=10)
        self.release.touch()
        self.wait_file(self.done)
        self.assert_uncertain_recovery(1)

    def test_outcome_persistence_fault_is_witnessed_and_never_repeats_effect(self):
        self.release.touch()
        (self.root / "dispatch.release").touch()
        process = self.launch(mode="outcome-fault")
        result = self.finish(process, "primary")
        self.assertTrue(
            (self.root / "outcome-fault.json").exists(), "post-effect fault was not reached"
        )
        self.assertTrue("error" in result or result["result"]["status"] == "uncertain")
        self.assertEqual(len(self.markers()), 1)
        self.assert_uncertain_recovery(1)

    def test_two_authorized_processes_racing_same_action_id_launch_once(self):
        self.release.touch()
        first = self.launch("primary")
        second = self.launch("competitor")
        self.wait_file(self.root / "primary.ready.json", first)
        self.wait_file(self.root / "competitor.ready.json", second)
        (self.root / "dispatch.release").touch()
        outcomes = [self.finish(first, "primary"), self.finish(second, "competitor")]
        self.assertEqual(
            sum(value.get("result", {}).get("status") == "completed" for value in outcomes), 1
        )
        self.assertEqual(sum("error" in value for value in outcomes), 1)
        self.assertEqual(len(self.markers()), 1)
        self.assertEqual(len(self.intent()), 1)

    def check_outer_transaction(self, scoped):
        self.release.touch()
        with DrawerStore(self.database, HashEmbeddingProvider(32)) as store:
            target = store
            if scoped:
                token = issue_grant(
                    store, scopes=[{"wing": "managed"}], capabilities=["read", "write"]
                )
                target = bind_grant(store, token)
            runtime = ManagedRuntime(target, config=self.config)
            brief = runtime.start(self.session, task_id=self.plan["task_id"])
            ack = runtime.acknowledge(
                {
                    "schema": "cairntir.managed-ack.v1",
                    "brief_id": brief["brief_id"],
                    "brief_sha256": brief["brief_sha256"],
                }
            )
            action = {
                "schema": "cairntir.managed-action.v1",
                "action_id": self.action_id,
                "ack_id": ack["ack_id"],
                "profile": "check",
                "claim": "Outer transaction must refuse launch",
                "predicted_outcome": "Child runs only after a real outer commit",
                "event_ids": [self.plan["event_id"]],
            }
            with (
                target.transaction(),
                patch(
                    "subprocess.Popen", side_effect=AssertionError("launch inside transaction")
                ) as spawn,
            ):
                with self.assertRaises(ManagedRuntimeError):
                    runtime.dispatch(action)
                spawn.assert_not_called()
            self.assertEqual(self.markers(), [])
            self.assertEqual(self.intent(), [])
            self.assertEqual(
                runtime.dispatch(action)["status"],
                "completed",
                "positive authority control outside caller transaction",
            )
        self.assertEqual(len(self.markers()), 1)

    def test_owner_outer_transaction_cannot_fake_preaction_commit(self):
        self.check_outer_transaction(False)

    def test_scoped_outer_transaction_cannot_fake_preaction_commit(self):
        self.check_outer_transaction(True)

    def test_changed_executable_cannot_use_previous_acknowledgement(self):
        executable = self.project / Path(sys.executable).name
        shutil.copyfile(sys.executable, executable)
        config = deepcopy(self.config)
        config["profiles"]["check"]["argv"][0] = str(executable)
        with DrawerStore(self.database, HashEmbeddingProvider(32)) as store:
            runtime = ManagedRuntime(store, config=config)
            brief = runtime.start(self.session, task_id=self.plan["task_id"])
            ack = runtime.acknowledge(
                {
                    "schema": "cairntir.managed-ack.v1",
                    "brief_id": brief["brief_id"],
                    "brief_sha256": brief["brief_sha256"],
                }
            )
            with executable.open("ab") as stream:
                stream.write(b"synthetic artifact change")
            action = {
                "schema": "cairntir.managed-action.v1",
                "action_id": self.action_id,
                "ack_id": ack["ack_id"],
                "profile": "check",
                "claim": "Changed executable must refuse launch",
                "predicted_outcome": "No process exists",
                "event_ids": [self.plan["event_id"]],
            }
            with patch(
                "subprocess.Popen", side_effect=AssertionError("changed executable")
            ) as spawn:
                with self.assertRaises(ManagedRuntimeError):
                    runtime.dispatch(action)
                spawn.assert_not_called()
        self.assertEqual(self.intent(), [])
        self.assertEqual(self.markers(), [])

    def test_unsafe_profile_configuration_is_rejected_before_launch(self):
        invalid = [
            {"argv": "python -c anything"},
            {"argv": ["relative-python"]},
            {"cwd": str(self.root)},
            {"timeout_seconds": True},
            {"timeout_seconds": 301},
            {"output_limit_bytes": 0},
            {"shell": True},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                config = deepcopy(self.config)
                config["profiles"]["check"].update(changes)
                with (
                    DrawerStore(self.database, HashEmbeddingProvider(32)) as store,
                    patch(
                        "subprocess.Popen", side_effect=AssertionError("unsafe configuration")
                    ) as spawn,
                ):
                    with self.assertRaises(ManagedRuntimeError):
                        ManagedRuntime(store, config=config).start(
                            self.session, task_id=self.plan["task_id"]
                        )
                    spawn.assert_not_called()
        self.assertEqual(self.intent(), [])
        self.assertEqual(self.markers(), [])

    def test_real_cli_jsonl_start_capture_brief_ack_dispatch_close(self):
        cache = os.environ.get("MANAGED_ACCEPTANCE_MODEL_CACHE")
        self.assertTrue(
            cache and Path(cache).is_dir(),
            "set MANAGED_ACCEPTANCE_MODEL_CACHE to the qualified cached model; no downloads or skipped CLI proof",
        )
        copied_cache = self.root / "cli-cache"
        shutil.copytree(cache, copied_cache)
        home = self.root / "cli-home"
        home.mkdir()
        config = deepcopy(self.config)
        config["profiles"]["check"]["argv"] = self.argv(home / "cairntir.db")
        path = self.root / "cli-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        env = {
            **self.environment(),
            "CAIRNTIR_HOME": str(home),
            "FASTEMBED_CACHE_PATH": str(copied_cache),
        }
        log = (self.root / "cli.stderr").open("w", encoding="utf-8")
        self.handles.append(log)
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
                self.session,
            ],
            cwd=self.project,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.processes.append(process)
        self.handles.extend([process.stdin, process.stdout])
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
        captured = command("capture", self.event())
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
        self.release.touch()
        outcome = command(
            "dispatch",
            {
                "schema": "cairntir.managed-action.v1",
                "action_id": self.action_id,
                "ack_id": ack["ack_id"],
                "profile": "check",
                "claim": "Normal CLI child observes a committed prediction",
                "predicted_outcome": "Child verifies then writes its external marker",
                "event_ids": [captured["event_id"]],
            },
        )
        self.assertEqual(outcome["status"], "completed")
        closed = command("close", {"last_sequence": 1})
        self.assertEqual(closed["status"], "closed")
        self.assertIs(closed["capture_complete"], True)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=15), 0)
        self.assertEqual(len(self.markers()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
