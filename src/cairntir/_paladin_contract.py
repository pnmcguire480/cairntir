"""Strict PALADIN contracts and read-only prepared-environment qualification."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import UUID

from cairntir.errors import CairntirError
from cairntir.finalization import FinalizationContract, FinalizationError

_FAMILIES = {"lint", "types", "build", "unit", "integration"}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class PaladinPythonError(CairntirError):
    """A prepared Python contract or its bound evidence is invalid."""


def canonical_sha(value: object) -> str:
    """Hash the exact JSON wire value without coercion or nonfinite numbers."""
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PaladinPythonError("contract must contain valid finite JSON values") from exc
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or (not empty and not value.strip()):
        raise PaladinPythonError(f"{label} must be a valid string")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise PaladinPythonError(f"{label} must be valid UTF-8") from exc
    return value


def _relative(value: object, *, allow_root: bool = False) -> str:
    text = _text(value, "relative path", empty=allow_root)
    if text == "" and allow_root:
        return text
    parts = text.split("/")
    if (
        "\\" in text
        or ":" in text
        or PureWindowsPath(text).drive
        or any(part in {"", ".", ".."} or part.rstrip(" .") != part for part in parts)
    ):
        raise PaladinPythonError("path must be a normalized relative POSIX path")
    return text


def _absolute(value: object) -> Path:
    path = Path(_text(value, "absolute path"))
    if not path.is_absolute():
        raise PaladinPythonError("root and executable paths must be absolute")
    return Path(os.path.normpath(path))


def contained_path(root: Path, relative: str, *, allow_root: bool = False) -> Path:
    """Resolve a normalized relative path without allowing symlink/reparse escape."""
    relative = _relative(relative, allow_root=allow_root)
    root = _absolute(str(root)).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise PaladinPythonError("resolved path escapes its declared root")
    return path


def _record(value: object, names: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != set(names.split()):
        raise PaladinPythonError("contract record fields do not match the schema")
    return value


def _list(value: object, *, minimum: int = 0) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum:
        raise PaladinPythonError("contract list has invalid type or length")
    return value


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise PaladinPythonError("contract integer is outside its permitted range")
    return value


def _uuid(value: object) -> None:
    text = _text(value, "UUID")
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise PaladinPythonError("identifier must be a canonical lowercase UUID") from exc
    if str(parsed) != text:
        raise PaladinPythonError("identifier must be a canonical lowercase UUID")


def _digest(value: object) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise PaladinPythonError("digest must be lowercase SHA256")


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise PaladinPythonError(f"duplicate {label}")


def _paths(values: object, *, minimum: int = 1) -> list[str]:
    paths = [_relative(item) for item in _list(values, minimum=minimum)]
    _unique([p.casefold() for p in paths], "paths")
    return paths


def _files(values: object, roles: set[str] | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    seen = set()
    for item in _list(values, minimum=1):
        record = _record(item, "path sha256" + (" role" if roles is not None else ""))
        path = _relative(record["path"])
        _digest(record["sha256"])
        if roles is not None and record["role"] not in roles:
            raise PaladinPythonError("input role does not match the schema")
        if path.casefold() in seen:
            raise PaladinPythonError("duplicate input path")
        seen.add(path.casefold())
        result[path] = record["sha256"]
    return result


def _reference(value: object, *, argument: bool = False) -> None:
    ref = _record(value, "root path prefix" if argument else "root path")
    if ref["root"] not in {"snapshot", "output"}:
        raise PaladinPythonError("command reference names an unknown root")
    _relative(ref["path"], allow_root=True)
    if argument:
        _text(ref["prefix"], "argument prefix", empty=True)


def _command(value: object, *, configured: bool = False) -> dict[str, Any]:
    names = "argv cwd timeout_seconds output_limit_bytes"
    command = _record(value, names + (" executable_sha256" if configured else ""))
    argv = _list(command["argv"], minimum=1)
    for item in argv:
        if isinstance(item, str):
            _text(item, "command argument", empty=True)
        elif not configured:
            _reference(item, argument=True)
        else:
            raise PaladinPythonError("configured argv must contain only strings")
    _absolute(argv[0])
    if configured:
        _absolute(command["cwd"])
        _digest(command["executable_sha256"])
    else:
        _reference(command["cwd"])
    _integer(command["timeout_seconds"], 1, 300)
    _integer(command["output_limit_bytes"], 1, 1048576)
    return command


def _expanded(command: dict[str, Any], slot: dict[str, Any], executable_sha: str) -> dict[str, Any]:
    roots = {"snapshot": _absolute(slot["snapshot_root"]), "output": _absolute(slot["output_root"])}
    argv = [
        item if isinstance(item, str) else item["prefix"] + str(roots[item["root"]] / item["path"])
        for item in command["argv"]
    ]
    argv[0] = str(_absolute(argv[0]))
    cwd = command["cwd"]
    return {
        "argv": argv,
        "cwd": str(roots[cwd["root"]] / cwd["path"]),
        "timeout_seconds": command["timeout_seconds"],
        "output_limit_bytes": command["output_limit_bytes"],
        "executable_sha256": executable_sha,
    }


def _tool(value: object) -> dict[str, Any]:
    tool = _record(
        value, "id executable sha256 version version_evidence payload_root payload_files"
    )
    _text(tool["id"], "tool id")
    _absolute(tool["executable"])
    _absolute(tool["payload_root"])
    _digest(tool["sha256"])
    _text(tool["version"], "tool version")
    files = _files(tool["payload_files"])
    version = _record(tool["version_evidence"], "path sha256")
    _relative(version["path"])
    _digest(version["sha256"])
    if files.get(version["path"]) != version["sha256"]:
        raise PaladinPythonError("tool version evidence must be bound in its payload inventory")
    return tool


def _version_record(tool: dict[str, Any], value: object) -> None:
    record = _record(value, "schema argv exit_code stdout stderr version")
    if (
        record["schema"] != "cairntir.tool-version.v1"
        or type(record["exit_code"]) is not int
        or record["exit_code"] != 0
        or record["version"] != tool["version"]
    ):
        raise PaladinPythonError("tool version observation differs")
    argv = _list(record["argv"], minimum=1)
    for argument in argv:
        _text(argument, "version command argument", empty=True)
    if _absolute(argv[0]) != _absolute(tool["executable"]):
        raise PaladinPythonError("version command uses a different executable")
    _text(record["stdout"], "version stdout", empty=True)
    _text(record["stderr"], "version stderr", empty=True)


def _stage(
    value: object, inputs: set[str], tools: dict[str, dict[str, Any]], earlier: set[str]
) -> dict[str, Any]:
    stage = _record(
        value, "stage_id family tool_ids requires command artifacts required_test_ids coverage"
    )
    _text(stage["stage_id"], "stage id")
    if stage["family"] not in _FAMILIES:
        raise PaladinPythonError("unknown stage family")
    ids = [_text(x, "tool id") for x in _list(stage["tool_ids"], minimum=1)]
    _unique(ids, "tool ids")
    if not set(ids) <= tools.keys():
        raise PaladinPythonError("stage refers to an unbound tool")
    prerequisites = [_text(x, "prerequisite") for x in _list(stage["requires"])]
    _unique(prerequisites, "stage prerequisites")
    if not set(prerequisites) <= earlier:
        raise PaladinPythonError("stage prerequisites must precede it")
    cmd = _command(stage["command"])
    if not any(_absolute(cmd["argv"][0]) == _absolute(tools[item]["executable"]) for item in ids):
        raise PaladinPythonError("stage executable has no selected tool binding")
    formats = []
    for artifact in _list(stage["artifacts"]):
        artifact = _record(artifact, "path format required_members")
        _relative(artifact["path"])
        if artifact["format"] not in {"junit", "coverage-json", "wheel", "file"}:
            raise PaladinPythonError("unknown artifact format")
        formats.append(artifact["format"])
        members = _list(artifact["required_members"])
        if bool(members) != (artifact["format"] == "wheel"):
            raise PaladinPythonError("only wheel artifacts have nonempty required member bindings")
        names = []
        for member in members:
            member = _record(member, "member source_path")
            names.append(_relative(member["member"]))
            if _relative(member["source_path"]) not in inputs:
                raise PaladinPythonError("wheel member refers to an unbound source")
        _unique(names, "wheel members")
    pairs = []
    for pair in _list(stage["required_test_ids"]):
        pair = _list(pair, minimum=2)
        if len(pair) != 2:
            raise PaladinPythonError("test identity must contain classname and name")
        pairs.append((_text(pair[0], "test classname"), _text(pair[1], "test name")))
    if len(pairs) != len(set(pairs)):
        raise PaladinPythonError("duplicate required test identity")
    testing = stage["family"] in {"unit", "integration"}
    if testing and (not pairs or formats.count("junit") != 1):
        raise PaladinPythonError("test stages require identities and exactly one JUnit artifact")
    if not testing and pairs:
        raise PaladinPythonError("only test stages declare required test identities")
    if stage["family"] == "build" and "wheel" not in formats:
        raise PaladinPythonError("build stage requires a wheel artifact")
    if stage["family"] == "unit":
        coverage = _record(stage["coverage"], "minimum_percent source_paths")
        minimum = coverage["minimum_percent"]
        if (
            type(minimum) not in (int, float)
            or not math.isfinite(minimum)
            or not 0 <= minimum <= 100
        ):
            raise PaladinPythonError("coverage threshold must be finite and in 0..100")
        if (
            not set(_paths(coverage["source_paths"])) <= inputs
            or formats.count("coverage-json") != 1
        ):
            raise PaladinPythonError(
                "coverage requires bound sources and exactly one JSON artifact"
            )
    elif stage["coverage"] is not None:
        raise PaladinPythonError("only unit stages declare coverage thresholds")
    return stage


def _finalization(value: object, inputs: set[str]) -> int:
    value = _record(value, "contract coder_id tester_id acceptance_paths")
    coder = _text(value["coder_id"], "coder id")
    tester = _text(value["tester_id"], "tester id")
    if coder == tester:
        raise PaladinPythonError("coder and tester role identities must differ")
    if not set(_paths(value["acceptance_paths"])) <= inputs:
        raise PaladinPythonError("acceptance paths must bind immutable inputs")
    contract = _record(
        value["contract"],
        "roadmap_modes thesis issue acceptance_criteria test_parameters non_goals "
        "verification_reserve max_repair_rounds gate_kind",
    )
    for name in ("roadmap_modes", "acceptance_criteria", "test_parameters", "non_goals"):
        for item in _list(contract[name], minimum=1):
            _text(item, name)
    for name in ("thesis", "issue"):
        _text(contract[name], name)
    _integer(contract["verification_reserve"], 25, 100)
    rounds = _integer(contract["max_repair_rounds"], 1, 2)
    if contract["gate_kind"] != "offline":
        raise PaladinPythonError("this controller supports only prepared offline finalization")
    try:
        FinalizationContract.freeze(**contract)
    except FinalizationError as exc:
        raise PaladinPythonError(str(exc)) from exc
    return rounds


@dataclass(frozen=True)
class CheckedContract:
    """Detached validated wire data and its exact plan/attempt identities."""

    data: dict[str, Any]
    plan_sha256: str
    contract_sha256: str
    slot: dict[str, Any]
    stages: dict[str, dict[str, Any]]


def validate_contract(value: object) -> CheckedContract:
    """Validate syntax and immutable plan relationships without inspecting files."""
    try:
        return _validate_contract(value)
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as exc:
        if isinstance(exc, PaladinPythonError):
            raise
        raise PaladinPythonError("invalid prepared Python contract") from exc


def _validate_contract(value: object) -> CheckedContract:
    data = deepcopy(_record(value, "schema run_id plan attempt"))
    if data["schema"] != "cairntir.paladin-python-contract.v1":
        raise PaladinPythonError("unknown prepared Python contract schema")
    _uuid(data["run_id"])
    plan = _record(
        data["plan"],
        "wing task_id inputs implementation_paths tools environment stages attempt_slots "
        "finalization human_items rationale_evidence",
    )
    _text(plan["wing"], "wing")
    _uuid(plan["task_id"])
    fixed = _files(plan["inputs"], {"test", "config"})
    implementation = _paths(plan["implementation_paths"])
    _unique([name.casefold() for name in [*fixed, *implementation]], "source and acceptance paths")
    for left in fixed:
        for right in implementation:
            if left.casefold().startswith(right.casefold() + "/") or right.casefold().startswith(
                left.casefold() + "/"
            ):
                raise PaladinPythonError("source and acceptance paths must not overlap")
    tools = [_tool(item) for item in _list(plan["tools"], minimum=1)]
    _unique([tool["id"] for tool in tools], "tool ids")
    tool_map = {tool["id"]: tool for tool in tools}
    identities: dict[Path, str] = {}
    for tool in tools:
        executable = _absolute(tool["executable"])
        if executable in identities and identities[executable] != tool["sha256"]:
            raise PaladinPythonError("one executable has conflicting identities")
        identities[executable] = tool["sha256"]
    environment = _record(plan["environment"], "policy_id values absent")
    _text(environment["policy_id"], "environment policy")
    if not isinstance(environment["values"], dict):
        raise PaladinPythonError("environment values must be a mapping")
    keys = []
    for key, item in environment["values"].items():
        key = _text(key, "environment variable")
        if "=" in key:
            raise PaladinPythonError("invalid environment variable name")
        keys.append(key.casefold())
        _text(item, "environment value", empty=True)
    absent = [
        _text(item, "absent environment variable").casefold()
        for item in _list(environment["absent"])
    ]
    _unique(keys + absent, "or contradictory environment declarations")
    stages: dict[str, dict[str, Any]] = {}
    for item in _list(plan["stages"], minimum=5):
        stage = _stage(item, set(fixed) | set(implementation), tool_map, set(stages))
        if stage["stage_id"] in stages:
            raise PaladinPythonError("duplicate stage id")
        stages[stage["stage_id"]] = stage
    if {stage["family"] for stage in stages.values()} != _FAMILIES:
        raise PaladinPythonError("all five Python stage families are required")
    artifacts = [
        item["path"].casefold() for stage in stages.values() for item in stage["artifacts"]
    ]
    _unique(artifacts, "artifact paths")
    rounds = _finalization(plan["finalization"], set(fixed))
    humans = []
    for item in _list(plan["human_items"]):
        item = _record(item, "id description required")
        humans.append(_text(item["id"], "human item id"))
        _text(item["description"], "human item description")
        if item["required"] is not True:
            raise PaladinPythonError("human items must remain required")
    _unique(humans, "human item ids")
    for item in _list(plan["rationale_evidence"]):
        item = _record(item, "drawer_id source_identity content_sha256")
        _integer(item["drawer_id"], 1, 2**63 - 1)
        _uuid(item["source_identity"])
        _digest(item["content_sha256"])
    slots = _list(plan["attempt_slots"], minimum=2)
    if len(slots) != rounds + 1:
        raise PaladinPythonError("attempt slots must match the bounded repair budget")
    roots: list[Path] = []
    profile_names = []
    for index, slot in enumerate(slots):
        slot = _record(slot, "index snapshot_root output_root profiles")
        if _integer(slot["index"], 0, 2) != index:
            raise PaladinPythonError("attempt slots must have contiguous indices")
        roots.extend((_absolute(slot["snapshot_root"]), _absolute(slot["output_root"])))
        bindings = _list(slot["profiles"], minimum=5)
        if len(bindings) != len(stages):
            raise PaladinPythonError("each slot must bind every stage exactly once")
        selected = []
        for binding in bindings:
            binding = _record(binding, "stage_id profile profile_sha256 configured_profile")
            stage_id = _text(binding["stage_id"], "bound stage id")
            if stage_id not in stages:
                raise PaladinPythonError("profile refers to an unknown stage")
            selected.append(stage_id)
            profile_names.append(_text(binding["profile"], "profile name"))
            configured = _command(binding["configured_profile"], configured=True)
            _digest(binding["profile_sha256"])
            executable = _absolute(stages[stage_id]["command"]["argv"][0])
            expected = _expanded(stages[stage_id]["command"], slot, identities[executable])
            if configured != expected or canonical_sha(configured) != binding["profile_sha256"]:
                raise PaladinPythonError(
                    "configured profile differs from its fixed command template"
                )
        _unique(selected, "slot stage bindings")
    _unique(profile_names, "slot profile names")
    for index, root in enumerate(roots):
        if any(root.is_relative_to(other) or other.is_relative_to(root) for other in roots[:index]):
            raise PaladinPythonError("attempt snapshot and output roots must be disjoint")
        for tool in tools:
            tool_root = _absolute(tool["payload_root"])
            if root.is_relative_to(tool_root) or tool_root.is_relative_to(root):
                raise PaladinPythonError("attempt roots must not overlap tool payload roots")
    attempt = _record(data["attempt"], "attempt_id index parent_attempt_id inputs")
    _uuid(attempt["attempt_id"])
    index = _integer(attempt["index"], 0, rounds)
    if index == 0:
        if attempt["parent_attempt_id"] is not None:
            raise PaladinPythonError("initial attempt cannot have a parent")
    else:
        _uuid(attempt["parent_attempt_id"])
        if attempt["parent_attempt_id"] == attempt["attempt_id"]:
            raise PaladinPythonError("attempt cannot parent itself")
    if set(_files(attempt["inputs"], {"source"})) != set(implementation):
        raise PaladinPythonError("attempt inputs must exactly bind implementation paths")
    return CheckedContract(data, canonical_sha(plan), canonical_sha(data), slots[index], stages)


def qualify_contract(
    checked: CheckedContract,
    *,
    runtime_config: Mapping[str, Any],
    environment: Mapping[str, str],
    stage_id: str | None = None,
) -> dict[str, Any]:
    """Observe current bindings without loading models, executing tools or writing files."""
    diagnostics: list[str] = []
    unavailable = False
    hashes: dict[Path, str] = {}
    plan = checked.data["plan"]

    def problem(message: str, *, missing: bool = False) -> None:
        nonlocal unavailable
        diagnostics.append(message)
        unavailable |= missing

    def directory(value: str) -> Path | None:
        try:
            path = _absolute(value)
            if not path.is_dir():
                problem(f"required root unavailable: {value}", missing=True)
                return None
            if path.resolve() != path:
                problem(f"declared root resolution changed: {value}")
        except (OSError, RuntimeError) as exc:
            problem(f"required root unavailable: {value} ({type(exc).__name__})", missing=True)
            return None
        else:
            return path

    def verify(path: Path, digest: str) -> None:
        try:
            if path not in hashes:
                hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            if hashes[path] != digest:
                problem(f"bound file changed: {path}")
        except OSError as exc:
            problem(f"bound file unavailable: {path} ({type(exc).__name__})", missing=True)

    def bound(root: Path, item: dict[str, Any]) -> None:
        try:
            verify(contained_path(root, item["path"]), item["sha256"])
        except PaladinPythonError:
            problem(f"bound file escapes its root: {item['path']}")
        except (OSError, RuntimeError) as exc:
            problem(f"bound file unavailable: {item['path']} ({type(exc).__name__})", missing=True)

    if canonical_sha(checked.data) != checked.contract_sha256:
        problem("validated contract was mutated")
        return {"status": "STALE", "diagnostics": diagnostics}
    if stage_id is not None and stage_id not in checked.stages:
        raise PaladinPythonError("unknown stage id")
    declared = plan["environment"]
    for key, expected in declared["values"].items():
        if environment.get(key) != expected:
            problem(f"declared environment value differs: {key}")
    for key in declared["absent"]:
        if key in environment:
            problem(f"forbidden environment variable present: {key}")
    actual_profiles = runtime_config.get("profiles", {})
    if not isinstance(actual_profiles, Mapping):
        problem("runtime profiles are unavailable", missing=True)
        actual_profiles = {}
    expected_paths = {item["path"] for item in plan["inputs"]} | set(plan["implementation_paths"])
    for slot in plan["attempt_slots"]:
        snapshot = directory(slot["snapshot_root"])
        output = directory(slot["output_root"])
        if snapshot is not None:
            for item in plan["inputs"]:
                bound(snapshot, item)
            if slot["index"] == checked.data["attempt"]["index"]:
                for item in checked.data["attempt"]["inputs"]:
                    bound(snapshot, item)
                try:
                    observed = {
                        p.relative_to(snapshot).as_posix()
                        for p in snapshot.rglob("*")
                        if p.is_file()
                    }
                    if observed != expected_paths:
                        problem("snapshot file inventory differs from frozen inputs")
                except OSError as exc:
                    problem(f"snapshot inventory unavailable ({type(exc).__name__})", missing=True)
        for binding in slot["profiles"]:
            configured = binding["configured_profile"]
            resolved = {
                **configured,
                "executable_path": str(Path(configured["argv"][0]).resolve()),
            }
            if actual_profiles.get(binding["profile"]) not in (configured, resolved):
                problem(f"runtime profile differs: {binding['profile']}")
        if snapshot is not None and output is not None:
            for stage in checked.stages.values():
                refs = [arg for arg in stage["command"]["argv"] if isinstance(arg, dict)]
                refs.append(stage["command"]["cwd"])
                for ref in refs:
                    try:
                        contained_path(
                            snapshot if ref["root"] == "snapshot" else output,
                            ref["path"],
                            allow_root=True,
                        )
                    except PaladinPythonError:
                        problem("command reference escapes its declared root")
                    except (OSError, RuntimeError) as exc:
                        problem(
                            f"command reference unavailable ({type(exc).__name__})", missing=True
                        )
                for artifact in stage["artifacts"]:
                    try:
                        contained_path(output, artifact["path"])
                    except PaladinPythonError:
                        problem("artifact path escapes its declared root")
                    except (OSError, RuntimeError) as exc:
                        problem(f"artifact path unavailable ({type(exc).__name__})", missing=True)
    for tool in plan["tools"]:
        verify(Path(tool["executable"]), tool["sha256"])
        root = directory(tool["payload_root"])
        if root is None:
            continue
        for item in tool["payload_files"]:
            bound(root, item)
        try:
            path = contained_path(root, tool["version_evidence"]["path"])
            _version_record(tool, json.loads(path.read_text(encoding="utf-8")))
        except OSError as exc:
            problem(
                f"tool version evidence unavailable: {tool['id']} ({type(exc).__name__})",
                missing=True,
            )
        except (PaladinPythonError, ValueError, TypeError, KeyError, RuntimeError):
            problem(f"tool version evidence is invalid: {tool['id']}")
    return {
        "status": "UNAVAILABLE" if unavailable else "STALE" if diagnostics else "CURRENT",
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }
