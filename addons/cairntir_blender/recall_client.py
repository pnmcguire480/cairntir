"""Bounded print-recall protocol and an owned external interpreter job."""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import tempfile
import time
from contextlib import ExitStack, suppress
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

_REQUEST = "cairntir.blender-print-recall.request.v1"
_RESPONSE = "cairntir.blender-print-recall.response.v1"
_SELECTOR = re.compile(r"[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_REQUEST_FIELDS = {"schema", "request_id", "wing", "room", "query", "limit", "budget_chars"}
_REPLY_FIELDS = {
    "schema",
    "request",
    "observed_at",
    "status",
    "entries",
    "omitted",
    "eligible_count",
    "error",
}
_DRAWER_FIELDS = {
    "resource",
    "id",
    "wing",
    "room",
    "layer",
    "content",
    "content_length",
    "content_hash",
    "metadata",
    "created_at",
    "claim",
    "predicted_outcome",
    "observed_outcome",
    "delta",
    "supersedes_id",
    "belief_mass",
    "provenance",
    "instruction_authority",
    "suspicious",
    "security_signals",
    "saved_at",
    "portable_identity",
    "currentness",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _uuid(value: Any, version: int | None = None) -> None:
    _require(isinstance(value, str), "Invalid recall identity")
    parsed = UUID(value)
    _require(
        str(parsed) == value and (version is None or parsed.version == version),
        "Invalid recall identity",
    )


def _selector(value: str) -> str:
    _require(isinstance(value, str), "Invalid recall selector")
    normalized = value.strip().lower()
    _require(_SELECTOR.fullmatch(normalized) is not None, "Invalid recall selector")
    return normalized


def build_request(
    wing: str,
    material: str,
    query: str,
    *,
    request_id: str | None = None,
    limit: int = 5,
    budget_chars: int = 12000,
) -> dict[str, Any]:
    """Build a normalized request with finite selectors and output limits."""
    identity = str(uuid4()) if request_id is None else request_id
    _uuid(identity, 4)
    _require(
        isinstance(query, str) and bool(query.strip()) and len(query) <= 512, "Invalid recall query"
    )
    query.encode("utf-8")
    _require(type(limit) is int and 1 <= limit <= 10, "Invalid recall limit")
    _require(type(budget_chars) is int and 4096 <= budget_chars <= 16000, "Invalid recall budget")
    return {
        "schema": _REQUEST,
        "request_id": identity,
        "wing": _selector(wing),
        "room": _selector(material),
        "query": query,
        "limit": limit,
        "budget_chars": budget_chars,
    }


def _request(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == _REQUEST_FIELDS, "Invalid recall request")
    normalized = build_request(
        value["wing"],
        value["room"],
        value["query"],
        request_id=value["request_id"],
        limit=value["limit"],
        budget_chars=value["budget_chars"],
    )
    _require(normalized == value, "Noncanonical recall request")
    return normalized


def _utc(value: Any) -> None:
    _require(isinstance(value, str), "Invalid recall timestamp")
    stamp = datetime.fromisoformat(
        value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    )
    _require(stamp.utcoffset() == timedelta(0), "Recall timestamp must be UTC")


def _identity(value: dict[str, Any]) -> tuple[int, str]:
    identity = value.get("id")
    _require(type(identity) is int and identity > 0, "Invalid drawer id")
    _require(value.get("resource") == f"cairntir://drawer/{identity}", "Invalid drawer resource")
    _uuid(value.get("portable_identity"))
    digest = value.get("content_hash")
    _require(
        isinstance(digest, str) and _DIGEST.fullmatch(digest) is not None, "Invalid drawer hash"
    )
    return identity, value["portable_identity"]


def _drawer(value: Any, request: dict[str, Any]) -> tuple[int, str]:
    _require(isinstance(value, dict) and set(value) >= _DRAWER_FIELDS, "Incomplete recalled drawer")
    identity = _identity(value)
    content = value["content"]
    _require(isinstance(content, str), "Invalid recalled content")
    _require(
        type(value["content_length"]) is int and value["content_length"] == len(content),
        "Incomplete recalled content",
    )
    _require(
        hashlib.sha256(content.encode("utf-8")).hexdigest() == value["content_hash"],
        "Recalled content hash differs",
    )
    _require(
        value["wing"] == request["wing"] and value["room"] == request["room"],
        "Recalled drawer is outside the request",
    )
    metadata = value["metadata"]
    _require(
        isinstance(metadata, dict)
        and metadata.get("source") == "blender"
        and metadata.get("kind") == "print_outcome",
        "Recalled drawer is not a print outcome",
    )
    _require(
        "success" not in metadata or type(metadata["success"]) is bool, "Invalid recorded success"
    )
    _utc(value["created_at"])
    _utc(value["saved_at"])
    _require(value["saved_at"] == value["created_at"], "Saved date differs")
    _require(
        value["instruction_authority"] == "none"
        and isinstance(value["provenance"], dict)
        and isinstance(value["provenance"].get("trust"), str),
        "Invalid recalled provenance",
    )
    _require(
        value["layer"] in ("identity", "essential", "on_demand", "deep")
        and value["currentness"] in ("current", "historical", "unresolved"),
        "Invalid recalled classification",
    )
    _require(
        all(
            value[key] is None or isinstance(value[key], str)
            for key in ("claim", "predicted_outcome", "observed_outcome", "delta")
        ),
        "Invalid recorded outcome fields",
    )
    parent = value["supersedes_id"]
    _require(parent is None or (type(parent) is int and parent > 0), "Invalid predecessor identity")
    _require(
        type(value["belief_mass"]) in (int, float) and value["belief_mass"] >= 0,
        "Invalid belief mass",
    )
    _require(
        type(value["suspicious"]) is bool
        and isinstance(value["security_signals"], list)
        and all(isinstance(signal, str) for signal in value["security_signals"]),
        "Invalid security assessment",
    )
    return identity


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in items:
        _require(key not in result, "Duplicate recall JSON key")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise ValueError("Nonfinite recall JSON")


def decode_reply(raw: bytes, expected_request: dict[str, Any]) -> dict[str, Any]:
    """Validate the complete response without rewriting stored drawer evidence."""
    request = _request(expected_request)
    _require(isinstance(raw, bytes) and 0 < len(raw) <= 65536, "Invalid recall output size")
    try:
        reply = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        packed = json.dumps(reply, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        packed.encode("utf-8")
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Invalid recall JSON") from error
    _require(
        isinstance(reply, dict) and set(reply) == _REPLY_FIELDS, "Invalid recall response schema"
    )
    _require(
        reply["schema"] == _RESPONSE and _request(reply["request"]) == request,
        "Recall response does not match the request",
    )
    _require(len(packed) <= request["budget_chars"], "Recall response exceeds its budget")
    _utc(reply["observed_at"])
    entries, omitted = reply["entries"], reply["omitted"]
    _require(isinstance(entries, list) and isinstance(omitted, list), "Invalid recall entries")
    status = reply["status"]
    _require(
        status in ("ok", "empty", "omitted", "denied", "unavailable", "invalid"),
        "Invalid recall status",
    )
    if status in ("denied", "unavailable", "invalid"):
        error = reply["error"]
        _require(
            not entries and not omitted and reply["eligible_count"] is None,
            "Protected partial error result",
        )
        _require(
            isinstance(error, dict)
            and set(error) == {"code", "message"}
            and isinstance(error["code"], str)
            and 0 < len(error["code"]) <= 128
            and isinstance(error["message"], str),
            "Invalid recall error",
        )
        return reply
    count = reply["eligible_count"]
    _require(type(count) is int and count >= 0 and reply["error"] is None, "Invalid eligible count")
    _require(
        len(entries) + len(omitted) == min(count, request["limit"]),
        "Recall selection count differs",
    )
    _require(
        status == ("omitted" if omitted else "empty" if count == 0 else "ok"),
        "Recall status/count differs",
    )
    identities = []
    for entry in entries:
        _require(isinstance(entry, dict) and set(entry) == {"drawer"}, "Invalid recall entry")
        identities.append(_drawer(entry["drawer"], request))
    for item in omitted:
        _require(
            isinstance(item, dict)
            and set(item) == {"id", "resource", "portable_identity", "content_hash", "reason"}
            and item["reason"] == "BUDGET",
            "Invalid recall omission",
        )
        identities.append(_identity(item))
    _require(
        len({identity[0] for identity in identities}) == len(identities)
        and len({identity[1] for identity in identities}) == len(identities),
        "Duplicate recalled identity",
    )
    return reply


class _BasicLimits(ctypes.Structure):
    _fields_ = [
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
    _fields_ = [
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
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
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


class _WindowsJob:
    def __init__(self) -> None:
        self.assigned = False
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
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
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self._checked(self.kernel.CreateJobObjectW(None, None))
        try:
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000
            self._checked(
                self.kernel.SetInformationJobObject(
                    self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                )
            )
        except OSError:
            self.close()
            raise

    @staticmethod
    def _checked(value: Any) -> Any:
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def attach(self, process: subprocess.Popen[bytes]) -> None:
        self._checked(
            self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle)))
        )
        self.assigned = True
        native = ctypes.WinDLL("ntdll")
        native.NtResumeProcess.argtypes = [wintypes.HANDLE]
        native.NtResumeProcess.restype = ctypes.c_long
        if native.NtResumeProcess(wintypes.HANDLE(int(process._handle))) != 0:
            raise OSError("Could not resume the recall process")

    def active(self) -> int:
        info = _Accounting()
        self._checked(
            self.kernel.QueryInformationJobObject(
                self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None
            )
        )
        return info.ActiveProcesses

    def terminate(self) -> None:
        if self.active():
            self._checked(self.kernel.TerminateJobObject(self.handle, 1))

    def close(self) -> None:
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self._checked(self.kernel.CloseHandle(handle))


class ProcessJob:
    """Poll one bounded subprocess and close only its owned process tree."""

    def __init__(
        self,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        *,
        timeout: float = 60,
        max_output_bytes: int = 65536,
    ) -> None:
        """Start an owned Windows job or a fresh POSIX process session."""
        _require(
            type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 60,
            "Invalid recall deadline",
        )
        _require(
            type(max_output_bytes) is int and 0 < max_output_bytes <= 65536,
            "Invalid recall output cap",
        )
        _require(
            isinstance(argv, list) and bool(argv) and all(isinstance(value, str) for value in argv),
            "Invalid recall command",
        )
        self.closed = False
        self.pid = 0
        self._deadline = time.monotonic() + timeout
        self._maximum = max_output_bytes
        self._terminal: tuple[int, bytes, bytes] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._job: _WindowsJob | None = None
        self._streams = ExitStack()
        self._stdout = self._stderr = None
        try:
            self._stdout = self._streams.enter_context(tempfile.TemporaryFile())  # noqa: SIM115 - job-owned ExitStack spans polling.
            self._stderr = self._streams.enter_context(tempfile.TemporaryFile())  # noqa: SIM115 - job-owned ExitStack spans polling.
            options = (
                {"creationflags": subprocess.CREATE_NO_WINDOW | 0x4}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            if os.name == "nt":
                self._job = _WindowsJob()
            self._process = subprocess.Popen(  # noqa: S603 - internal argv; public launcher fixes the command.
                list(argv),
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=self._stdout,
                stderr=self._stderr,
                shell=False,
                **options,
            )
            self.pid = self._process.pid
            if self._job is not None:
                self._job.attach(self._process)
        except (OSError, ValueError):
            self.close()
            raise

    def _sizes(self) -> None:
        if any(
            os.fstat(stream.fileno()).st_size > self._maximum
            for stream in (self._stdout, self._stderr)
        ):
            raise ValueError("Recall output exceeded its limit")

    def _group_alive(self) -> bool:
        try:
            os.killpg(self.pid, 0)
        except ProcessLookupError:
            return False
        return True

    def _dispose(self, collect: bool = False) -> tuple[int, bytes, bytes] | None:
        if self.closed:
            return self._terminal
        deadline = time.monotonic() + 4.5
        try:
            process = self._process
            if process is not None:
                try:
                    if self._job is not None and self._job.assigned:
                        self._job.terminate()
                    elif os.name != "nt":
                        with suppress(ProcessLookupError):
                            os.killpg(self.pid, signal.SIGKILL)
                    elif process.poll() is None:
                        process.kill()
                    process.wait(timeout=max(0.01, deadline - time.monotonic()))
                    while (
                        self._job.active()
                        if self._job is not None
                        else os.name != "nt" and self._group_alive()
                    ):
                        if time.monotonic() >= deadline:
                            raise OSError("Recall process tree did not exit")
                        time.sleep(0.01)
                except subprocess.TimeoutExpired as error:
                    raise OSError("Recall process cleanup timed out") from error
                finally:
                    try:
                        if self._job is not None:
                            self._job.close()
                    finally:
                        if os.name == "nt":
                            process._handle.Close()
                if collect:
                    self._sizes()
                    self._stdout.seek(0)
                    self._stderr.seek(0)
                    self._terminal = (
                        process.returncode,
                        self._stdout.read(self._maximum),
                        self._stderr.read(self._maximum),
                    )
            return self._terminal
        finally:
            try:
                if self._job is not None:
                    self._job.close()
            finally:
                try:
                    self._streams.close()
                finally:
                    self.closed = True

    def poll(self) -> tuple[int, bytes, bytes] | None:
        """Return the terminal bytes, or raise a typed error after cleanup."""
        if self._terminal is not None or self.closed:
            return self._terminal
        try:
            self._sizes()
            if time.monotonic() >= self._deadline:
                raise TimeoutError("Recall deadline exceeded")
            if self._process.poll() is None:
                return None
            return self._dispose(collect=True)
        except (OSError, ValueError):
            self.close()
            raise

    def cancel(self) -> None:
        """Cancel this job and wait finitely for its owned descendants."""
        self._dispose()

    def close(self) -> None:
        """Close this job idempotently, cancelling unfinished work."""
        self._dispose()


def start_recall(
    python: str, home: str, grant_file: str, request: dict[str, Any], *, timeout: float = 60
) -> ProcessJob:
    """Launch only the bundled bridge with trusted connection paths."""
    request = _request(request)
    executable, directory, grant = Path(python), Path(home), Path(grant_file)
    _require(
        all(path.is_absolute() for path in (executable, directory, grant)),
        "Recall connection paths must be absolute",
    )
    executable, directory, grant = (
        executable.resolve(strict=True),
        directory.resolve(strict=True),
        grant.resolve(),
    )
    _require(executable.is_file() and directory.is_dir(), "Recall connection is unavailable")
    addon = Path(__file__).resolve().parent
    bridge = (addon / "recall_bridge.py").resolve(strict=True)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    cache = env.get("FASTEMBED_CACHE_PATH")
    _require(cache is None or Path(cache).is_absolute(), "FASTEMBED_CACHE_PATH must be absolute")
    env.update(
        CAIRNTIR_HOME=str(directory),
        CAIRNTIR_GRANT_FILE=str(grant),
        PYTHONSAFEPATH="1",
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    argv = [
        str(executable),
        "-I",
        "-B",
        str(bridge),
        "--request-id=" + request["request_id"],
        "--wing=" + request["wing"],
        "--material=" + request["room"],
        "--query=" + request["query"],
        "--limit=" + str(request["limit"]),
        "--budget-chars=" + str(request["budget_chars"]),
    ]
    return ProcessJob(argv, str(addon), env, timeout=timeout)
