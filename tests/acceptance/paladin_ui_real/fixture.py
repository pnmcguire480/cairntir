"""Real-browser Q04 runs: actual worker, producer, Node and prepared Chromium."""

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from tests.acceptance.paladin_ui_unit.fixture import UIFixture, absolute_file, files
from tests.acceptance.paladin_ui_unit.oracle import PACKET, canonical, digest, read_json

from cairntir.managed import ManagedRuntime

SOURCE = Path(__file__).resolve().parents[3] / "src" / "cairntir"
CHROMIUM = "151.0.7922.34"
TOOLS_VARIABLE = "CAIRNTIR_Q04_TOOLS"


def prepared_root():
    """Return the prepared tools folder, or None when it is not configured."""
    value = os.environ.get(TOOLS_VARIABLE)
    return Path(value).resolve() if value else None


def _rows(root, names=None):
    root = Path(root)
    paths = (
        [root / name for name in names]
        if names is not None
        else [path for path in root.rglob("*") if path.is_file()]
    )
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()),
        }
        for path in paths
    ]
    return sorted(rows, key=lambda row: row["path"])


def _package(root):
    return json.loads((Path(root) / "package.json").read_text(encoding="utf-8"))["version"]


def real_tools(prepared):
    """Bind every prepared external tool by exact bytes and observed version."""
    modules = prepared / "node_modules"
    chrome = next((prepared / "browsers").glob("chromium-*/chrome-win64/chrome.exe"), None)
    if chrome is None:
        chrome = next((prepared / "browsers").glob("chromium-*/chrome-linux*/chrome"))
    node = Path(shutil.which("node")).resolve()
    node_version = subprocess.run(  # noqa: S603 - resolved Node, fixed argv
        [str(node), "-p", "process.versions.node"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    python = Path(sys.executable).resolve()
    rows = []

    def add(name, root, entry, version, names=None):
        rows.append(
            {
                "id": name,
                "root": str(Path(root).resolve()),
                "entry_path": entry,
                "version": version,
                "files": _rows(root, names),
            }
        )

    add(
        "python",
        python.parent,
        python.name,
        ".".join(map(str, sys.version_info[:3])),
        [python.name],
    )
    add("node", node.parent, node.name, node_version, [node.name])
    for name, entry in (
        ("playwright", "index.js"),
        ("playwright-core", "index.js"),
        ("pngjs", "lib/png.js"),
        ("pixelmatch", "index.js"),
    ):
        add(name, modules / name, entry, _package(modules / name))
    add("chrome", chrome.parent, chrome.name, CHROMIUM)
    return rows


class RealUIFixture(UIFixture):
    """The frozen unit fixture's store and scope, with no synthetic dispatch."""

    def __init__(self, root, monkeypatch, prepared):
        super().__init__(root, monkeypatch)
        self.external_tools = real_tools(prepared)

    def new_run(self, *, variant="clean", approved=None, fresh_task=False):
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
        worker = producer / "worker" / "_paladin_ui_worker.py"
        node_producer = producer / "node" / "_paladin_ui_producer.cjs"
        for source, target in (
            (SOURCE / worker.name, worker),
            (SOURCE / node_producer.name, node_producer),
        ):
            target.parent.mkdir()
            shutil.copy2(source, target)
        tools = deepcopy(self.external_tools)
        for name, entry in (("worker", worker), ("producer", node_producer)):
            tools.append(
                {
                    "id": name,
                    "root": str(entry.parent),
                    "entry_path": entry.name,
                    "version": "1",
                    "files": _rows(entry.parent, [entry.name]),
                }
            )
        selected = {
            "schema": "cairntir.paladin-ui-tools.v1",
            "tools": tools,
            "packaged_chromium_version": CHROMIUM,
        }
        tools_file = producer / "selected-tools.json"
        tools_file.write_bytes(canonical(selected))
        output = root / "output"
        mode = "compare" if approved is not None else "capture-baseline"
        template = {
            "schema": "cairntir.paladin-ui-producer-template.v1",
            "mode": mode,
            "project": {
                "project_id": self.project_id,
                "route_id": "index",
                "state_id": "initial",
                "source_revision": variant + "-real-v1",
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
        approved_input = None
        if approved is not None:
            manifest_file = producer / "approved-baseline.json"
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
        expected_revision = 0
        if fresh_task:
            from cairntir.tasks import TaskBook

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
                    "content": "Q04 real-browser run of a frozen UI fixture.",
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
            "variant": variant,
        }
        self.runs.append(run)
        self.runtime = runtime
        return run

    def action(self, run):
        action = super().action(run)
        action["claim"] = "Q04 real-browser measurement"
        action["predicted_outcome"] = "The frozen oracle agrees with the browser report."
        return action


def review_artifact(fixture, bundle, expected, decision):
    """Write one exact review artifact and the callback that checks its binding."""
    manifest = bundle["manifest"]
    assert digest(canonical(manifest)) == bundle["manifest_sha256"]
    images = [
        {"role": role, "viewport_id": row["viewport_id"], **row[role]}
        for row in manifest["images"]
        for role in ("current", "previous", "diff")
        if row[role] is not None
    ]
    review_id = str(uuid4())
    value = {
        "schema": "cairntir.paladin-ui-independent-review.v1",
        "review_id": review_id,
        "candidate_id": manifest["candidate_id"],
        "candidate_manifest_sha256": bundle["manifest_sha256"],
        "expected_revision": deepcopy(expected),
        "scope": deepcopy(manifest["scope"]),
        "decision": decision,
        "reviewed_images": images,
        "reviewer": "Q04 real-browser test (test author, not an independent person)",
        "method": "Exact image and candidate binding check in an automated test.",
        "reason": "Exercise the explicit review path; no human image review is claimed.",
    }
    directory = fixture.root / "reviews"
    directory.mkdir(exist_ok=True)
    path = directory / (review_id + ".json")
    path.write_bytes(canonical(value))
    reference = absolute_file(path)

    def callback(request):
        assert request["review_evidence"] == reference
        assert read_json(path, 131072) == value
        assert request["candidate"] == manifest
        assert request["expected_revision"] == expected
        return decision == "APPROVE"

    return value, reference, callback
