import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant
from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.tasks import TaskBook

from .oracle import PACKET, canonical, digest, read_json
from .synthetic import materialize


def files(root, media=False):
    types = {
        ".html": "text/html",
        ".ttf": "font/ttf",
        ".txt": "text/plain",
        ".svg": "image/svg+xml",
    }
    rows = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file():
            row = {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
            }
            if media:
                row["media_type"] = types[path.suffix]
            rows.append(row)
    return rows


def absolute_file(path):
    return {
        "path": str(path.resolve()),
        "sha256": digest(path.read_bytes()),
        "bytes": path.stat().st_size,
    }


class UIFixture:
    def __init__(self, root, monkeypatch):
        self.root = root.resolve()
        self.root.mkdir()
        self.monkeypatch = monkeypatch
        self.db = self.root / "memory.db"
        self.store = DrawerStore(self.db, HashEmbeddingProvider(32))
        self.baseline_id = str(uuid4())
        self.project_id = "print-notes"
        self.task_id = None
        self.event_id = None
        self.runs = []
        self.calls = []
        self.approved = None
        self.runtime = None
        self.last_sequence = 0
        values = {
            key: str(self.root / "private" / key.lower())
            for key in (
                "HOME",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
                "TEMP",
                "TMP",
                "CAIRNTIR_HOME",
            )
        }
        for value in values.values():
            Path(value).mkdir(parents=True)
        self.environment = {"values": values, "absent": []}
        self.environment_patch = patch.dict(os.environ, values)
        self.environment_patch.start()
        self.tool_root = self.root / "unit-tools"
        self.tool_root.mkdir()
        self.selected_tools = {
            "schema": "cairntir.paladin-ui-tools.v1",
            "tools": [],
            "packaged_chromium_version": "151.0.7922.34",
        }
        for name in (
            "python",
            "node",
            "playwright",
            "playwright-core",
            "chrome",
            "pngjs",
            "pixelmatch",
            "worker",
            "producer",
        ):
            directory = self.tool_root / name
            directory.mkdir()
            entry = directory / "unit-input.txt"
            entry.write_text("SYNTHETIC UNIT INPUT: " + name, encoding="utf-8")
            if name == "python":
                entry = Path(sys.executable).resolve()
                directory = entry.parent
            self.selected_tools["tools"].append(
                {
                    "id": name,
                    "root": str(directory),
                    "entry_path": entry.name,
                    "version": "SYNTHETIC_UNIT_EVIDENCE",
                    "files": [
                        {
                            "path": entry.name,
                            "bytes": entry.stat().st_size,
                            "sha256": digest(entry.read_bytes()),
                        }
                    ],
                }
            )
        self.tools_file = self.root / "selected-tools.json"
        self.tools_file.write_bytes(canonical(self.selected_tools))

    def new_run(self, *, variant="clean", approved=None, fault=None, fresh_task=False):
        if self.runtime is not None:
            self.runtime.close(last_sequence=self.last_sequence)
        root = self.root / ("run-" + str(len(self.runs)))
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()
        shutil.copytree(PACKET / "fixtures/assets", snapshot / "assets")
        shutil.copy2(PACKET / "fixtures" / (variant + ".html"), snapshot / "index.html")
        producer = root / "producer"
        producer.mkdir()
        worker = producer / "worker" / "unit-worker.py"
        worker.parent.mkdir()
        worker.write_text(
            "raise RuntimeError('Unit dispatch must use independent synthetic writer')\n",
            encoding="utf-8",
        )
        unit_node = producer / "node" / "producer.cjs"
        unit_node.parent.mkdir()
        unit_node.write_text(
            'throw Error("Synthetic unit producer is not a native browser tool");\n',
            encoding="utf-8",
        )
        selected_tools = deepcopy(self.selected_tools)
        for name, entry in (("worker", worker), ("producer", unit_node)):
            row = next(tool for tool in selected_tools["tools"] if tool["id"] == name)
            row.update(
                root=str(entry.parent),
                entry_path=entry.name,
                files=[
                    {
                        "path": entry.name,
                        "bytes": entry.stat().st_size,
                        "sha256": digest(entry.read_bytes()),
                    }
                ],
            )
        tools_file = producer / "selected-tools.json"
        tools_file.write_bytes(canonical(selected_tools))
        output = root / "output"
        mode = "compare" if approved is not None else "capture-baseline"
        template = {
            "schema": "cairntir.paladin-ui-producer-template.v1",
            "mode": mode,
            "project": {
                "project_id": self.project_id,
                "route_id": "index",
                "state_id": "initial",
                "source_revision": variant + "-unit-v1",
                "snapshot_root": str(snapshot),
                "snapshot_sha256": digest(canonical(files(snapshot, True))),
                "files": files(snapshot, True),
                "entry_path": "index.html",
            },
            "output_root": str(output),
            "selected_tools": absolute_file(tools_file),
            "render_policy": read_json(PACKET / "RENDER-POLICY.json"),
            "checks": read_json(PACKET / "CHECKS.json"),
            "baseline_reference": None,
        }
        if approved is not None:
            manifest_file = producer / "approved-baseline.json"
            if not manifest_file.exists():
                manifest_file.write_bytes(canonical(approved["manifest"]))
            approved_input = {
                "reference": deepcopy(approved),
                "manifest_file": absolute_file(manifest_file),
            }
            template["baseline_reference"] = {
                "baseline_id": self.baseline_id,
                "generation": approved["head"]["generation"],
                "revision_sha256": approved["head"]["revision_sha256"],
                "approval_id": approved["approval_id"],
                "approval": deepcopy(approved["approval"]),
                "manifest_file": absolute_file(manifest_file),
                "baseline_origin_snapshot_sha256": approved["manifest"]["baseline_origin"][
                    "source"
                ]["snapshot_sha256"],
            }
        else:
            approved_input = None
        template_file = producer / "template.json"
        template_file.write_bytes(canonical(template))
        command = {
            "argv": [
                str(Path(sys.executable).resolve()),
                "-I",
                "-B",
                "-X",
                "pycache_prefix=" + str(output / "runtime/python-cache"),
                str(worker),
                "--request",
                str(output / "request.json"),
                "--template",
                str(template_file),
                "--template-sha256",
                digest(template_file.read_bytes()),
            ],
            "cwd": str(snapshot),
            "timeout_seconds": 150,
            "output_limit_bytes": 65536,
        }
        config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "ui-q04",
            "room": "requests",
            "project_root": str(self.root),
            "brief_budget_chars": 262144,
            "profiles": {"ui_measure": deepcopy(command)},
        }
        if fresh_task:
            saved = json.loads(
                TaskBook(self.store).checkpoint(
                    "ui-q04",
                    "requests",
                    "Fresh authorized project task using an existing reviewed baseline.",
                    {
                        "expected_revision": 0,
                        "idempotency_key": str(uuid4()),
                        "status": "active",
                        "completed": [],
                        "outstanding": ["Compare current UI"],
                        "next_action": "Measure declared current UI",
                        "evidence_ids": [],
                    },
                )
            )
            self.task_id, self.event_id = saved["task_id"], None
            expected_revision = saved["revision"]
        else:
            expected_revision = 0
        runtime = ManagedRuntime(self.store, config=deepcopy(config))
        session = str(uuid4())
        runtime.start(session, task_id=self.task_id)
        self.last_sequence = 0
        if self.event_id is None:
            captured = runtime.capture(
                {
                    "schema": "cairntir.managed-event.v1",
                    "event_id": str(uuid4()),
                    "session_id": session,
                    "sequence": 1,
                    "task_id": self.task_id,
                    "expected_revision": expected_revision,
                    "content": (
                        "Finite Q04 synthetic unit records; no actual browser or model observation."
                    ),
                }
            )
            self.task_id, self.event_id = captured["task_id"], captured["event_id"]
            self.last_sequence = 1
        attempt_id = str(uuid4())
        contract = {
            "schema": "cairntir.paladin-ui-contract.v1",
            "run_id": str(uuid4()),
            "mode": mode,
            "task_id": self.task_id,
            "wing": "ui-q04",
            "room": "requests",
            "baseline_id": self.baseline_id,
            "project_id": self.project_id,
            "route_id": "index",
            "state_id": "initial",
            "producer_root": str(producer),
            "producer_files": files(producer),
            "environment": deepcopy(self.environment),
            "attempts": [
                {
                    "attempt_id": attempt_id,
                    "profile": "ui_measure",
                    "command": deepcopy(command),
                    "template_file": {
                        "path": "template.json",
                        "bytes": template_file.stat().st_size,
                        "sha256": digest(template_file.read_bytes()),
                    },
                    "template": template,
                    "approved_baseline": approved_input,
                }
            ],
        }
        run = {
            "root": root,
            "snapshot": snapshot,
            "producer": producer,
            "output": output,
            "template": template,
            "contract": contract,
            "config": config,
            "runtime": runtime,
            "attempt_id": attempt_id,
            "fault": fault,
            "variant": variant,
        }

        def synthesize(profile):
            self.calls.append(contract["run_id"])
            return materialize(run, selected_tools)

        self.monkeypatch.setattr(runtime, "_run", synthesize)
        self.runs.append(run)
        self.runtime = runtime
        return run

    def action(self, run):
        brief = run["runtime"].brief()
        ack = run["runtime"].acknowledge(
            {
                "schema": "cairntir.managed-ack.v1",
                "brief_id": brief["brief_id"],
                "brief_sha256": brief["brief_sha256"],
            }
        )
        return {
            "schema": "cairntir.managed-action.v1",
            "action_id": str(uuid4()),
            "ack_id": ack["ack_id"],
            "profile": "ui_measure",
            "claim": "Synthetic Q04 unit measurement",
            "predicted_outcome": "Only declared synthetic evidence is evaluated.",
            "event_ids": [self.event_id],
        }

    def scoped(self, capabilities=("read",), rooms=None):
        scope = {"wing": "ui-q04"}
        if rooms is not None:
            scope["rooms"] = rooms
        token = issue_grant(self.store, scopes=[scope], capabilities=list(capabilities))
        return bind_grant(self.store, token), token

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def close(self):
        self.store.close()
        self.environment_patch.stop()
