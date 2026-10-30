import hashlib
import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

PACKET = Path(__file__).resolve().parents[1]
STAGES = ("performance", "bundle", "security")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes())}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


class ResourceFixture:
    def __init__(self, root, variant="clean", producer_variant="normal", copy_uv=False):
        self.root = root.resolve()
        self.root.mkdir(parents=True)
        self.snapshot = self.root / "snapshot"
        self.output = self.root / "output"
        self.producer = self.root / "independent-producer"
        shutil.copytree(PACKET / "fixture", self.snapshot)
        shutil.copytree(PACKET / "producer", self.producer)
        self.output.mkdir()
        notes = self.snapshot / "src/q05_notes/notes.py"
        if variant == "redundant":
            notes.write_text(notes.read_text().replace(
                "    return [",
                "    for _ in range(20000):\n"
                '        connection.execute("SELECT SUM(id) FROM notes").fetchone()\n'
                "    return [", 1), encoding="utf-8")
        elif variant == "allocation":
            notes.write_text(notes.read_text().replace(
                "    return [", "    retained = bytearray(16 * 1024 * 1024)\n"
                "    retained[0] = 1\n    return [", 1), encoding="utf-8")
        elif variant == "oversized":
            (self.snapshot / "src/q05_notes/payload.bin").write_bytes(b"".join(
                hashlib.sha256(index.to_bytes(4, "little")).digest() for index in range(32768)
            ))
        elif variant in {"unsafe", "unsafe-noqa"}:
            expression = "return eval(text)" + ("  # noqa: S307" if variant == "unsafe-noqa" else "")
            notes.write_text(notes.read_text().replace("return int(text)", expression),
                             encoding="utf-8")
        elif variant == "wrong":
            notes.write_text(notes.read_text().replace("fetchone()[0]", 'fetchone()[0] + "-wrong"'),
                             encoding="utf-8")
        elif variant != "clean":
            raise ValueError(variant)
        if producer_variant == "receipt-only":
            (self.producer / "measure.py").write_text(
                "import pathlib,sys\n"
                'p=pathlib.Path(sys.argv[sys.argv.index("--output")+1])\n'
                'p.mkdir(parents=True,exist_ok=True)\n'
                'p.joinpath("report.json").write_text(\'{"datasets":[],"status":"PASS"}\')\n',
                encoding="utf-8")
        elif producer_variant == "timeout":
            (self.producer / "measure.py").write_text("while True:\n    pass\n", encoding="utf-8")
        elif producer_variant != "normal":
            raise ValueError(producer_variant)
        platform_path = Path(os.environ["CAIRNTIR_Q05_PLATFORM"])
        self.platform = json.loads(platform_path.read_text(encoding="utf-8"))
        self.tools = [deepcopy(tool) for tool in self.platform["tools"]
                      if tool["id"] in {"python", "ruff", "uv"}]
        if copy_uv:
            tool = next(tool for tool in self.tools if tool["id"] == "uv")
            original = Path(tool["payload_root"])
            copied = self.root / "copied-uv"
            for item in tool["payload_files"]:
                destination = copied / item["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original / item["path"], destination)
            tool["payload_root"] = str(copied)
        environment = deepcopy(self.platform["environment"])
        for key, relative in {
            "TEMP": "tmp", "TMP": "tmp", "HOME": "home", "USERPROFILE": "home",
            "LOCALAPPDATA": "home/local", "APPDATA": "home/roaming", "UV_CACHE_DIR": "uv-cache",
            "CAIRNTIR_HOME": "cairntir-home",
        }.items():
            directory = self.root / relative
            directory.mkdir(parents=True, exist_ok=True)
            environment["values"][key] = str(directory)
        environment["values"]["COVERAGE_FILE"] = str(self.root / ".coverage")
        self.environment_patch = patch.dict(os.environ, environment["values"], clear=True)
        self.environment_patch.start()
        python = next(tool["executable"] for tool in self.tools if tool["id"] == "python")
        uv = next(tool["executable"] for tool in self.tools if tool["id"] == "uv")
        prepared = Path(next(tool["payload_root"] for tool in self.tools if tool["id"] == "uv"))
        for name in STAGES:
            (self.output / name).mkdir()
        commands = {
            "performance": {
                "argv": [python, "-I", "-B", str(self.producer / "measure.py"),
                         "--snapshot", str(self.snapshot), "--output", str(self.output / "performance")],
                "cwd": str(self.snapshot), "timeout_seconds": 300, "output_limit_bytes": 1048576,
            },
            "bundle": {
                "argv": [uv, "build", "--offline", "--no-index", "--find-links",
                         str(prepared / "wheelhouse"), "--no-config", "--no-python-downloads",
                         "--link-mode", "copy", "--python", python, "--build-constraints",
                         str(prepared / "build-constraints.txt"), "--wheel", "--out-dir",
                         str(self.output / "bundle"), str(self.snapshot)],
                "cwd": str(self.snapshot), "timeout_seconds": 120, "output_limit_bytes": 1048576,
            },
            "security": {
                "argv": [python, "-I", "-B", "-m", "ruff", "check", "--isolated", "--select", "S307",
                         "--ignore-noqa", "--no-cache", "--output-format", "json", "--output-file",
                         str(self.output / "security/report.json"), str(self.snapshot / "src")],
                "cwd": str(self.snapshot), "timeout_seconds": 30, "output_limit_bytes": 1048576,
            },
        }
        if producer_variant == "timeout":
            commands["performance"]["timeout_seconds"] = 1
        self.config = {
            "schema": "cairntir.managed-config.v1", "wing": "resources", "room": "requests",
            "project_root": str(self.root), "brief_budget_chars": 262144,
            "profiles": {"q05_" + name: deepcopy(command) for name, command in commands.items()},
        }
        self.store = DrawerStore(self.root / "memory.db", HashEmbeddingProvider(32))
        self.runtime = ManagedRuntime(self.store, config=deepcopy(self.config))
        self.session_id = str(uuid4())
        self.runtime.start(self.session_id)
        self.capture = self.runtime.capture({
            "schema": "cairntir.managed-event.v1", "event_id": str(uuid4()),
            "session_id": self.session_id, "sequence": 1, "task_id": None,
            "expected_revision": 0,
            "content": "Run only the independently bound finite Q05 resource fixture; retain failures.",
        })
        artifacts = {
            "performance": [{"path": "performance/report.json", "format": "q05-performance"}],
            "bundle": [{"path": "bundle/q05_notes-0.0.1-py3-none-any.whl", "format": "wheel"}],
            "security": [{"path": "security/report.json", "format": "ruff-json"}],
        }
        self.contract = {
            "schema": "cairntir.paladin-resources-contract.v1", "run_id": str(uuid4()),
            "wing": "resources", "task_id": self.capture["task_id"],
            "snapshot_root": str(self.snapshot), "output_root": str(self.output),
            "producer_root": str(self.producer), "inputs": inventory(self.snapshot),
            "producer_files": inventory(self.producer), "tools": self.tools,
            "environment": environment,
            "policy": json.loads((PACKET / "POLICY.json").read_text(encoding="utf-8")),
            "stages": [{
                "stage_id": name, "family": name, "profile": "q05_" + name,
                "command": {**deepcopy(command), "executable_sha256": digest(Path(command["argv"][0]).read_bytes())},
                "tool_ids": {"performance": ["python"], "bundle": ["python", "uv"],
                             "security": ["python", "ruff"]}[name],
                "artifacts": artifacts[name],
            } for name, command in commands.items()],
        }
        self.actions = {}

    def action(self, stage):
        brief = self.runtime.brief()
        ack = self.runtime.acknowledge({"schema": "cairntir.managed-ack.v1",
                                       "brief_id": brief["brief_id"], "brief_sha256": brief["brief_sha256"]})
        action = {"schema": "cairntir.managed-action.v1", "action_id": str(uuid4()),
                  "ack_id": ack["ack_id"], "profile": "q05_" + stage,
                  "claim": "Execute actual Q05 " + stage,
                  "predicted_outcome": "The exact declared resource evidence determines the result.",
                  "event_ids": [self.capture["event_id"]]}
        self.actions[stage] = action
        return action

    def reopen(self):
        self.runtime.close(last_sequence=1)
        self.store.close()
        self.store = DrawerStore(self.root / "memory.db", HashEmbeddingProvider(32))
        self.runtime = ManagedRuntime(self.store, config=deepcopy(self.config))

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def close(self):
        self.store.close()
        self.environment_patch.stop()
