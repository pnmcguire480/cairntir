"""Standalone, bounded ownership and artifact closure for the UI producer."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, ClassVar, cast
from uuid import UUID

_VERSION = "1"
_TOTAL_BYTES = 134217728
_PRIVATE_PATHS = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "TEMP",
    "TMP",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
)
_ABSENT_ENVIRONMENT = (
    "NODE_OPTIONS",
    "NODE_PATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "PLAYWRIGHT_DOWNLOAD_HOST",
    "CAIRNTIR_HOME",
    "CAIRNTIR_GRANT_FILE",
)
_LIMITS = {
    "request_bytes": 262144,
    "template_bytes": 131072,
    "selected_tool_manifest_bytes": 2097152,
    "selected_tool_file_rows": 4096,
    "selected_tool_total_bytes": 2147483648,
    "project_files": 128,
    "project_total_bytes": 8388608,
    "report_bytes": 1048576,
    "raw_json_bytes": 2097152,
    "png_bytes": 8388608,
    "decoded_png_pixels": 1024000,
    "stdout_bytes": 65536,
    "stderr_bytes": 65536,
    "attempt_regular_files": 4096,
    "attempt_total_bytes": 134217728,
    "selectors": 32,
    "checks": 64,
    "dom_nodes": 512,
    "ax_nodes": 1024,
    "network_events": 256,
    "producer_work_seconds": 90,
    "wrapper_total_seconds": 120,
    "managed_timeout_seconds": 150,
}
_TOOL_IDS = {
    "python",
    "node",
    "playwright",
    "playwright-core",
    "chrome",
    "pngjs",
    "pixelmatch",
    "worker",
    "producer",
}


def _require(value: object, message: str) -> None:
    if not value:
        raise ValueError(message)


def canonical(value: object) -> bytes:
    """Encode finite canonical JSON without a trailing newline."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == keys, "Unexpected object fields")
    return cast(dict[str, Any], value)


def _text(value: object, maximum: int = 512) -> str:
    _require(
        isinstance(value, str) and 0 < len(value) <= maximum and "\0" not in value, "Invalid text"
    )
    return cast(str, value)


def _number(value: object, minimum: float, maximum: float) -> float:
    _require(type(value) in (int, float), "Invalid number")
    result = float(cast(float, value))
    _require(math.isfinite(result) and minimum <= result <= maximum, "Number outside bounds")
    return result


def _integer(value: object, minimum: int, maximum: int) -> int:
    _require(type(value) is int and minimum <= value <= maximum, "Invalid integer")
    return cast(int, value)


def _digest(value: object) -> str:
    result = _text(value, 64)
    _require(re.fullmatch("[0-9a-f]{64}", result), "Invalid SHA256")
    return result


def _uuid(value: object) -> str:
    result = _text(value, 36)
    parsed = UUID(result)
    _require(str(parsed) == result and parsed.version == 4, "Invalid UUID4")
    return result


def _relative(value: object) -> str:
    result = _text(value)
    _require(
        not any(part in ("", ".", "..") for part in result.split("/"))
        and not any(char in result for char in "\\:\r\n")
        and not PurePosixPath(result).is_absolute(),
        "Unsafe relative path",
    )
    return result


def _path(value: object) -> Path:
    path = Path(_text(value, 2048))
    _require(path.is_absolute(), "Absolute path required")
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            info = ancestor.lstat()
            _require(
                not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse path refused",
            )
    return path.resolve()


def _deadline(deadline: float | None) -> None:
    _require(deadline is None or time.monotonic() < deadline, "UI worker deadline exceeded")


def _hash(path: Path, deadline: float | None = None) -> tuple[str, int]:
    path = _path(str(path))
    _require(path.is_file(), "Regular file required")
    size = path.stat().st_size
    _require(size <= 2147483648, "File exceeds selected byte cap")
    result = hashlib.sha256()
    observed = 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            _deadline(deadline)
            observed += len(block)
            _require(observed <= size, "Input grew while hashing")
            result.update(block)
    _require(observed == size == path.stat().st_size, "Input changed while hashing")
    return result.hexdigest(), observed


def _reference(value: object, cap: int = 2097152) -> dict[str, Any]:
    result = _object(value, {"path", "sha256", "bytes"})
    _path(result["path"])
    _digest(result["sha256"])
    _integer(result["bytes"], 0, cap)
    return result


def _verify(row: Mapping[str, Any], deadline: float | None = None) -> Path:
    path = _path(row["path"])
    digest, size = _hash(path, deadline)
    _require((digest, size) == (row["sha256"], row["bytes"]), "Pinned file changed")
    return path


def read_json(path: Path, limit: int) -> Any:
    """Read bounded UTF-8 JSON, refusing duplicate keys and nonfinite values."""

    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError("Nonfinite JSON: " + value)

    path = _path(str(path))
    _require(path.stat().st_size <= limit, "JSON byte cap exceeded")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) <= limit, "JSON byte cap exceeded")
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    stack = [(result, 0)]
    while stack:
        item, depth = stack.pop()
        _require(depth <= 64, "JSON depth cap exceeded")
        if isinstance(item, dict):
            stack.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            stack.extend((value, depth + 1) for value in item)
        elif isinstance(item, float):
            _require(math.isfinite(item), "Nonfinite JSON")
    return result


def _rows(value: object, maximum: int) -> list[Any]:
    _require(isinstance(value, list) and 0 < len(value) <= maximum, "Invalid row count")
    return cast(list[Any], value)


def _file_rows(value: object, maximum: int, total: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    names: list[str] = []
    size = 0
    for item in _rows(value, maximum):
        row = _object(item, {"path", "sha256", "bytes"})
        names.append(_relative(row["path"]))
        _digest(row["sha256"])
        size += _integer(row["bytes"], 0, total)
        rows.append(row)
    _require(
        names == sorted(names)
        and len({name.casefold() for name in names}) == len(names)
        and size <= total,
        "File inventory ordering, aliases or byte cap differ",
    )
    return rows


def validate_template(value: object) -> dict[str, Any]:
    """Validate and detach the fixed producer template without launching or writing."""
    result = _object(
        value,
        {
            "schema",
            "mode",
            "project",
            "output_root",
            "selected_tools",
            "render_policy",
            "checks",
            "baseline_reference",
        },
    )
    _require(
        result["schema"] == "cairntir.paladin-ui-producer-template.v1", "Wrong template schema"
    )
    _require(result["mode"] in ("capture-baseline", "compare"), "Wrong template mode")
    _path(result["output_root"])
    _reference(result["selected_tools"])
    project = _object(
        result["project"],
        {
            "project_id",
            "route_id",
            "state_id",
            "source_revision",
            "snapshot_root",
            "snapshot_sha256",
            "files",
            "entry_path",
        },
    )
    _require(
        re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]", _text(project["project_id"], 64)),
        "Invalid project identifier",
    )
    _require(
        re.fullmatch(r"[a-z0-9][a-z0-9._:-]*[a-z0-9]", _text(project["route_id"], 128))
        and project["state_id"] == "initial",
        "Invalid route/state",
    )
    _text(project["source_revision"], 128)
    _path(project["snapshot_root"])
    _digest(project["snapshot_sha256"])
    names: list[str] = []
    size = 0
    for item in _rows(project["files"], 128):
        row = _object(item, {"path", "sha256", "bytes", "media_type"})
        names.append(_relative(row["path"]))
        _digest(row["sha256"])
        size += _integer(row["bytes"], 0, 8388608)
        _require(
            row["media_type"]
            in {
                "text/html",
                "text/css",
                "text/javascript",
                "font/ttf",
                "image/png",
                "image/svg+xml",
                "text/plain",
            },
            "Unsupported project media",
        )
    _require(
        size <= 8388608
        and names == sorted(names)
        and len({name.casefold() for name in names}) == len(names),
        "Project inventory differs",
    )
    _require(_relative(project["entry_path"]) in names, "Project entry absent")
    _require(
        hashlib.sha256(canonical(project["files"])).hexdigest() == project["snapshot_sha256"],
        "Project inventory digest differs",
    )
    policy = _object(
        result["render_policy"],
        {
            "viewports",
            "locale",
            "timezone_id",
            "color_scheme",
            "reduced_motion",
            "font",
            "screenshot",
        },
    )
    _require(
        policy["viewports"]
        == [
            {"id": "mobile", "width": 375, "height": 800, "device_scale_factor": 1},
            {"id": "desktop", "width": 1280, "height": 800, "device_scale_factor": 1},
        ],
        "Unsupported viewports",
    )
    _require(
        (policy["locale"], policy["timezone_id"], policy["color_scheme"], policy["reduced_motion"])
        == ("en-US", "UTC", "light", "reduce"),
        "Unsupported rendering policy",
    )
    _require(
        policy["screenshot"]
        == {
            "type": "png",
            "full_page": False,
            "animations": "disabled",
            "caret": "hide",
            "masks": [],
        },
        "Unsupported screenshot policy",
    )
    font = _object(
        policy["font"],
        {
            "path",
            "sha256",
            "license_path",
            "license_sha256",
            "css_family",
            "platform_family",
            "postscript_name",
            "text_selectors",
        },
    )
    for key in ("path", "license_path"):
        _require(_relative(font[key]) in names, "Font input absent")
    for key in ("sha256", "license_sha256"):
        _digest(font[key])
    for key in ("css_family", "platform_family", "postscript_name"):
        _text(font[key])
    selectors = [_text(item) for item in _rows(font["text_selectors"], 16)]
    _require(len(set(selectors)) == len(selectors), "Duplicate font selectors")
    check_ids: list[str] = []
    families: set[str] = set()
    visuals = 0
    common = {"id", "kind", "family"}
    fields = {
        "document-equals": {"property", "expected"},
        "ax-role-name": {"selector", "role", "name"},
        "keyboard-tab-order": {"start_selector", "expected_focus"},
        "keyboard-key-state": {"key", "control", "panel", "expanded", "visible"},
        "required-visible": {"selectors", "tolerance_css_pixels"},
        "horizontal-overflow": {"maximum_css_pixels"},
        "rgba-diff": {
            "threshold",
            "includeAA",
            "allowed_diff_ratio",
            "alpha",
            "aaColor",
            "diffColor",
            "diffColorAlt",
            "diffMask",
            "checkerboard",
        },
    }
    for item in _rows(result["checks"], 64):
        _require(isinstance(item, dict), "Invalid check")
        check = cast(dict[str, Any], item)
        kind = _text(check.get("kind"), 64)
        _require(kind in fields, "Unsupported check kind")
        _object(check, common | fields[kind])
        check_ids.append(_text(check["id"], 128))
        _require(re.fullmatch(r"[a-z0-9][a-z0-9._:-]*[a-z0-9]", check_ids[-1]), "Invalid check ID")
        family = (
            "responsive"
            if kind in ("required-visible", "horizontal-overflow")
            else "visual"
            if kind == "rgba-diff"
            else "accessibility"
        )
        _require(check["family"] == family, "Check family differs")
        families.add(family)
        if kind == "document-equals":
            _require(check["property"] in ("language", "title"), "Unsupported document property")
            _text(check["expected"])
        elif kind == "ax-role-name":
            for key in ("selector", "role", "name"):
                _text(check[key])
            selectors.append(check["selector"])
        elif kind == "keyboard-tab-order":
            selectors.append(_text(check["start_selector"]))
            selectors.extend(_text(item) for item in _rows(check["expected_focus"], 16))
        elif kind == "keyboard-key-state":
            _require(check["key"] in ("Enter", "Space"), "Unsupported keyboard key")
            _require(
                type(check["expanded"]) is bool and type(check["visible"]) is bool,
                "Invalid keyboard state",
            )
            selectors.extend((_text(check["control"]), _text(check["panel"])))
        elif kind == "required-visible":
            chosen = [_text(item) for item in _rows(check["selectors"], 32)]
            _require(
                len(set(chosen)) == len(chosen) and check["tolerance_css_pixels"] == 1,
                "Unsupported visibility policy",
            )
            selectors.extend(chosen)
        elif kind == "horizontal-overflow":
            _require(check["maximum_css_pixels"] == 1, "Unsupported overflow policy")
        else:
            visuals += 1
            _require(
                {key: check[key] for key in fields[kind]}
                == {
                    "threshold": 0.1,
                    "includeAA": True,
                    "allowed_diff_ratio": 0.001,
                    "alpha": 0.1,
                    "aaColor": [255, 255, 0],
                    "diffColor": [255, 0, 0],
                    "diffColorAlt": None,
                    "diffMask": False,
                    "checkerboard": True,
                },
                "Unsupported pixel policy",
            )
    _require(
        len(set(check_ids)) == len(check_ids)
        and len(set(selectors)) <= 32
        and families == {"accessibility", "responsive", "visual"}
        and visuals == 1,
        "Incomplete or duplicate checks",
    )
    baseline = result["baseline_reference"]
    if result["mode"] == "capture-baseline":
        _require(baseline is None, "Capture cannot claim approval")
    else:
        row = _object(
            baseline,
            {
                "baseline_id",
                "generation",
                "revision_sha256",
                "approval_id",
                "approval",
                "manifest_file",
                "baseline_origin_snapshot_sha256",
            },
        )
        _uuid(row["baseline_id"])
        _uuid(row["approval_id"])
        _integer(row["generation"], 1, 2147483647)
        _digest(row["revision_sha256"])
        _digest(row["baseline_origin_snapshot_sha256"])
        evidence = _object(row["approval"], {"drawer_id", "source_identity", "content_sha256"})
        _integer(evidence["drawer_id"], 1, 9223372036854775807)
        _uuid(evidence["source_identity"])
        _digest(evidence["content_sha256"])
        _reference(row["manifest_file"])
        _require(
            row["manifest_file"]["sha256"] == row["revision_sha256"],
            "Approved manifest revision differs",
        )
    return cast(dict[str, Any], json.loads(canonical(result)))


class _BasicLimits(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        (name, ctypes.c_longlong)
        for name in (
            "TotalUserTime",
            "TotalKernelTime",
            "ThisPeriodTotalUserTime",
            "ThisPeriodTotalKernelTime",
        )
    ] + [
        (name, wintypes.DWORD)
        for name in (
            "TotalPageFaultCount",
            "TotalProcesses",
            "ActiveProcesses",
            "TotalTerminatedProcesses",
        )
    ]


def _checked(value: Any) -> Any:
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def _kernel() -> Any:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, arguments, result in (
        ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        (
            "SetInformationJobObject",
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        (
            "QueryInformationJobObject",
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
            wintypes.BOOL,
        ),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ):
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


class OwnedProcessError(RuntimeError):
    """Surface an ownership failure with its actual detached cleanup state."""

    def __init__(self, message: str, state: dict[str, Any]) -> None:
        """Retain a detached record rather than an owner handle."""
        super().__init__(message)
        self.state = cast(dict[str, Any], json.loads(canonical(state)))


class OwnedProcess:
    """Own one suspended Windows process and its descendants within one deadline."""

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: str,
        environment: dict[str, str],
        output_root: str,
        timeout_seconds: float,
        output_limit_bytes: int = 65536,
    ) -> None:
        """Validate and detach input without starting a process or writing."""
        _require(isinstance(argv, list) and 0 < len(argv) <= 32, "Invalid argv")
        self._argv = [_text(item, 2048) for item in argv]
        _path(self._argv[0])
        self._cwd = _path(cwd)
        _require(self._cwd.is_dir(), "Working directory absent")
        self._output = _path(output_root)
        _require(
            isinstance(environment, dict)
            and all(
                isinstance(key, str)
                and isinstance(value, str)
                and key
                and "=" not in key
                and "\0" not in key + value
                for key, value in environment.items()
            ),
            "Invalid environment",
        )
        self._environment = dict(environment)
        self._timeout = _number(timeout_seconds, 0.01, 120)
        self._limit = _integer(output_limit_bytes, 1, 65536)
        self._child: subprocess.Popen[bytes] | None = None
        self._job: Any = None
        self._kernel: Any = None
        self._threads: list[threading.Thread] = []
        self._sinks: list[BinaryIO] = []
        self._reader_errors: list[dict[str, str]] = []
        self._truncated = threading.Event()
        self._started = False
        self._terminal = False
        self._began = 0.0
        self._deadline = 0.0
        self._state: dict[str, Any] = {
            "argv": list(self._argv),
            "cwd": str(self._cwd),
            "started_at": None,
            "finished_at": None,
            "timeout_seconds": self._timeout,
            "elapsed_seconds": 0.0,
            "pid": None,
            "direct_process_handle": None,
            "job_handle": None,
            "suspended_creation": False,
            "assigned_owned_job": False,
            "direct_exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "output_truncated": False,
            "job_total_processes": 0,
            "job_active_processes": 0,
            "owned_tree_exit_observed": False,
            "job_handle_closed": False,
            "direct_process_handle_closed": False,
            "cleanup_uncertain": False,
            "errors": [],
        }

    @property
    def pid(self) -> int | None:
        """Return the actual child identity after creation."""
        return cast(int | None, self._state["pid"])

    @property
    def closed(self) -> bool:
        """Return true only after actual tree and handle closure."""
        return bool(
            self._terminal
            and self._state["owned_tree_exit_observed"]
            and self._state["job_handle_closed"]
            and self._state["direct_process_handle_closed"]
            and not self._state["cleanup_uncertain"]
        )

    def _copy(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(canonical(self._state)))

    def _error(self, stage: str, error: BaseException) -> None:
        self._state["errors"].append(
            {
                "stage": stage,
                "type": type(error).__name__,
                "message": str(error)[:4096],
            }
        )

    def _query(self) -> int:
        info: Any = _Accounting()
        _checked(
            self._kernel.QueryInformationJobObject(
                self._job, 1, ctypes.byref(info), ctypes.sizeof(info), None
            )
        )
        self._state.update(
            job_total_processes=int(info.TotalProcesses),
            job_active_processes=int(info.ActiveProcesses),
        )
        return int(info.ActiveProcesses)

    def _drain(self, stream: BinaryIO, sink: BinaryIO) -> None:
        count = 0
        try:
            while block := stream.read(4096):
                remaining = max(0, self._limit - count)
                sink.write(block[:remaining])
                count += len(block)
                if count > self._limit:
                    self._truncated.set()
        except (OSError, ValueError) as error:
            self._reader_errors.append(
                {
                    "stage": "wait",
                    "type": type(error).__name__,
                    "message": str(error)[:4096],
                }
            )
        finally:
            sink.close()
            stream.close()

    def start(self, on_assigned: Callable[[dict[str, Any]], None] | None = None) -> None:
        """Create once, assign its job, call the durable hook, then resume."""
        if self._started:
            raise RuntimeError("Owned process is one-shot")
        self._started = True
        self._began = time.monotonic()
        self._deadline = self._began + self._timeout
        self._state["started_at"] = datetime.now(UTC).isoformat()
        stage = "create"
        try:
            _require(os.name == "nt", "Owned UI processes require Windows")
            self._output.mkdir(parents=True, exist_ok=True)
            self._kernel = _kernel()
            self._job = _checked(self._kernel.CreateJobObjectW(None, None))
            self._state["job_handle"] = int(self._job)
            limits: Any = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000
            _checked(
                self._kernel.SetInformationJobObject(
                    self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                )
            )
            self._sinks.append((self._output / "stdout.txt").open("xb"))
            self._sinks.append((self._output / "stderr.txt").open("xb"))
            self._child = subprocess.Popen(  # noqa: S603 - validated argv, no shell, owned suspended job
                self._argv,
                cwd=self._cwd,
                env=self._environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW | 0x4,
            )
            handle = int(cast(Any, self._child)._handle)
            self._state.update(
                pid=self._child.pid,
                suspended_creation=True,
                direct_process_handle=handle,
            )
            stage = "assign"
            _checked(self._kernel.AssignProcessToJobObject(self._job, wintypes.HANDLE(handle)))
            self._state["assigned_owned_job"] = True
            self._query()
            for stream, sink in zip(
                (self._child.stdout, self._child.stderr), self._sinks, strict=True
            ):
                _require(stream is not None, "Owned output pipe absent")
                thread = threading.Thread(target=self._drain, args=(stream, sink), daemon=True)
                thread.start()
                self._threads.append(thread)
            if on_assigned is not None:
                on_assigned(self._copy())
            stage = "resume"
            native = ctypes.WinDLL("ntdll")
            native.NtResumeProcess.argtypes = [wintypes.HANDLE]
            native.NtResumeProcess.restype = ctypes.c_long
            status = native.NtResumeProcess(wintypes.HANDLE(handle))
            _require(status == 0, "NtResumeProcess failed: " + str(status))
        except BaseException as error:
            self._error(stage, error)
            self._finish()
            raise OwnedProcessError("Owned process start failed", self._copy()) from error

    def _finish(self) -> dict[str, Any]:
        if self._terminal:
            return self._copy()
        try:
            if self._child is not None:
                if self._state["assigned_owned_job"]:
                    if self._query():
                        _checked(self._kernel.TerminateJobObject(self._job, 124))
                    while self._query() and time.monotonic() < self._deadline:
                        time.sleep(0.01)
                    self._state["owned_tree_exit_observed"] = (
                        self._state["job_active_processes"] == 0
                    )
                elif self._child.poll() is None:
                    self._child.kill()
                self._state["direct_exit_code"] = self._child.wait(
                    timeout=max(0.01, self._deadline - time.monotonic())
                )
            for thread in self._threads:
                thread.join(timeout=max(0, self._deadline - time.monotonic()))
            _require(
                not any(thread.is_alive() for thread in self._threads), "Owned output did not close"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._error("cleanup", error)
            self._state["cleanup_uncertain"] = True
        finally:
            self._state["errors"].extend(self._reader_errors)
            self._state["output_truncated"] = self._truncated.is_set()
            for sink in self._sinks:
                if not sink.closed and not any(thread.is_alive() for thread in self._threads):
                    sink.close()
            if self._job is not None:
                try:
                    _checked(self._kernel.CloseHandle(self._job))
                    self._state["job_handle_closed"] = True
                except OSError as error:
                    self._error("close", error)
            else:
                self._state["job_handle_closed"] = True
            if self._child is not None:
                try:
                    cast(Any, self._child)._handle.Close()
                    self._state["direct_process_handle_closed"] = True
                except OSError as error:
                    self._error("close", error)
            else:
                self._state["direct_process_handle_closed"] = True
            self._state.update(
                finished_at=datetime.now(UTC).isoformat(),
                elapsed_seconds=time.monotonic() - self._began,
            )
            self._state["cleanup_uncertain"] = bool(
                self._state["cleanup_uncertain"]
                or not self._state["owned_tree_exit_observed"]
                or not self._state["job_handle_closed"]
                or not self._state["direct_process_handle_closed"]
            )
            self._terminal = True
        return self._copy()

    def poll(self) -> dict[str, Any] | None:
        """Return immutable terminal state after exit, deadline or output truncation."""
        _require(self._started, "Owned process was not started")
        if self._terminal:
            return self._copy()
        _require(self._child is not None, "Owned child absent")
        child = cast(subprocess.Popen[bytes], self._child)
        reserve = min(2.0, max(0.2, self._timeout / 5))
        if child.poll() is None and not self._truncated.is_set():
            if time.monotonic() < self._deadline - reserve:
                return None
            self._state["timed_out"] = True
        return self._finish()

    def cancel(self) -> dict[str, Any]:
        """Cancel only this live owned tree without resetting its deadline."""
        if self._terminal:
            return self._copy()
        _require(self._started, "Owned process was not started")
        self._state["cancelled"] = True
        return self._finish()

    def close(self) -> dict[str, Any]:
        """Close idempotently, cancelling a live process if necessary."""
        return self._copy() if self._terminal else self.cancel()


def _inventory(root: Path, deadline: float, omit: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending = [root]
    directories = total = 0
    while pending:
        directory = pending.pop()
        directories += 1
        _require(directories <= 8192, "Directory count cap exceeded")
        with os.scandir(directory) as children:
            for entry in children:
                _deadline(deadline)
                path = _path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                else:
                    _require(entry.is_file(follow_symlinks=False), "Nonregular output refused")
                    if relative == omit:
                        continue
                    size = path.stat().st_size
                    total += size
                    _require(
                        len(rows) < 4096 and total <= _TOTAL_BYTES, "Attempt byte/file cap exceeded"
                    )
                    digest, observed = _hash(path, deadline)
                    rows.append({"path": relative, "sha256": digest, "bytes": observed})
    rows.sort(key=lambda row: row["path"])
    _require(len({row["path"].casefold() for row in rows}) == len(rows), "Output path alias")
    return rows


def _save(path: Path, value: object, cap: int = 2097152) -> None:
    raw = canonical(value)
    _require(len(raw) <= cap, "Output JSON cap exceeded")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _tools(template: dict[str, Any], deadline: float) -> dict[str, dict[str, Any]]:
    path = _verify(template["selected_tools"], deadline)
    manifest = _object(read_json(path, 2097152), {"schema", "tools", "packaged_chromium_version"})
    _require(
        manifest["schema"] == "cairntir.paladin-ui-tools.v1"
        and manifest["packaged_chromium_version"] == "151.0.7922.34",
        "Wrong selected tools",
    )
    tools: dict[str, dict[str, Any]] = {}
    count = total = 0
    for item in _rows(manifest["tools"], 9):
        tool = _object(item, {"id", "root", "entry_path", "version", "files"})
        _require(tool["id"] in _TOOL_IDS and tool["id"] not in tools, "Tool identity differs")
        root = _path(tool["root"])
        _text(tool["version"])
        rows = _file_rows(tool["files"], 4096, 2147483648)
        count += len(rows)
        total += sum(row["bytes"] for row in rows)
        _require(count <= 4096 and total <= 2147483648, "Selected tool cap exceeded")
        _require(
            _relative(tool["entry_path"]) in {row["path"] for row in rows}, "Tool entry absent"
        )
        for row in rows:
            file = _path(str(root / row["path"]))
            _require(file.is_relative_to(root), "Tool file escaped")
            _verify({**row, "path": str(file)}, deadline)
        tools[tool["id"]] = tool
    _require(set(tools) == _TOOL_IDS, "Incomplete selected tools")
    return tools


def _tool_observation(tool: dict[str, Any], version: str) -> dict[str, Any]:
    path = _path(str(Path(tool["root"]) / tool["entry_path"]))
    _require(tool["version"] == version, "Actual tool version differs")
    return {
        "id": tool["id"],
        "entry_path": str(path),
        "entry_sha256": _hash(path)[0],
        "version": version,
    }


def _project(template: dict[str, Any], deadline: float) -> None:
    project = template["project"]
    root = _path(project["snapshot_root"])
    actual = _inventory(root, deadline)
    expected = [{key: row[key] for key in ("path", "sha256", "bytes")} for row in project["files"]]
    _require(actual == expected, "Complete project snapshot changed")
    font = template["render_policy"]["font"]
    for path_key, hash_key in (("path", "sha256"), ("license_path", "license_sha256")):
        _require(_hash(root / font[path_key], deadline)[0] == font[hash_key], "Font input differs")


def _environment(runtime: Path) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
        if key in os.environ
    }
    for name in _PRIVATE_PATHS:
        path = runtime / name.lower()
        path.mkdir()
        environment[name] = str(path)
    system = Path(os.environ["SYSTEMROOT"])
    environment.update(
        PATH=os.pathsep.join((str(system / "System32"), str(system))),
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1",
    )
    return environment


def main() -> int:
    """Run one validated producer and emit only its bounded closure references."""
    began = time.monotonic()
    deadline = began + 120
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--template-sha256", required=True)
    args = parser.parse_args()
    job: OwnedProcess | None = None
    try:
        request_path = _path(str(args.request))
        template_path = _path(str(args.template))
        _require(
            _hash(template_path, deadline)[0] == _digest(args.template_sha256),
            "Template hash differs",
        )
        template = validate_template(read_json(template_path, 131072))
        request = _object(
            read_json(request_path, 262144),
            {
                "schema",
                "run_id",
                "attempt_id",
                "action_id",
                "contract_sha256",
                "template_sha256",
                "template",
            },
        )
        _require(request["schema"] == "cairntir.paladin-ui-producer.v1", "Wrong request schema")
        for key in ("run_id", "attempt_id", "action_id"):
            _uuid(request[key])
        _digest(request["contract_sha256"])
        _require(
            request["template_sha256"] == args.template_sha256 and request["template"] == template,
            "Request template differs",
        )
        _require(request_path.read_bytes() == canonical(request), "Request is not canonical")
        root = _path(template["output_root"])
        _require(request_path == root / "request.json", "Wrong prepared request path")
        cache = _path(str(root / "runtime/python-cache"))
        _require(
            sys.flags.isolated
            and sys.dont_write_bytecode
            and not sys.flags.optimize
            and sys.pycache_prefix == str(cache)
            and not cache.exists(),
            "Python runtime/cache flags differ",
        )
        tools = _tools(template, deadline)
        _project(template, deadline)
        python = _tool_observation(tools["python"], ".".join(map(str, sys.version_info[:3])))
        _require(
            Path(python["entry_path"]) == Path(sys.executable).resolve(), "Wrong Python origin"
        )
        worker = _tool_observation(tools["worker"], _VERSION)
        _require(Path(worker["entry_path"]) == Path(__file__).resolve(), "Wrong worker origin")
        operations, runtime = root / "operations", root / "runtime"
        operations.mkdir()
        runtime.mkdir()
        environment = _environment(runtime)
        node = _path(str(Path(tools["node"]["root"]) / tools["node"]["entry_path"]))
        producer = _path(str(Path(tools["producer"]["root"]) / tools["producer"]["entry_path"]))
        _require(tools["producer"]["version"] == _VERSION, "Wrong producer protocol version")
        argv = [str(node), str(producer), "--request", str(request_path)]
        identity = {
            key: request[key]
            for key in ("run_id", "attempt_id", "action_id", "contract_sha256", "template_sha256")
        }
        identity["request_sha256"] = _hash(request_path, deadline)[0]

        def ownership(state: dict[str, Any], phase: str) -> dict[str, Any]:
            prefix_state = (
                "ABSENT" if not cache.exists() else "NONEMPTY" if any(cache.iterdir()) else "EMPTY"
            )
            observation = {
                **python,
                "isolated": bool(sys.flags.isolated),
                "dont_write_bytecode": sys.dont_write_bytecode,
                "optimize": sys.flags.optimize,
                "pycache_prefix": str(cache),
                "cache_prefix_state": prefix_state,
            }
            return {
                "schema": "cairntir.paladin-ui-ownership.v1",
                "phase": phase,
                **identity,
                **state,
                "python": observation,
                "worker": worker,
            }

        controls = {
            "values": {
                name: environment[name]
                for name in (*_PRIVATE_PATHS, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD")
            },
            "absent": list(_ABSENT_ENVIRONMENT),
        }
        _require(
            all(name not in environment for name in _ABSENT_ENVIRONMENT),
            "Forbidden child environment routing",
        )
        _save(
            operations / "INVOCATION.json",
            {
                "schema": "cairntir.paladin-ui-invocation.v1",
                **identity,
                "selected_tools_sha256": template["selected_tools"]["sha256"],
                "argv": argv,
                "cwd": template["project"]["snapshot_root"],
                "environment_controls": controls,
                "limits": _LIMITS,
            },
        )
        job = OwnedProcess(
            argv,
            cwd=template["project"]["snapshot_root"],
            environment=environment,
            output_root=str(operations),
            timeout_seconds=max(0.01, deadline - time.monotonic() - 8),
        )
        job.start(
            lambda state: _save(operations / "OWNERSHIP-START.json", ownership(state, "START"))
        )
        terminal = job.poll()
        while terminal is None:
            time.sleep(0.01)
            terminal = job.poll()
        _tools(template, deadline)
        _project(template, deadline)
        _require(not cache.exists() or not any(cache.iterdir()), "Python cache changed")
        terminal_ownership = ownership(terminal, "EXIT")
        _save(operations / "OWNERSHIP-EXIT.json", terminal_ownership)
        report_path = root / "producer/ui-result.json"
        report = read_json(report_path, 1048576)
        _require(
            isinstance(report, dict)
            and report.get("status") == "COMPLETE"
            and all(report.get(key) == value for key, value in identity.items()),
            "Producer report binding differs",
        )
        rows = _inventory(root, deadline, "operations/CLOSURE.json")
        _require(len(rows) <= 4095, "Closure file cap exceeded")
        closure = {
            "schema": "cairntir.paladin-ui-closure.v1",
            **{
                key: identity[key]
                for key in ("run_id", "attempt_id", "action_id", "request_sha256")
            },
            "files": rows,
            "file_count": len(rows),
            "total_bytes": sum(row["bytes"] for row in rows),
        }
        _save(operations / "CLOSURE.json", closure, 8388608)
        complete = _inventory(root, deadline)
        _require(
            [row for row in complete if row["path"] != "operations/CLOSURE.json"] == rows,
            "Closed payload changed",
        )
        by_path = {row["path"]: row for row in complete}
        summary = {
            "schema": "cairntir.paladin-ui-worker-summary.v1",
            **identity,
            "report": by_path["producer/ui-result.json"],
            "ownership": by_path["operations/OWNERSHIP-EXIT.json"],
            "closure": by_path["operations/CLOSURE.json"],
        }
        valid = bool(
            terminal["direct_exit_code"] == 0
            and terminal["owned_tree_exit_observed"]
            and terminal["job_active_processes"] == 0
            and terminal["job_handle_closed"]
            and terminal["direct_process_handle_closed"]
            and not terminal["cleanup_uncertain"]
            and not terminal["timed_out"]
            and not terminal["cancelled"]
            and not terminal["output_truncated"]
            and not terminal["errors"]
        )
        print(canonical(summary).decode(), flush=True)
        exit_code = 0 if valid else 1
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        if job is not None:
            job.close()
        print(type(error).__name__ + ": " + str(error), file=sys.stderr, flush=True)
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
