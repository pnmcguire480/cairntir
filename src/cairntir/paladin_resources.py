"""Run declared resource measurements through durable managed actions."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import os
import pstats
import re
import stat
import zipfile
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from email.message import Message
from email.parser import BytesHeaderParser
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

from cairntir._paladin_artifacts import _unique_object, _zip_name
from cairntir._paladin_contract import (
    _absolute,
    _command,
    _digest,
    _files,
    _integer,
    _list,
    _record,
    _relative,
    _text,
    _tool,
    _unique,
    _uuid,
    _version_record,
    canonical_sha,
    contained_path,
)
from cairntir.access import ScopedStore, _paladin_resources_records
from cairntir.durability import request_hash
from cairntir.errors import CairntirError
from cairntir.managed import ManagedRuntime
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.provenance import Sensitivity

_CHUNK = 65536
_HEADER_END = re.compile(rb"\r\n\r\n|\r\n\n|\n\r\n|\n\n|\r\r|\r\n\r|\n\r")
_STAGES = ("performance", "bundle", "security")
_FORMATS = ("q05-performance", "wheel", "ruff-json")
_P = ParamSpec("_P")
_T = TypeVar("_T")


class PaladinResourcesError(CairntirError):
    """A resource contract or its durable evidence is invalid."""


def _boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    @wraps(function)
    def call(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return function(*args, **kwargs)
        except (CairntirError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            if isinstance(exc, PaladinResourcesError):
                raise
            raise PaladinResourcesError(str(exc)) from exc

    return call


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PaladinResourcesError(message)


def _json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def _stream_wheel(
    artifact: Path, members: list[dict[str, str]], snapshot: Path, inputs: dict[str, str]
) -> dict[str, int]:
    with zipfile.ZipFile(artifact) as archive:
        contents: dict[str, zipfile.ZipInfo] = {}
        sizes: dict[str, int] = {}
        documents: dict[str, Message] = {}
        seen: set[str] = set()
        for info in archive.infolist():
            _require(info.orig_filename == info.filename, "truncated wheel member name")
            name = _zip_name(info.filename.removesuffix("/") if info.is_dir() else info.filename)
            _require(name.casefold() not in seen, "duplicate wheel member")
            seen.add(name.casefold())
            _require(
                not stat.S_ISLNK(info.external_attr >> 16), "wheel symlink member is unsupported"
            )
            if info.is_dir():
                continue
            contents[name] = info
            root = name.split("/")[0]
            headers = (
                bytearray()
                if root.endswith(".dist-info") and name in {root + "/METADATA", root + "/WHEEL"}
                else None
            )
            in_headers = headers is not None
            size = 0
            with archive.open(info) as stream:
                while chunk := stream.read(_CHUNK):
                    size += len(chunk)
                    if in_headers and headers is not None:
                        start = max(0, len(headers) - 3)
                        headers.extend(chunk)
                        boundary = _HEADER_END.search(headers, start)
                        if boundary is not None:
                            del headers[boundary.end() :]
                            in_headers = False
            _require(size == info.file_size, "wheel member size differs from archive")
            sizes[name] = size
            if headers is not None:
                documents[name] = BytesHeaderParser().parsebytes(bytes(headers))
        metadata_roots = {
            name.split("/")[0] for name in contents if name.split("/")[0].endswith(".dist-info")
        }
        _require(len(metadata_roots) == 1, "wheel must contain one distribution metadata directory")
        info_root = next(iter(metadata_roots))
        _require(
            all(f"{info_root}/{name}" in contents for name in ("METADATA", "WHEEL", "RECORD")),
            "wheel metadata is incomplete",
        )
        metadata = documents[f"{info_root}/METADATA"]
        wheel = documents[f"{info_root}/WHEEL"]
        _require(not metadata.defects and not wheel.defects, "malformed wheel metadata headers")
        for document, fields in (
            (metadata, ("Metadata-Version", "Name", "Version")),
            (wheel, ("Wheel-Version", "Root-Is-Purelib")),
        ):
            _require(
                all(
                    len(document.get_all(field, [])) == 1 and document[field].strip()
                    for field in fields
                ),
                "wheel metadata has missing or duplicate required headers",
            )
        name, version = metadata["Name"], metadata["Version"]
        _require(
            bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name)),
            "invalid wheel distribution name",
        )
        _require(
            bool(
                re.fullmatch(
                    r"(?:[1-9][0-9]*!)?(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*"
                    r"(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
                    r"(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?",
                    version,
                )
            ),
            "unsupported normalized wheel distribution version",
        )
        expected_root = re.sub(r"[-_.]+", "_", name).lower() + "-" + version + ".dist-info"
        _require(
            info_root.lower() == expected_root.lower(),
            "wheel distribution identity is inconsistent",
        )
        _require(
            bool(re.fullmatch(r"(?:1\.[1-9][0-9]*|2\.[0-9]+)", metadata["Metadata-Version"])),
            "unsupported wheel core metadata version",
        )
        _require(
            wheel["Wheel-Version"] == "1.0" and wheel["Root-Is-Purelib"] in {"true", "false"},
            "unsupported wheel format or installation scheme",
        )
        tags = wheel.get_all("Tag", [])
        _require(
            bool(tags)
            and len(set(tags)) == len(tags)
            and all(
                re.fullmatch(r"[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+", tag) for tag in tags
            ),
            "invalid wheel compatibility tags",
        )
        record_name = f"{info_root}/RECORD"
        records: dict[str, tuple[str, str]] = {}
        with (
            archive.open(contents[record_name]) as stream,
            io.TextIOWrapper(stream, encoding="utf-8", newline="") as text,
        ):
            for row in csv.reader(text, strict=True):
                _require(len(row) == 3, "invalid wheel RECORD row")
                entry = _zip_name(row[0])
                _require(entry not in records, "duplicate wheel RECORD entry")
                records[entry] = (row[1], row[2])
        signatures = {f"{info_root}/RECORD.jws", f"{info_root}/RECORD.p7s"}
        _require(
            set(records) == set(contents) - signatures,
            "wheel RECORD inventory differs from archive",
        )
        for entry, (digest, size_text) in records.items():
            if entry == record_name:
                _require(not digest and not size_text, "wheel RECORD cannot hash itself")
                continue
            _require(
                bool(re.fullmatch(r"[0-9]+", size_text)) and int(size_text) == sizes[entry],
                "wheel RECORD size differs from member",
            )
            algorithm, separator, encoded = digest.partition("=")
            _require(bool(separator), "wheel RECORD lacks a secure hash")
            hasher = hashlib.new(algorithm)
            _require(hasher.digest_size >= 32, "wheel RECORD hash algorithm is too weak")
            with archive.open(contents[entry]) as stream:
                while chunk := stream.read(_CHUNK):
                    hasher.update(chunk)
            computed = base64.urlsafe_b64encode(hasher.digest()).rstrip(b"=").decode("ascii")
            _require(encoded == computed, "wheel RECORD hash differs from member")
        for binding in members:
            member, source = binding["member"], binding["source_path"]
            _require(
                member in contents and source in inputs, "required wheel source/member is missing"
            )
            path = contained_path(snapshot, source)
            _require(_file_sha(path) == inputs[source], "wheel source binding changed")
            with path.open("rb") as original, archive.open(contents[member]) as candidate:
                while chunk := original.read(_CHUNK):
                    _require(
                        candidate.read(len(chunk)) == chunk,
                        "wheel member differs from bound source",
                    )
                _require(not candidate.read(1), "wheel member differs from bound source")
        return {
            "compressed_bytes": artifact.stat().st_size,
            "uncompressed_bytes": sum(sizes.values()),
            "member_count": len(contents),
        }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes(), object_pairs_hook=_unique_object)


def _validate(value: object) -> dict[str, Any]:
    data = deepcopy(
        _record(
            value,
            "schema run_id wing task_id snapshot_root output_root producer_root inputs "
            "producer_files tools environment policy stages",
        )
    )
    canonical_sha(data)
    _require(data["schema"] == "cairntir.paladin-resources-contract.v1", "unknown resource schema")
    for name in ("run_id", "task_id"):
        _uuid(data[name])
    _validate_ident(data["wing"], "wing")
    roots = [_absolute(data[name]) for name in ("snapshot_root", "output_root", "producer_root")]
    for index, root in enumerate(roots):
        _require(
            not any(
                root.is_relative_to(other) or other.is_relative_to(root) for other in roots[:index]
            ),
            "resource roots must be disjoint",
        )
    _files(data["inputs"])
    producer_files = _files(data["producer_files"])
    tools = [_tool(item) for item in _list(data["tools"], minimum=1)]
    _unique([item["id"] for item in tools], "tool identities")
    for tool in tools:
        tool_root = _absolute(tool["payload_root"])
        _require(
            all(
                not root.is_relative_to(tool_root) and not tool_root.is_relative_to(root)
                for root in roots
            ),
            "resource roots overlap a tool payload",
        )
    environment = _record(data["environment"], "policy_id values absent")
    _text(environment["policy_id"], "environment policy")
    _require(isinstance(environment["values"], dict), "environment values must be a mapping")
    keys = []
    for key, value in environment["values"].items():
        _text(key, "environment key")
        _require("=" not in key, "invalid environment key")
        _text(value, "environment value", empty=True)
        keys.append(key.casefold())
    absent = [
        _text(item, "absent environment key").casefold() for item in _list(environment["absent"])
    ]
    _unique(keys + absent, "environment declarations")
    policy = _record(
        data["policy"],
        "schema workload_id dataset_sizes expected_outputs reads_per_sample warmups samples "
        "wall_scope wall_p95_ns python_peak_bytes profile_sql_calls bundle_compressed_bytes "
        "bundle_uncompressed_bytes security_rules maximum_findings oracle",
    )
    _require(policy["schema"] == "cairntir.q05-policy.v1", "unknown resource policy schema")
    for name in ("workload_id", "oracle", "wall_scope"):
        _text(policy[name], name)
    sizes = [_integer(item, 1, 2**63 - 1) for item in _list(policy["dataset_sizes"], minimum=1)]
    _require(len(set(sizes)) == len(sizes), "duplicate dataset size")
    expected = {}
    for item in _list(policy["expected_outputs"], minimum=1):
        item = _record(item, "size expected_output_sha256")
        size = _integer(item["size"], 1, 2**63 - 1)
        _digest(item["expected_output_sha256"])
        _require(size not in expected, "duplicate oracle dataset")
        expected[size] = item["expected_output_sha256"]
    _require(set(expected) == set(sizes), "oracle manifest must cover exactly the declared sizes")
    for name in (
        "reads_per_sample",
        "samples",
        "wall_p95_ns",
        "python_peak_bytes",
        "profile_sql_calls",
        "bundle_compressed_bytes",
        "bundle_uncompressed_bytes",
    ):
        _integer(policy[name], 1, 2**63 - 1)
    for name in ("warmups", "maximum_findings"):
        _integer(policy[name], 0, 2**63 - 1)
    _require(policy["security_rules"] == ["S307"], "resource policy requires the S307 scanner rule")
    stages = _list(data["stages"], minimum=3)
    _require(len(stages) == 3, "all three resource stages are required")
    profiles = []
    tool_map = {item["id"]: item for item in tools}
    for stage, stage_id, artifact_format in zip(stages, _STAGES, _FORMATS, strict=True):
        stage = _record(stage, "stage_id family profile command tool_ids artifacts")
        _require(
            stage["stage_id"] == stage_id and stage["family"] == stage_id,
            "invalid resource stage order",
        )
        _validate_ident(stage["profile"], "profile")
        profiles.append(stage["profile"])
        command = _command(stage["command"], configured=True)
        _require(_absolute(command["cwd"]) == roots[0], "stage cwd must be the declared snapshot")
        selected = [_text(item, "tool id") for item in _list(stage["tool_ids"], minimum=1)]
        _unique(selected, "selected tools")
        _require(set(selected) <= tool_map.keys(), "stage selects an undeclared tool")
        _require(
            any(
                _absolute(tool_map[name]["executable"]) == _absolute(command["argv"][0])
                and tool_map[name]["sha256"] == command["executable_sha256"]
                for name in selected
            ),
            "stage executable is not a selected pinned tool",
        )
        artifacts = _list(stage["artifacts"], minimum=1)
        _require(len(artifacts) == 1, "each resource stage requires one primary artifact")
        artifact = _record(artifacts[0], "path format")
        path = _relative(artifact["path"])
        _require(
            path.startswith(stage_id + "/") and artifact["format"] == artifact_format,
            "invalid resource artifact",
        )
        if stage_id == "performance":
            _require(
                any(str(roots[2] / name) in command["argv"] for name in producer_files),
                "performance command must invoke the bound independent producer",
            )
        elif stage_id == "security":
            argv = command["argv"]
            required = ["--isolated", "--ignore-noqa", "--no-cache"]
            _require(
                all(argv.count(flag) == 1 for flag in required),
                "scanner isolation flags are required",
            )
            for flag, argument in (
                ("--select", "S307"),
                ("--output-format", "json"),
                ("--output-file", str(roots[1] / path)),
            ):
                _require(
                    argv.count(flag) == 1
                    and argv.index(flag) + 1 < len(argv)
                    and argv[argv.index(flag) + 1] == argument,
                    "scanner command differs from policy",
                )
            _require(
                argv[-1] == str(roots[0] / "src"), "scanner must inspect the bound source tree"
            )
    _unique(profiles, "stage profiles")
    return data


class PaladinResourcesRun:
    """Keep actual performance, wheel and scanner evidence under one frozen contract."""

    @_boundary
    def __init__(self, runtime: ManagedRuntime, *, contract: dict[str, Any]) -> None:
        """Detach and validate configuration without dispatching or writing."""
        self._runtime = runtime
        self._store = runtime._store
        self._contract = _validate(contract)
        self._digest = canonical_sha(self._contract)
        self._prefix = f"paladin-resources:{self._contract['run_id']}:"
        self._stages = {stage["stage_id"]: stage for stage in self._contract["stages"]}
        self._snapshot = Path(self._contract["snapshot_root"])
        self._output = Path(self._contract["output_root"])
        self._producer = Path(self._contract["producer_root"])

    def _context(self, *, active: bool = False) -> None:
        data = self._contract
        _require(
            self._runtime._wing == data["wing"]
            and (self._runtime._task_id is None or self._runtime._task_id == data["task_id"]),
            "runtime belongs to another resource task",
        )
        if isinstance(self._store, ScopedStore):
            self._store._authorize_complete_wing(data["wing"])
        task = json.loads(self._runtime._book.resume(data["wing"], data["task_id"], 262144))
        if task["status"] == "omitted":
            task = json.loads(
                self._runtime._book.resume(data["wing"], data["task_id"], task["required_chars"])
            )
        _require(task["status"] in {"ready", "terminal"}, "resource task evidence is unavailable")
        if active:
            self._runtime._check()
            _require(
                self._runtime._task_id == data["task_id"] and task["status"] == "ready",
                "resource task is not active",
            )
            _require(
                not self._store.transaction_active,
                "resource execution cannot use a caller transaction",
            )

    def _records(self) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        args = {
            "wing": self._contract["wing"],
            "room": self._runtime._room,
            "run_id": self._contract["run_id"],
            "task_id": self._contract["task_id"],
        }
        if isinstance(self._store, ScopedStore):
            projection = self._store._paladin_resources_records(**args)
        else:
            _require(
                isinstance(self._store, DrawerStore), "resource history requires a supported store"
            )
            projection = _paladin_resources_records(self._store, **args)
        records = {
            row["idempotency_key"][len(self._prefix) :]: row["result"]
            for row in projection["resources"]
        }
        for record in records.values():
            _require(
                record["request"]["contract_sha256"] == self._digest,
                "run is bound to a different contract",
            )
        if "plan" in records:
            _require(
                records["plan"]["request"]["contract"] == self._contract, "run contract has changed"
            )
        return records, projection["managed"]

    def _reference(self, drawer_id: int) -> dict[str, Any]:
        _require(type(drawer_id) is int and drawer_id > 0, "invalid resource evidence identity")
        sources = self._store._task_drawers([drawer_id])
        _require(drawer_id in sources, "resource evidence is unavailable")
        drawer, provenance = sources[drawer_id]
        now = datetime.now(UTC)
        _require(
            drawer.wing == self._contract["wing"]
            and drawer.room == self._runtime._room
            and provenance.sensitivity != Sensitivity.SECRET
            and (provenance.valid_from is None or provenance.valid_from <= now)
            and (provenance.valid_until is None or provenance.valid_until > now),
            "resource evidence is not currently accessible",
        )
        return {
            "drawer_id": drawer_id,
            "source_identity": self._store.portable_identity(drawer_id),
            "content_sha256": _sha(drawer.content.encode("utf-8")),
        }

    def _request(self, **extra: Any) -> dict[str, Any]:
        return {
            "run_id": self._contract["run_id"],
            "wing": self._contract["wing"],
            "room": self._runtime._room,
            "task_id": self._contract["task_id"],
            "contract_sha256": self._digest,
            **extra,
        }

    def _save(
        self, suffix: str, kind: str, request: dict[str, Any], value: dict[str, Any]
    ) -> dict[str, Any]:
        operation = f"paladin.resources.{kind}.v1"

        def append() -> dict[str, Any]:
            drawer = self._store.add(
                Drawer(
                    wing=self._contract["wing"],
                    room=self._runtime._room,
                    content=_json(
                        {
                            "operation": operation,
                            "request_sha256": request_hash(request),
                            "result": value,
                        }
                    ),
                    metadata={
                        "kind": "paladin.resources.record",
                        "run_id": self._contract["run_id"],
                        "operation": operation,
                    },
                )
            )
            if drawer.id is None:
                raise PaladinResourcesError("resource record has no persisted identity")
            return {"request": request, "result": value, "evidence": self._reference(drawer.id)}

        self._store.execute_once(
            idempotency_key=self._prefix + suffix,
            operation=operation,
            request=request,
            action=append,
        )
        records, _ = self._records()
        _require(suffix in records, "resource registry was not committed")
        return records[suffix]

    def _qualify(self) -> dict[str, Any]:
        diagnostics: list[str] = []
        unavailable = False

        def problem(code: str, *, missing: bool = False) -> None:
            nonlocal unavailable
            diagnostics.append(code)
            unavailable |= missing

        def verify(
            root: Path, files: list[dict[str, Any]], code: str, *, complete: bool = False
        ) -> None:
            try:
                if not root.is_dir():
                    problem(code, missing=True)
                    return
                if root.resolve() != root:
                    problem(code)
                expected = {item["path"] for item in files}
                if (
                    complete
                    and {
                        path.relative_to(root).as_posix()
                        for path in root.rglob("*")
                        if path.is_file()
                    }
                    != expected
                ):
                    problem(code)
                for item in files:
                    path = contained_path(root, item["path"])
                    if path != root / item["path"]:
                        problem(code)
                    if not path.is_file():
                        problem(code, missing=True)
                    elif _file_sha(path) != item["sha256"]:
                        problem(code)
            except (CairntirError, OSError, RuntimeError):
                problem(code, missing=True)

        data = self._contract
        _require(canonical_sha(data) == self._digest, "validated resource contract was mutated")
        verify(self._snapshot, data["inputs"], "INPUT_CHANGED", complete=True)
        verify(self._producer, data["producer_files"], "PRODUCER_CHANGED", complete=True)
        try:
            if not self._output.is_dir():
                problem("MISSING_ARTIFACT", missing=True)
            elif self._output.resolve() != self._output:
                problem("ARTIFACT_CHANGED")
        except (OSError, RuntimeError):
            problem("MISSING_ARTIFACT", missing=True)
        environment = data["environment"]
        if any(os.environ.get(key) != value for key, value in environment["values"].items()) or any(
            key in os.environ for key in environment["absent"]
        ):
            problem("PROFILE_MISMATCH")
        for stage in self._stages.values():
            command = stage["command"]
            configured = {**command, "executable_path": str(Path(command["argv"][0]).resolve())}
            if self._runtime._config["profiles"].get(stage["profile"]) != configured:
                problem("PROFILE_MISMATCH")
        for tool in data["tools"]:
            try:
                executable = Path(tool["executable"])
                if not executable.is_file():
                    problem("TOOL_UNAVAILABLE", missing=True)
                elif _file_sha(executable) != tool["sha256"]:
                    problem("TOOL_UNAVAILABLE")
                root = Path(tool["payload_root"])
                verify(root, tool["payload_files"], "TOOL_UNAVAILABLE")
                _version_record(
                    tool, _read_json(contained_path(root, tool["version_evidence"]["path"]))
                )
            except (CairntirError, OSError, ValueError, TypeError, KeyError, RuntimeError):
                problem("TOOL_UNAVAILABLE", missing=True)
        return {
            "status": "UNAVAILABLE" if unavailable else "STALE" if diagnostics else "CURRENT",
            "diagnostics": list(dict.fromkeys(diagnostics)),
        }

    def _action(self, action: object, stage: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(
            _record(action, "schema action_id ack_id profile claim predicted_outcome event_ids")
        )
        _require(
            value["schema"] == "cairntir.managed-action.v1"
            and value["profile"] == stage["profile"],
            "stage requires its configured managed action",
        )
        for key in ("action_id", "ack_id"):
            _uuid(value[key])
        for key in ("claim", "predicted_outcome"):
            _text(value[key], key)
        events = _list(value["event_ids"], minimum=1)
        for event in events:
            _uuid(event)
        _unique(events, "captured events")
        return value

    def _readiness(self, action: dict[str, Any]) -> None:
        brief = self._runtime._latest
        ack = next(
            (row for row in self._runtime._records("ack") if row["ack_id"] == action["ack_id"]),
            None,
        )
        _require(
            brief is not None
            and ack is not None
            and ack["brief_id"] == brief["brief_id"]
            and ack["epoch"] == self._runtime._epoch
            and ack["brief_sha256"] == brief["brief_sha256"],
            "action has no current committed acknowledgement",
        )
        if brief is None:
            raise PaladinResourcesError("action has no current managed brief")
        self._runtime._ack_state(brief)
        self._runtime._action_events(action)
        _require(not self._runtime._uncertain(), "an uncertain managed action prevents dispatch")

    def _closure(self, stage_id: str) -> list[dict[str, str]]:
        root = contained_path(self._output, stage_id)
        _require(
            root == self._output / stage_id and root.is_dir(),
            "stage artifact root is unavailable or aliased",
        )
        result = []
        for path in sorted(root.rglob("*")):
            _require(path.resolve() == path, "stage artifact path is aliased")
            if path.is_file():
                result.append(
                    {
                        "path": path.relative_to(self._output).as_posix(),
                        "sha256": _file_sha(path),
                    }
                )
            else:
                _require(path.is_dir(), "stage output contains a nonregular artifact")
        return result

    def _performance(self, artifact: Path) -> tuple[dict[str, Any], list[str]]:
        raw = _record(_read_json(artifact), "schema producer_sha256 python pid datasets")
        _require(raw["schema"] == "cairntir.q05-performance.v1", "invalid performance schema")
        producer = next(
            item
            for item in self._contract["producer_files"]
            if str(self._producer / item["path"]) in self._stages["performance"]["command"]["argv"]
        )
        _require(
            raw["producer_sha256"] == producer["sha256"], "performance producer identity differs"
        )
        _text(raw["python"], "performance Python identity")
        _integer(raw["pid"], 1, 2**63 - 1)
        policy = self._contract["policy"]
        expected = {
            item["size"]: item["expected_output_sha256"] for item in policy["expected_outputs"]
        }
        datasets = _list(raw["datasets"], minimum=1)
        _require(len(datasets) == len(expected), "performance datasets are incomplete")
        diagnostics: list[str] = []
        results = []
        seen: set[int] = set()
        for row in datasets:
            row = _record(
                row,
                "size oracle_sha256 wall_samples_ns profile_path profile_output_sha256 "
                "allocation_output_sha256 python_peak_bytes",
            )
            size = _integer(row["size"], 1, 2**63 - 1)
            _require(
                size in expected and size not in seen, "unexpected or duplicate performance dataset"
            )
            seen.add(size)
            samples = [
                _integer(value, 1, 2**63 - 1) for value in _list(row["wall_samples_ns"], minimum=1)
            ]
            _require(len(samples) == policy["samples"], "performance wall sample count differs")
            p95 = sorted(samples)[math.ceil(len(samples) * 0.95) - 1]
            peak = _integer(row["python_peak_bytes"], 1, 2**63 - 1)
            profile_path = contained_path(artifact.parent, row["profile_path"])
            _require(
                profile_path == artifact.parent / row["profile_path"], "profile path is aliased"
            )
            stats = pstats.Stats(str(profile_path))
            calls = sum(
                value[1]
                for key, value in cast(Any, stats).stats.items()
                if "'execute' of 'sqlite3.Connection'" in key[2]
            )
            _require(
                type(calls) is int and calls > 0, "profile has no actual SQLite execution calls"
            )
            for key in ("oracle_sha256", "profile_output_sha256", "allocation_output_sha256"):
                _digest(row[key])
                if row[key] != expected[size]:
                    diagnostics.append("FUNCTIONAL_ORACLE")
            if p95 > policy["wall_p95_ns"]:
                diagnostics.append("PERFORMANCE_WALL_BUDGET")
            if peak > policy["python_peak_bytes"]:
                diagnostics.append("PERFORMANCE_PYTHON_ALLOCATION_BUDGET")
            if calls > policy["profile_sql_calls"]:
                diagnostics.append("PERFORMANCE_SQL_CALL_BUDGET")
            results.append(
                {
                    "size": size,
                    "wall_samples_ns": samples,
                    "wall_p95_ns": p95,
                    "python_peak_bytes": peak,
                    "profile_sql_calls": calls,
                    "oracle_sha256": row["oracle_sha256"],
                }
            )
        launches = [
            json.loads(line, object_pairs_hook=_unique_object)
            for line in (artifact.parent / "launches.jsonl").read_bytes().splitlines()
        ]
        expected_launches = {
            (size, mode, ordinal)
            for size in expected
            for mode, ordinals in (
                (
                    "wall",
                    [
                        *[f"warmup-{index}" for index in range(policy["warmups"])],
                        *range(policy["samples"]),
                    ],
                ),
                ("profile", [0]),
                ("allocation", [0]),
            )
            for ordinal in ordinals
        }
        observed = set()
        for launch in launches:
            launch = _record(launch, "argv mode size ordinal exit_code")
            identity = (launch["size"], launch["mode"], launch["ordinal"])
            _require(
                identity in expected_launches and identity not in observed,
                "unexpected or duplicate measured child invocation",
            )
            observed.add(identity)
            _require(
                type(launch["exit_code"]) is int and launch["exit_code"] == 0,
                "measured child did not complete",
            )
            argv = _list(launch["argv"], minimum=4)
            _require(
                argv[0] == self._stages["performance"]["command"]["argv"][0]
                and argv[1:3] == ["-I", "-B"]
                and argv[3] == str(self._producer / producer["path"]),
                "measured child producer differs",
            )
            for flag, value in (
                ("--snapshot", str(self._snapshot)),
                ("--size", str(launch["size"])),
                ("--mode", launch["mode"]),
            ):
                _require(
                    argv.count(flag) == 1
                    and argv.index(flag) + 1 < len(argv)
                    and argv[argv.index(flag) + 1] == value,
                    "measured child arguments differ",
                )
            stem = f"child-{launch['size']}-{launch['mode']}-{launch['ordinal']}"
            child = _record(
                _read_json(artifact.parent / (stem + ".stdout")), "values python_peak_bytes"
            )
            values = _list(child["values"])
            _require(
                len(values) == policy["reads_per_sample"]
                and all(isinstance(value, str) for value in values),
                "measured child output is incomplete",
            )
            output_hash = _sha(
                json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )
            if output_hash != expected[launch["size"]]:
                diagnostics.append("FUNCTIONAL_ORACLE")
            _require(
                (artifact.parent / (stem + ".stderr")).is_file(),
                "measured child stderr is unavailable",
            )
        _require(observed == expected_launches, "actual child invocation inventory is incomplete")
        results.sort(key=lambda row: policy["dataset_sizes"].index(row["size"]))
        return {"datasets": results}, list(dict.fromkeys(diagnostics))

    def _bundle(self, artifact: Path) -> tuple[dict[str, Any], list[str]]:
        inputs = _files(self._contract["inputs"])
        members = [
            {"member": path.removeprefix("src/"), "source_path": path}
            for path in inputs
            if path.endswith(".py")
        ]
        _require(bool(members), "wheel has no declared Python source bindings")
        metrics = _stream_wheel(artifact, members, self._snapshot, inputs)
        diagnostics = []
        if metrics["compressed_bytes"] > self._contract["policy"]["bundle_compressed_bytes"]:
            diagnostics.append("BUNDLE_COMPRESSED_BUDGET")
        if metrics["uncompressed_bytes"] > self._contract["policy"]["bundle_uncompressed_bytes"]:
            diagnostics.append("BUNDLE_UNCOMPRESSED_BUDGET")
        return metrics, diagnostics

    def _security(self, artifact: Path, exit_code: int) -> tuple[dict[str, Any], list[str]]:
        findings = _list(_read_json(artifact))
        for item in findings:
            _require(
                isinstance(item, dict) and {"code", "filename", "location"} <= item.keys(),
                "malformed scanner finding",
            )
            _require(
                item["code"] in self._contract["policy"]["security_rules"],
                "scanner finding has an undeclared rule",
            )
            path = _absolute(item["filename"])
            _require(
                path.resolve() == path
                and path.is_relative_to(self._snapshot / "src")
                and path.relative_to(self._snapshot).as_posix() in _files(self._contract["inputs"]),
                "scanner finding is outside bound source",
            )
            location = _record(item["location"], "row column")
            for value in location.values():
                _integer(value, 1, 2**63 - 1)
        _require(
            (exit_code == 0 and not findings) or (exit_code == 1 and bool(findings)),
            "scanner exit contradicts its findings",
        )
        return {"findings": findings}, ["SECURITY_FINDING_S307"] if len(findings) > self._contract[
            "policy"
        ]["maximum_findings"] else []

    def _collect(
        self, stage_id: str, managed: dict[str, Any], evidence_ids: list[int]
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "stage_id": stage_id,
            "action_id": managed["action_id"],
            "status": "INCONCLUSIVE",
            "metrics": {},
            "diagnostics": [],
            "managed_result": deepcopy(managed),
            "artifacts": [],
            "evidence_ids": evidence_ids,
            "replayed": False,
        }
        qualification = self._qualify()
        if qualification["status"] != "CURRENT":
            receipt["diagnostics"] = qualification["diagnostics"]
            return receipt
        try:
            receipt["artifacts"] = self._closure(stage_id)
        except (CairntirError, OSError, RuntimeError):
            receipt["diagnostics"] = ["MISSING_ARTIFACT"]
            return receipt
        if (
            managed["status"] == "uncertain"
            or managed["timed_out"]
            or managed["output_truncated"]
            or managed["outcome_drawer_id"] is None
        ):
            receipt["diagnostics"] = ["EXECUTION_INCOMPLETE"]
            return receipt
        if (
            stage_id == "performance"
            and managed["exit_code"] != 0
            and "RuntimeError: FUNCTIONAL_ORACLE" in managed["stderr"]
        ):
            receipt.update(status="FAIL", diagnostics=["FUNCTIONAL_ORACLE"])
            return receipt
        if stage_id == "security" and managed["exit_code"] not in (0, 1):
            receipt["diagnostics"] = ["SCANNER_UNAVAILABLE"]
            return receipt
        if stage_id != "security" and managed["exit_code"] != 0:
            receipt["diagnostics"] = ["EXECUTION_INCOMPLETE"]
            return receipt
        artifact = contained_path(self._output, self._stages[stage_id]["artifacts"][0]["path"])
        if not artifact.is_file():
            receipt["diagnostics"] = ["MISSING_ARTIFACT"]
            return receipt
        try:
            if stage_id == "performance":
                metrics, diagnostics = self._performance(artifact)
            elif stage_id == "bundle":
                metrics, diagnostics = self._bundle(artifact)
            else:
                metrics, diagnostics = self._security(artifact, managed["exit_code"])
        except (
            CairntirError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
            EOFError,
            StopIteration,
            IndexError,
            csv.Error,
            zipfile.BadZipFile,
        ) as exc:
            code = {
                "performance": "INVALID_PERFORMANCE_ARTIFACT",
                "bundle": "INVALID_WHEEL",
                "security": "INVALID_SECURITY_ARTIFACT",
            }[stage_id]
            if stage_id == "bundle" and "wheel member differs from bound source" in str(exc):
                code = "WHEEL_SOURCE_MISMATCH"
            receipt["diagnostics"] = [code]
            return receipt
        qualification = self._qualify()
        if qualification["status"] != "CURRENT":
            receipt["diagnostics"] = qualification["diagnostics"]
            return receipt
        if self._closure(stage_id) != receipt["artifacts"]:
            receipt["diagnostics"] = ["ARTIFACT_CHANGED"]
            return receipt
        receipt.update(
            metrics=metrics, diagnostics=diagnostics, status="FAIL" if diagnostics else "PASS"
        )
        return receipt

    @staticmethod
    def _outcome(
        managed: list[dict[str, Any]], action_id: str
    ) -> tuple[dict[str, Any], list[int]] | None:
        for row in managed:
            if (
                row["_managed"]["operation"] in {"managed.outcome.v1", "managed.observation.v1"}
                and row["action_id"] == action_id
            ):
                return {key: value for key, value in row.items() if key != "_managed"} | {
                    "replayed": True
                }, row["_managed"]["evidence_ids"]
        return None

    @_boundary
    def execute(self, stage_id: str, action: dict[str, Any]) -> dict[str, Any]:
        """Prepare durably, dispatch once and retain authenticated resource evidence."""
        _require(stage_id in self._stages, "unknown resource stage")
        self._context()
        action = self._action(action, self._stages[stage_id])
        records, managed = self._records()
        suffix = f"stage:{stage_id}:"
        prepared = records.get(suffix + "prepare")
        result = records.get(suffix + "result")
        if prepared is not None:
            _require(
                prepared["request"]["action"] == action, "stage is bound to another managed action"
            )
            if result is not None:
                public: dict[str, Any] = deepcopy(result["result"])
                return public | {"replayed": True}
            recovered = self._outcome(managed, action["action_id"])
            if recovered is None:
                raise PaladinResourcesError(
                    "prepared action has no committed managed outcome and cannot relaunch"
                )
            self._context(active=True)
            managed_result, evidence_ids = recovered
            receipt = self._collect(stage_id, managed_result, evidence_ids)
            receipt["replayed"] = True
        else:
            self._context(active=True)
            qualification = self._qualify()
            _require(qualification["status"] == "CURRENT", ",".join(qualification["diagnostics"]))
            self._readiness(action)
            _require(
                not any(
                    row.get("action_id") == action["action_id"]
                    for row in self._runtime._records("dispatch")
                ),
                "managed action already belongs to another execution",
            )
            root = contained_path(self._output, stage_id)
            _require(
                root == self._output / stage_id and root.is_dir() and not any(root.iterdir()),
                "stage output must be a fresh unaliased directory",
            )
            if "plan" not in records:
                self._save(
                    "plan",
                    "plan",
                    self._request(contract=self._contract),
                    {"contract_sha256": self._digest},
                )
            prepared = self._save(
                suffix + "prepare",
                "prepare",
                self._request(stage_id=stage_id, action=action),
                {"status": "PREPARED", "action_id": action["action_id"]},
            )
            self._runtime.dispatch(action)
            _, managed = self._records()
            outcome = self._outcome(managed, action["action_id"])
            if outcome is None:
                raise PaladinResourcesError("managed dispatch has no committed outcome")
            managed_result, evidence_ids = outcome
            managed_result["replayed"] = False
            receipt = self._collect(stage_id, managed_result, evidence_ids)
        receipt["evidence_ids"] = list(
            dict.fromkeys([*receipt["evidence_ids"], prepared["evidence"]["drawer_id"]])
        )
        saved = self._save(
            suffix + "result",
            "result",
            self._request(stage_id=stage_id, preparation=prepared["evidence"]),
            receipt,
        )
        return deepcopy(saved["result"])

    @_boundary
    def report(self) -> dict[str, Any]:
        """Requalify current bytes while preserving each immutable historical receipt."""
        self._context()
        records, _ = self._records()
        qualification = self._qualify()
        stages = []
        for stage_id in _STAGES:
            record = records.get(f"stage:{stage_id}:result")
            receipt = deepcopy(record["result"]) if record is not None else None
            status = receipt["status"] if receipt is not None else "PENDING"
            if receipt is not None:
                try:
                    if self._closure(stage_id) != receipt["artifacts"]:
                        qualification["diagnostics"].append("ARTIFACT_CHANGED")
                        if qualification["status"] == "CURRENT":
                            qualification["status"] = "STALE"
                except (CairntirError, OSError, RuntimeError):
                    qualification["diagnostics"].append("MISSING_ARTIFACT")
                    qualification["status"] = "UNAVAILABLE"
            stages.append({"stage_id": stage_id, "status": status, "receipt": receipt})
        qualification["diagnostics"] = list(dict.fromkeys(qualification["diagnostics"]))
        complete = qualification["status"] == "CURRENT" and all(
            stage["status"] == "PASS" for stage in stages
        )
        self._context()
        return {
            "disposition": "COMPLETE" if complete else "BLOCKED",
            "qualification": qualification,
            "stages": stages,
        }
