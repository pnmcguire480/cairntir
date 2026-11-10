"""Independent prepared snapshots for public PALADIN acceptance."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.access import bind_grant, issue_grant
from cairntir.managed import ManagedRuntime
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore

PACKET = Path(__file__).resolve().parent
FAMILIES = ("lint", "types", "build", "unit", "integration")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def bound(path, relative, role=None):
    value = {"path": relative, "sha256": digest(path.read_bytes())}
    if role is not None:
        value["role"] = role
    return value


def argument(root, path="", prefix=""):
    return {"root": root, "path": path, "prefix": prefix}


class PreparedFixture:
    def __init__(
        self,
        case,
        *,
        values=(7, 7, 7),
        modes=("normal", "normal", "normal"),
        real=False,
        variants=("clean", "clean", "clean"),
        scoped=False,
    ):
        temporary = tempfile.TemporaryDirectory()
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.real = real
        self.session = str(uuid4())
        self.snapshots = []
        self.outputs = []
        self.store = DrawerStore(self.root / "memory.db", HashEmbeddingProvider(32))
        case.addCleanup(lambda: self.store.close())
        self.homes = {
            "CAIRNTIR_HOME": str(self.root / "home"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
        self.environment_patch = patch.dict(os.environ, self.homes)
        self.environment_patch.start()
        case.addCleanup(self.environment_patch.stop)
        if real:
            platform_path = Path(os.environ["CAIRNTIR_PALADIN_PLATFORM"])
            self.platform = json.loads(platform_path.read_text(encoding="utf8"))
            environment = deepcopy(self.platform["environment"])
            environment["values"].update(self.homes)
            environment["values"]["CAIRNTIR_PALADIN_PLATFORM"] = str(platform_path)
            environment["values"]["COVERAGE_FILE"] = str(self.root / "scratch" / ".coverage")
            (self.root / "scratch").mkdir()
            self.prepared_environment = patch.dict(os.environ, environment["values"], clear=True)
            self.prepared_environment.start()
            case.addCleanup(self.prepared_environment.stop)
            self.environment = environment
            self.tools = deepcopy(self.platform["tools"])
            self.commands = json.loads(
                (platform_path.parent / "stage-commands.json").read_text(encoding="utf8")
            )
        else:
            self.environment = {
                "policy_id": "public-controlled-process",
                "values": self.homes,
                "absent": [],
            }
            toolroot = self.root / "tools"
            toolroot.mkdir()
            executable = str(Path(sys.executable).resolve())
            observed = subprocess.run(  # noqa: S603 - resolved current interpreter
                [executable, "--version"], capture_output=True, text=True, check=True
            )
            version_record = {
                "schema": "cairntir.tool-version.v1",
                "argv": [executable, "--version"],
                "exit_code": observed.returncode,
                "stdout": observed.stdout,
                "stderr": observed.stderr,
                "version": sys.version.split()[0],
            }
            (toolroot / "version.json").write_bytes(canonical(version_record))
            self.tools = [
                {
                    "id": "python",
                    "executable": executable,
                    "sha256": digest(Path(executable).read_bytes()),
                    "version": sys.version.split()[0],
                    "version_evidence": bound(toolroot / "version.json", "version.json"),
                    "payload_root": str(toolroot),
                    "payload_files": [bound(toolroot / "version.json", "version.json")],
                }
            ]
        for index in range(3):
            snapshot, output = self.root / f"snapshot-{index}", self.root / f"output-{index}"
            snapshot.mkdir()
            output.mkdir()
            for family in FAMILIES:
                (output / family).mkdir()
            self.snapshots.append(snapshot)
            self.outputs.append(output)
            if real:
                shutil.copytree(PACKET / "fixture", snapshot, dirs_exist_ok=True)
                self._variant(snapshot, variants[index])
            else:
                (snapshot / "src").mkdir()
                (snapshot / "acceptance").mkdir()
                (snapshot / "src/subject.json").write_text(
                    json.dumps({"value": values[index], "mode": modes[index]})
                )
                shutil.copyfile(
                    PACKET / "controlled_stage.py",
                    snapshot / "acceptance/controlled_stage.py",
                )
                (snapshot / "acceptance/contract.txt").write_text(
                    "Independent expected value: seven. All five stages are required.\n"
                )
        first = self.snapshots[0]
        self.implementation_paths = sorted(
            p.relative_to(first).as_posix()
            for p in first.rglob("*")
            if p.is_file() and "acceptance" not in p.relative_to(first).parts
        )
        inputs = [
            bound(p, p.relative_to(first).as_posix(), "test" if p.suffix == ".py" else "config")
            for p in sorted((first / "acceptance").rglob("*"))
            if p.is_file()
        ]
        stages = [self._stage(name) for name in FAMILIES]
        slots = []
        profiles = {}
        for index, (snapshot, output) in enumerate(zip(self.snapshots, self.outputs, strict=True)):
            bindings = []
            for stage in stages:
                command = stage["command"]
                roots = {"snapshot": snapshot, "output": output}
                argv = [
                    x
                    if isinstance(x, str)
                    else x["prefix"] + str((roots[x["root"]] / x["path"]).resolve())
                    for x in command["argv"]
                ]
                profile = {
                    "argv": argv,
                    "cwd": str((roots[command["cwd"]["root"]] / command["cwd"]["path"]).resolve()),
                    "timeout_seconds": command["timeout_seconds"],
                    "output_limit_bytes": command["output_limit_bytes"],
                    "executable_sha256": digest(Path(argv[0]).read_bytes()),
                }
                name = f"slot{index}_{stage['stage_id']}"
                profiles[name] = {k: v for k, v in profile.items() if k != "executable_sha256"}
                bindings.append(
                    {
                        "stage_id": stage["stage_id"],
                        "profile": name,
                        "profile_sha256": digest(canonical(profile)),
                        "configured_profile": profile,
                    }
                )
            slots.append(
                {
                    "index": index,
                    "snapshot_root": str(snapshot),
                    "output_root": str(output),
                    "profiles": bindings,
                }
            )
        self.runtime_config = {
            "schema": "cairntir.managed-config.v1",
            "wing": "paladin",
            "room": "requests",
            "project_root": str(self.root),
            "brief_budget_chars": 32768,
            "profiles": profiles,
        }
        self.token = (
            issue_grant(self.store, scopes=[{"wing": "paladin"}], capabilities=["read", "write"])
            if scoped
            else None
        )
        self.runtime = ManagedRuntime(
            bind_grant(self.store, self.token) if self.token else self.store,
            config=deepcopy(self.runtime_config),
        )
        self.runtime.start(self.session)
        self.capture = self.runtime.capture(
            {
                "schema": "cairntir.managed-event.v1",
                "event_id": str(uuid4()),
                "session_id": self.session,
                "sequence": 1,
                "task_id": None,
                "expected_revision": 0,
                "content": (
                    "Qualify only the frozen prepared Python fixture; retain every failed attempt."
                ),
            }
        )
        finalization = {
            "contract": {
                "roadmap_modes": ["implementation", "finalization"],
                "thesis": "Execute the fixed prepared Python gates with evidence.",
                "issue": "A zero exit or coverage number cannot substitute for required behavior.",
                "acceptance_criteria": [
                    "All required stages execute and pass unchanged acceptance."
                ],
                "test_parameters": ["Public local process witnesses."],
                "non_goals": ["No private custody or host installation."],
                "verification_reserve": 25,
                "max_repair_rounds": 2,
                "gate_kind": "offline",
            },
            "coder_id": "fixture-builder",
            "tester_id": "independent-public-tester",
            "acceptance_paths": [x["path"] for x in inputs],
        }
        self.plan = {
            "wing": "paladin",
            "task_id": self.capture["task_id"],
            "inputs": inputs,
            "implementation_paths": self.implementation_paths,
            "tools": self.tools,
            "environment": self.environment,
            "stages": stages,
            "attempt_slots": slots,
            "finalization": finalization,
            "human_items": [],
            "rationale_evidence": [],
        }
        self.run_id = str(uuid4())
        self.attempt_ids = [str(uuid4()) for _ in range(3)]

    def _variant(self, snapshot, variant):
        boundary = snapshot / "src/paladin_fixture/boundaries.py"
        counter = snapshot / "src/paladin_fixture/counter.py"
        if variant == "lint":
            boundary.write_text("import os\n" + boundary.read_text())
        elif variant == "types":
            boundary.write_text('def clamp_count(value: int) -> int:\n    return "wrong type"\n')
        elif variant == "behavior":
            boundary.write_text(
                "def clamp_count(value: int) -> int:\n    return -value if value < 0 else value\n"
            )
        elif variant == "restart":
            counter.write_text(
                counter.read_text().replace(
                    'print(row[0] if row is not None else "missing")', 'print("missing")'
                )
            )
        elif variant == "build":
            project = snapshot / "pyproject.toml"
            project.write_text(
                project.read_text().replace('version = "0.0.1"', 'version = "not-a-valid-version!"')
            )
        elif variant != "clean":
            raise ValueError(variant)

    def _stage(self, family):
        if self.real:
            command = deepcopy(self.commands[family])
            test_ids = {
                "unit": [
                    ["acceptance.test_unit", "test_negative"],
                    ["acceptance.test_unit", "test_zero"],
                    ["acceptance.test_unit", "test_positive"],
                ],
                "integration": [["acceptance.test_integration", "test_persistent_counter"]],
            }.get(family, [])
            source = "src/paladin_fixture/boundaries.py"
            tool_ids = [x["id"] for x in self.tools]
        else:
            command = {
                "argv": [
                    self.tools[0]["executable"],
                    "-I",
                    "-B",
                    argument("snapshot", "acceptance/controlled_stage.py"),
                    family,
                    argument("snapshot"),
                    argument("output"),
                ],
                "cwd": {"root": "snapshot", "path": ""},
                "timeout_seconds": 2,
                "output_limit_bytes": 1048576,
            }
            test_ids = [["public_oracle", family]] if family in {"unit", "integration"} else []
            source = "src/subject.json"
            tool_ids = ["python"]
        artifacts = []
        if self.real and family in {"lint", "types"}:
            artifacts.append(
                {
                    "path": "lint/report.json" if family == "lint" else "types/report.xml",
                    "format": "file",
                    "required_members": [],
                }
            )
        if family in {"unit", "integration"}:
            artifacts.append(
                {"path": f"{family}/report.xml", "format": "junit", "required_members": []}
            )
        if family == "unit":
            artifacts.append(
                {"path": "unit/coverage.json", "format": "coverage-json", "required_members": []}
            )
        if family == "build":
            sources = (
                list(self.implementation_paths) if hasattr(self, "implementation_paths") else []
            )
            members = (
                [
                    {"member": p.removeprefix("src/"), "source_path": p}
                    for p in sources
                    if p.endswith(".py")
                ]
                if self.real
                else [{"member": "paladin_fixture/subject.json", "source_path": source}]
            )
            artifacts.append(
                {
                    "path": "build/paladin_fixture-0.0.1-py3-none-any.whl"
                    if self.real
                    else "build/fixture.whl",
                    "format": "wheel",
                    "required_members": members,
                }
            )
        return {
            "stage_id": family,
            "family": family,
            "tool_ids": tool_ids,
            "requires": [],
            "command": command,
            "artifacts": artifacts,
            "required_test_ids": test_ids,
            "coverage": {"minimum_percent": 95.0, "source_paths": [source]}
            if family == "unit"
            else None,
        }

    def contract(self, index=0):
        snapshot = self.snapshots[index]
        return {
            "schema": "cairntir.paladin-python-contract.v1",
            "run_id": self.run_id,
            "plan": deepcopy(self.plan),
            "attempt": {
                "attempt_id": self.attempt_ids[index],
                "index": index,
                "parent_attempt_id": None if index == 0 else self.attempt_ids[index - 1],
                "inputs": [
                    bound(snapshot / path, path, "source") for path in self.implementation_paths
                ],
            },
        }

    def action(self, stage, index=0):
        brief = self.runtime.brief()
        ack = self.runtime.acknowledge(
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
            "profile": f"slot{index}_{stage}",
            "claim": f"Execute required {stage} evidence for the selected frozen attempt.",
            "predicted_outcome": "The fixed stage produces complete passing evidence.",
            "event_ids": [self.capture["event_id"]],
        }

    def restart(self):
        self.runtime.close(last_sequence=1)
        self.store.close()
        self.store = DrawerStore(self.root / "memory.db", HashEmbeddingProvider(32))
        self.runtime = ManagedRuntime(
            bind_grant(self.store, self.token) if self.token else self.store,
            config=deepcopy(self.runtime_config),
        )

    def state(self):
        return "\n".join(self.store._conn.iterdump())

    def effects(self, index=0):
        path = self.outputs[index] / "effects.log"
        return path.read_bytes() if path.exists() else b""
