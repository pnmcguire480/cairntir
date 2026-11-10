"""Scoped, durable UI measurements and independently reviewed image baselines."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import struct
import zlib
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from cairntir.access import AccessDenied, ScopedStore, _paladin_ui_records
from cairntir.durability import request_hash
from cairntir.errors import CairntirError
from cairntir.managed import ManagedRuntime
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer, _validate_ident
from cairntir.provenance import Sensitivity


class PaladinUIError(CairntirError):
    """The UI contract or its authenticated evidence is unavailable or inconsistent."""


_P = ParamSpec("_P")
_T = TypeVar("_T")


def _boundary(function: Callable[_P, _T]) -> Callable[_P, _T]:
    @wraps(function)
    def call(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return function(*args, **kwargs)
        except (AccessDenied, PaladinUIError):
            raise
        except (
            CairntirError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            RuntimeError,
            StopIteration,
            OverflowError,
            struct.error,
            zlib.error,
        ) as exc:
            raise PaladinUIError(str(exc)) from exc

    return call


def _need(value: bool, message: str = "invalid UI evidence") -> None:
    if not value:
        raise PaladinUIError(message)


def _record(value: object, keys: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise PaladinUIError("invalid UI record fields")
    return value


def _finite(value: object, depth: int = 0) -> None:
    _need(depth <= 64, "JSON depth limit")
    if isinstance(value, dict):
        for key, child in value.items():
            _need(isinstance(key, str) and "\x00" not in key, "invalid JSON key")
            _finite(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _finite(child, depth + 1)
    else:
        _need(
            value is None
            or type(value) in (str, int, bool)
            or (type(value) is float and math.isfinite(value)),
            "invalid JSON value",
        )


def _canonical(value: object, limit: int = 2097152) -> bytes:
    _finite(value)
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    _need(len(data) <= limit, "JSON byte limit")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: object) -> str:
    return _sha(_canonical(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        _need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _parse(data: bytes, limit: int) -> Any:
    _need(len(data) <= limit, "JSON byte limit")
    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(PaladinUIError("nonfinite JSON")),
    )
    _finite(value)
    return value


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise PaladinUIError("invalid UUID")
    parsed = UUID(value)
    _need(str(parsed) == value and parsed.version == 4, "expected canonical UUID4")
    return value


def _ident(value: object) -> str:
    if not isinstance(value, str):
        raise PaladinUIError("invalid identifier")
    _validate_ident(value, "UI identifier")
    return value


def _path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PaladinUIError("invalid absolute path")
    path = Path(value)
    _need(
        path.is_absolute() and str(path) == value and path.resolve() == path,
        "path must be absolute and unaliased",
    )
    for current in (path, *path.parents):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            _need(
                not stat.S_ISLNK(info.st_mode)
                and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "reparse path refused",
            )
    return path


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or any(x in value for x in ("\\", ":", "\x00")):
        raise PaladinUIError("invalid relative path")
    parts = value.split("/")
    _need(
        all(part not in ("", ".", "..") and not part.endswith((".", " ")) for part in parts),
        "invalid relative path",
    )
    return value


def _inside(root: Path, relative: str) -> Path:
    path = _path(str(root / _relative(relative)))
    _need(path.is_relative_to(root), "path escapes root")
    return path


def _file_hash(path: Path, limit: int) -> tuple[str, int]:
    _path(str(path))
    info = path.stat()
    _need(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "file type or byte limit")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(min(1048576, limit - total + 1)):
            total += len(chunk)
            _need(total <= limit, "file byte limit")
            digest.update(chunk)
    after = path.stat()
    _need(
        total == info.st_size == after.st_size and info.st_mtime_ns == after.st_mtime_ns,
        "file changed while reading",
    )
    return digest.hexdigest(), total


def _read(path: Path, limit: int = 2097152) -> Any:
    _file_hash(path, limit)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return _parse(data, limit)


def _reference(path: Path, limit: int = 134217728) -> dict[str, Any]:
    digest, size = _file_hash(path, limit)
    return {"path": str(path), "sha256": digest, "bytes": size}


def _absolute_file(value: object, limit: int = 134217728) -> Path:
    row = _record(value, "path sha256 bytes")
    _need(
        type(row["bytes"]) is int
        and 0 <= row["bytes"] <= limit
        and isinstance(row["sha256"], str)
        and re.fullmatch("[0-9a-f]{64}", row["sha256"]) is not None
    )
    path = _path(row["path"])
    _need(_reference(path, limit) == row, "file identity changed")
    return path


def _inventory(root: Path, max_files: int, max_bytes: int) -> list[dict[str, Any]]:
    _path(str(root))
    _need(root.is_dir(), "missing file root")
    rows: list[dict[str, Any]] = []
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            _path(str(Path(directory) / name))
        for name in names:
            path = _path(str(Path(directory) / name))
            digest, size = _file_hash(path, max_bytes - total)
            total += size
            rows.append(
                {"path": path.relative_to(root).as_posix(), "sha256": digest, "bytes": size}
            )
            _need(len(rows) <= max_files and total <= max_bytes, "file inventory limit")
    rows.sort(key=lambda row: row["path"])
    _need(len({row["path"].casefold() for row in rows}) == len(rows), "aliased file inventory")
    return rows


def _verify_files(root: Path, rows: object, *, complete: bool, count: int, size: int) -> None:
    if not isinstance(rows, list) or not 0 < len(rows) <= count:
        raise PaladinUIError("invalid file inventory")
    paths, total = [], 0
    for row in rows:
        _need(
            isinstance(row, dict)
            and set(row) in ({"path", "sha256", "bytes"}, {"path", "sha256", "bytes", "media_type"})
        )
        relative = _relative(row["path"])
        digest, amount = _file_hash(_inside(root, relative), size - total)
        _need(
            type(row["bytes"]) is int and (digest, amount) == (row["sha256"], row["bytes"]),
            "input file changed",
        )
        paths.append(relative)
        total += amount
    _need(
        paths == sorted(paths) and len({path.casefold() for path in paths}) == len(paths),
        "file inventory must be unique and sorted",
    )
    if complete:
        actual = _inventory(root, count, size)
        _need(
            actual == [{key: row[key] for key in ("path", "sha256", "bytes")} for row in rows],
            "input file set changed",
        )


def _schema(value: object, schema: dict[str, Any] | bool, depth: int = 0) -> None:
    _need(depth <= 96, "wire schema depth")
    if schema is True:
        return
    if schema is False:
        raise PaladinUIError("wire value refused")
    if "$ref" in schema:
        _schema(value, _WIRE[schema["$ref"].rsplit("/", 1)[1]], depth + 1)
        return
    types = schema.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        matches = {
            "null": value is None,
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "boolean": type(value) is bool,
            "integer": type(value) is int,
            "number": type(value) in (int, float),
        }
        _need(any(matches.get(kind, False) for kind in types), "wire value type")
    if "const" in schema:
        _need(_canonical(value) == _canonical(schema["const"]), "wire constant")
    if "enum" in schema:
        _need(
            any(type(value) is type(item) and value == item for item in schema["enum"]), "wire enum"
        )
    if isinstance(value, str):
        _need(
            schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 2147483648)
            and "\x00" not in value,
            "wire string",
        )
        if "pattern" in schema:
            _need(re.search(schema["pattern"], value) is not None, "wire string pattern")
        if schema.get("format") == "uuid":
            _uuid(value)
        if schema.get("format") == "date-time":
            _need(
                datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None,
                "wire timestamp",
            )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _need(math.isfinite(value), "wire finite number")
        if "minimum" in schema:
            _need(value >= schema["minimum"], "wire number bound")
        if "maximum" in schema:
            _need(value <= schema["maximum"], "wire number bound")
        if "exclusiveMinimum" in schema:
            _need(value > schema["exclusiveMinimum"], "wire number bound")
        if "exclusiveMaximum" in schema:
            _need(value < schema["exclusiveMaximum"], "wire number bound")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        _need(set(schema.get("required", ())) <= set(value), "wire required field")
        for key, child in value.items():
            if key in properties:
                _schema(child, properties[key], depth + 1)
            elif "additionalProperties" in schema:
                _schema(child, schema["additionalProperties"], depth + 1)
    if isinstance(value, list):
        _need(
            schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 2147483648),
            "wire array bound",
        )
        prefix = schema.get("prefixItems", ())
        for index, child in enumerate(value):
            selected = prefix[index] if index < len(prefix) else schema.get("items", True)
            _schema(child, selected, depth + 1)
        if schema.get("uniqueItems"):
            _need(len({_canonical(item) for item in value}) == len(value), "wire duplicate item")
    if "oneOf" in schema:
        successful = 0
        for option in schema["oneOf"]:
            try:
                _schema(value, option, depth + 1)
            except PaladinUIError:
                continue
            successful += 1
        _need(successful == 1, "wire union")
    for option in schema.get("allOf", ()):
        _schema(value, option, depth + 1)
    if "if" in schema:
        try:
            _schema(value, schema["if"], depth + 1)
        except PaladinUIError:
            branch = schema.get("else", True)
        else:
            branch = schema.get("then", True)
        _schema(value, branch, depth + 1)


def _wire(kind: str, value: object) -> None:
    _finite(value)
    _schema(value, _WIRE[kind])


def _png(path: Path, width: int, height: int) -> bytes:
    _file_hash(path, 8388608)
    data = path.read_bytes()
    _need(data.startswith(b"\x89PNG\r\n\x1a\n") and width * height <= 1024000, "invalid PNG")
    offset, compressed, channels, ended = 8, bytearray(), None, False
    while offset < len(data):
        _need(offset + 12 <= len(data), "truncated PNG")
        (length,) = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4 : offset + 8]
        _need(offset + length + 12 <= len(data), "truncated PNG chunk")
        body = data[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack_from(">I", data, offset + 8 + length)
        _need(zlib.crc32(kind + body) & 0xFFFFFFFF == crc, "PNG CRC mismatch")
        if offset == 8:
            _need(kind == b"IHDR" and length == 13, "missing PNG header")
            w, h, bit, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            _need(
                (w, h) == (width, height)
                and bit == 8
                and color in (2, 6)
                and (compression, filtering, interlace) == (0, 0, 0),
                "unsupported PNG dimensions or encoding",
            )
            channels = 4 if color == 6 else 3
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            _need(length == 0 and offset + 12 == len(data), "invalid PNG end")
            ended = True
        else:
            _need(bool(kind[0] & 32) or kind in (b"PLTE",), "unsupported PNG critical chunk")
        offset += length + 12
    _need(ended and channels is not None, "incomplete PNG")
    if channels is None:
        raise PaladinUIError("missing PNG channels")
    stride = width * channels
    expected = height * (stride + 1)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, expected + 1)
    _need(
        len(raw) == expected
        and decoder.eof
        and not decoder.unused_data
        and not decoder.unconsumed_tail,
        "invalid PNG decoded length",
    )
    result, previous, cursor = bytearray(), bytearray(stride), 0
    for _ in range(height):
        filter_kind, row = raw[cursor], bytearray(raw[cursor + 1 : cursor + 1 + stride])
        cursor += stride + 1
        _need(filter_kind <= 4, "invalid PNG filter")
        if filter_kind:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = previous[i]
                upper_left = previous[i - channels] if i >= channels else 0
                if filter_kind == 1:
                    add = left
                elif filter_kind == 2:
                    add = up
                elif filter_kind == 3:
                    add = (left + up) // 2
                else:
                    estimate = left + up - upper_left
                    a, b, c = abs(estimate - left), abs(estimate - up), abs(estimate - upper_left)
                    add = left if a <= b and a <= c else up if b <= c else upper_left
                row[i] = (row[i] + add) & 255
        previous = row
        if channels == 4:
            result.extend(row)
        else:
            rgba = bytearray(width * 4)
            rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = (
                row[0::3],
                row[1::3],
                row[2::3],
                b"\xff" * width,
            )
            result.extend(rgba)
    return bytes(result)


def _pixel_counts(left: bytes, right: bytes, threshold: float) -> tuple[int, int]:
    _need(len(left) == len(right), "pixel shape mismatch")
    if left == right:
        return 0, 0
    exact = mismatched = 0
    bound = 35215 * threshold * threshold
    for index, (a, b) in enumerate(
        zip(memoryview(left).cast("I"), memoryview(right).cast("I"), strict=True)
    ):
        if a == b:
            continue
        exact += 1
        offset = index * 4
        r1, g1, b1, a1 = left[offset : offset + 4]
        r2, g2, b2, a2 = right[offset : offset + 4]
        r = 255 + (r1 - 255) * a1 / 255 - (255 + (r2 - 255) * a2 / 255)
        g = 255 + (g1 - 255) * a1 / 255 - (255 + (g2 - 255) * a2 / 255)
        blue = 255 + (b1 - 255) * a1 / 255 - (255 + (b2 - 255) * a2 / 255)
        y = r * 0.29889531 + g * 0.58662247 + blue * 0.11448223
        i = r * 0.59597799 - g * 0.27417610 - blue * 0.32180189
        q = r * 0.21147017 - g * 0.52261711 + blue * 0.31114694
        mismatched += 0.5053 * y * y + 0.299 * i * i + 0.1957 * q * q > bound
    return exact, mismatched


def _profile(attempt: dict[str, Any]) -> dict[str, Any]:
    manifest = _read(_absolute_file(attempt["template"]["selected_tools"], 2097152))
    _wire("selectedTools", manifest)
    python = [tool for tool in manifest["tools"] if tool["id"] == "python"]
    _need(len(python) == 1, "selected Python is not unique")
    tool = python[0]
    path = _inside(_path(tool["root"]), tool["entry_path"])
    _need(
        str(path) == attempt["command"]["argv"][0], "selected Python differs from managed command"
    )
    entries = [row for row in tool["files"] if row["path"] == tool["entry_path"]]
    _need(len(entries) == 1, "selected Python entry is not bound")
    return {
        **attempt["command"],
        "executable_path": str(path.resolve()),
        "executable_sha256": entries[0]["sha256"],
    }


class PaladinUIRun:
    """Join one immutable UI run to authenticated managed and baseline history."""

    @_boundary
    def __init__(
        self,
        runtime: ManagedRuntime,
        *,
        contract: dict[str, Any],
        operator_approval: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """Detach and validate an immutable run without writes or launches."""
        _need(isinstance(runtime, ManagedRuntime), "UI requires ManagedRuntime")
        _need(operator_approval is None or callable(operator_approval), "invalid approval callback")
        self._runtime, self._store, self._approval = runtime, runtime._store, operator_approval
        self._contract = _parse(_canonical(contract), 2097152)
        data = _record(
            self._contract,
            "schema run_id mode task_id wing room baseline_id project_id route_id state_id "
            "producer_root producer_files environment attempts",
        )
        _need(
            data["schema"] == "cairntir.paladin-ui-contract.v1"
            and data["mode"] in {"capture-baseline", "compare"},
            "unsupported UI contract",
        )
        for name in ("run_id", "task_id", "baseline_id"):
            _uuid(data[name])
        for name in ("wing", "room", "project_id", "route_id", "state_id"):
            _ident(data[name])
        environment = _record(data["environment"], "values absent")
        _need(
            isinstance(environment["values"], dict)
            and isinstance(environment["absent"], list)
            and len(set(environment["absent"])) == len(environment["absent"])
            and not set(environment["values"]) & set(environment["absent"]),
            "invalid environment binding",
        )
        for name, value in environment["values"].items():
            _need(
                isinstance(name, str)
                and bool(name)
                and "=" not in name
                and isinstance(value, str)
                and "\x00" not in name + value
            )
        _need(
            all(
                isinstance(name, str) and name and "=" not in name and "\x00" not in name
                for name in environment["absent"]
            )
        )
        self._producer = _path(data["producer_root"])
        attempts = data["attempts"]
        _need(
            isinstance(attempts, list)
            and 1 <= len(attempts) <= 7
            and (data["mode"] != "capture-baseline" or len(attempts) == 1),
            "invalid attempt inventory",
        )
        self._attempts: dict[str, dict[str, Any]] = {}
        outputs: list[Path] = []
        for attempt in attempts:
            _record(attempt, "attempt_id profile command template_file template approved_baseline")
            identity = _uuid(attempt["attempt_id"])
            _need(identity not in self._attempts, "duplicate attempt")
            _ident(attempt["profile"])
            template = attempt["template"]
            _wire("template", template)
            _need(
                template["mode"] == data["mode"]
                and all(
                    template["project"][name] == data[name]
                    for name in ("project_id", "route_id", "state_id")
                ),
                "UI project scope mismatch",
            )
            _canonical(template, 131072)
            template_ref = _record(attempt["template_file"], "path sha256 bytes")
            template_path = _inside(self._producer, template_ref["path"])
            _need(
                _reference(template_path, 131072) == {**template_ref, "path": str(template_path)}
                and _read(template_path, 131072) == template,
                "template changed",
            )
            output = _path(template["output_root"])
            snapshot = _path(template["project"]["snapshot_root"])
            _need(
                not output.is_relative_to(snapshot)
                and not snapshot.is_relative_to(output)
                and not output.is_relative_to(self._producer)
                and not self._producer.is_relative_to(output),
                "output overlaps immutable input",
            )
            _need(
                all(
                    not output.is_relative_to(other) and not other.is_relative_to(output)
                    for other in outputs
                ),
                "shared attempt output",
            )
            outputs.append(output)
            command = _record(attempt["command"], "argv cwd timeout_seconds output_limit_bytes")
            argv = command["argv"]
            _need(
                isinstance(argv, list)
                and len(argv) == 12
                and all(isinstance(value, str) and value and "\x00" not in value for value in argv)
                and argv[1:4] == ["-I", "-B", "-X"]
                and argv[4] == "pycache_prefix=" + str(output / "runtime/python-cache")
                and argv[6:]
                == [
                    "--request",
                    str(output / "request.json"),
                    "--template",
                    str(template_path),
                    "--template-sha256",
                    template_ref["sha256"],
                ]
                and command["cwd"] == str(snapshot)
                and type(command["timeout_seconds"]) in (int, float)
                and command["timeout_seconds"] == 150
                and type(command["output_limit_bytes"]) is int
                and command["output_limit_bytes"] == 65536,
                "UI requires its fixed managed command",
            )
            for executable in (argv[0], argv[5]):
                _path(executable)
            self._baseline_input(attempt)
            self._attempts[identity] = attempt
        self._digest = _digest(data)
        self._prefix = f"paladin-ui:{data['run_id']}:"
        self._qualify()

    @staticmethod
    def _head(value: object) -> dict[str, Any]:
        head = _record(value, "generation revision_sha256")
        _need(type(head["generation"]) is int and head["generation"] >= 0)
        revision = head["revision_sha256"]
        _need(
            (head["generation"] == 0 and revision is None)
            or (
                head["generation"] > 0
                and isinstance(revision, str)
                and re.fullmatch("[0-9a-f]{64}", revision) is not None
            ),
            "invalid baseline head",
        )
        return head

    def _baseline_input(self, attempt: dict[str, Any]) -> None:
        baseline = attempt["approved_baseline"]
        template = attempt["template"]
        if self._contract["mode"] == "capture-baseline":
            _need(baseline is None and template["baseline_reference"] is None)
            return
        _record(baseline, "reference manifest_file")
        reference = _record(baseline["reference"], "head manifest approval_id approval")
        head = self._head(reference["head"])
        _uuid(reference["approval_id"])
        _need(
            head["generation"] > 0 and head["revision_sha256"] == _digest(reference["manifest"]),
            "invalid approved manifest digest",
        )
        path = _absolute_file(baseline["manifest_file"], 1048576)
        _need(
            path.is_relative_to(self._producer)
            and path.read_bytes() == _canonical(reference["manifest"], 1048576)
            and baseline["manifest_file"]["sha256"] == head["revision_sha256"],
            "baseline manifest changed",
        )
        manifest = reference["manifest"]
        _record(
            manifest,
            "schema scope generation previous_revision_sha256 candidate_id "
            "candidate_manifest_sha256 baseline_origin images",
        )
        _need(
            manifest["schema"] == "cairntir.paladin-ui-approved-baseline.v1"
            and manifest["generation"] == head["generation"]
        )
        _need(
            template["baseline_reference"]
            == {
                "baseline_id": self._contract["baseline_id"],
                "generation": head["generation"],
                "revision_sha256": head["revision_sha256"],
                "approval_id": reference["approval_id"],
                "approval": reference["approval"],
                "manifest_file": baseline["manifest_file"],
                "baseline_origin_snapshot_sha256": manifest["baseline_origin"]["source"][
                    "snapshot_sha256"
                ],
            },
            "baseline rendering reference mismatch",
        )
        scope = manifest["scope"]
        _need(
            all(
                scope[name] == self._contract[name]
                for name in ("baseline_id", "wing", "room", "project_id", "route_id", "state_id")
            ),
            "foreign baseline scope",
        )

    def _tools(self, attempt: dict[str, Any]) -> dict[str, dict[str, Any]]:
        template = attempt["template"]
        path = _absolute_file(template["selected_tools"], 2097152)
        manifest = _read(path)
        _wire("selectedTools", manifest)
        tools: dict[str, dict[str, Any]] = {tool["id"]: tool for tool in manifest["tools"]}
        _need(
            set(tools)
            == {
                "python",
                "node",
                "playwright",
                "playwright-core",
                "chrome",
                "pngjs",
                "pixelmatch",
                "worker",
                "producer",
            },
            "selected tool inventory",
        )
        count = total = 0
        for tool in tools.values():
            root = _path(tool["root"])
            _verify_files(root, tool["files"], complete=False, count=4096, size=2147483648)
            _need(
                tool["entry_path"] in {row["path"] for row in tool["files"]},
                "tool entry is unbound",
            )
            count += len(tool["files"])
            total += sum(row["bytes"] for row in tool["files"])
        _need(count <= 4096 and total <= 2147483648, "selected tool inventory cap")
        argv = attempt["command"]["argv"]
        _need(
            argv[0] == str(_inside(_path(tools["python"]["root"]), tools["python"]["entry_path"]))
            and argv[5]
            == str(_inside(_path(tools["worker"]["root"]), tools["worker"]["entry_path"])),
            "command/tool origin mismatch",
        )
        for name in ("worker", "producer"):
            _need(
                _inside(_path(tools[name]["root"]), tools[name]["entry_path"]).is_relative_to(
                    self._producer
                ),
                "producer code is outside immutable provider root",
            )
        return tools

    def _qualify(self) -> None:
        _need(
            _digest(self._contract) == getattr(self, "_digest", _digest(self._contract)),
            "contract mutated",
        )
        data = self._contract
        _verify_files(
            self._producer, data["producer_files"], complete=True, count=128, size=8388608
        )
        environment = data["environment"]
        _need(
            all(os.environ.get(key) == value for key, value in environment["values"].items())
            and all(key not in os.environ for key in environment["absent"]),
            "environment changed",
        )
        _need(
            (self._runtime._wing, self._runtime._room) == (data["wing"], data["room"]),
            "runtime scope mismatch",
        )
        for attempt in self._attempts.values():
            template = attempt["template"]
            project = template["project"]
            _verify_files(
                _path(project["snapshot_root"]),
                project["files"],
                complete=True,
                count=128,
                size=8388608,
            )
            _need(
                project["snapshot_sha256"] == _digest(project["files"]), "project snapshot mismatch"
            )
            _need(
                self._runtime._config["profiles"].get(attempt["profile"]) == _profile(attempt),
                "managed profile changed",
            )
            checks = template["checks"]
            _need(
                len({row["id"] for row in checks}) == len(checks)
                and {row["family"] for row in checks} == {"accessibility", "responsive", "visual"}
                and sum(row["kind"] == "rgba-diff" for row in checks) == 1,
                "invalid check inventory",
            )
            selectors = set(template["render_policy"]["font"]["text_selectors"])
            for check in checks:
                for key in ("selector", "control", "panel", "start_selector"):
                    if key in check:
                        selectors.add(check[key])
                for key in ("selectors", "expected_focus"):
                    selectors.update(check.get(key, ()))
            _need(len(selectors) <= 32, "selector cap")
            self._tools(attempt)
            self._baseline_input(attempt)

    def _context(self, *, active: bool = False, approve: bool = False) -> None:
        data = self._contract
        _need(
            (self._runtime._wing, self._runtime._room) == (data["wing"], data["room"])
            and self._runtime._task_id in (None, data["task_id"]),
            "runtime task mismatch",
        )
        if isinstance(self._store, ScopedStore):
            self._store._authorize_complete_wing(data["wing"])
            self._store.authorize("read", wing=data["wing"], room=data["room"])
            if active:
                for capability in ("write", "approve") if approve else ("write",):
                    self._store.authorize(capability, wing=data["wing"], room=data["room"])
        task = _parse(
            self._runtime._book.resume(data["wing"], data["task_id"], 262144).encode(), 2097152
        )
        if task["status"] == "omitted":
            task = _parse(
                self._runtime._book.resume(
                    data["wing"], data["task_id"], task["required_chars"]
                ).encode(),
                2097152,
            )
        _need(task["status"] in {"ready", "terminal"}, "task evidence unavailable")
        if active:
            self._runtime._check()
            _need(
                self._runtime._task_id == data["task_id"]
                and task["status"] == "ready"
                and not self._store.transaction_active,
                "UI mutation requires an active task outside a caller transaction",
            )

    def _records(
        self,
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        arguments = {
            name: self._contract[name]
            for name in ("wing", "room", "run_id", "task_id", "baseline_id")
        }
        if isinstance(self._store, ScopedStore):
            projected = self._store._paladin_ui_records(**arguments)
        else:
            _need(isinstance(self._store, DrawerStore), "unsupported UI store")
            projected = _paladin_ui_records(self._store, **arguments)
        records = {
            row["idempotency_key"][len(self._prefix) :]: row["result"]
            for row in projected["ui"]
            if row["idempotency_key"].startswith(self._prefix)
        }
        for record in records.values():
            _need(record["request"]["contract_sha256"] == self._digest, "run contract rebound")
        if "plan" in records:
            _need(records["plan"]["request"]["contract"] == self._contract, "run contract changed")
        return records, projected["ui"], projected["managed"]

    def _evidence(self, identity: int) -> dict[str, Any]:
        _need(type(identity) is int and identity > 0)
        sources = self._store._task_drawers([identity])
        _need(identity in sources, "missing evidence drawer")
        drawer, provenance = sources[identity]
        now = datetime.now(UTC)
        _need(
            drawer.wing == self._contract["wing"]
            and drawer.room == self._contract["room"]
            and provenance.sensitivity != Sensitivity.SECRET
            and (provenance.valid_from is None or provenance.valid_from <= now)
            and (provenance.valid_until is None or provenance.valid_until > now),
            "evidence unavailable",
        )
        return {
            "drawer_id": identity,
            "source_identity": self._store.portable_identity(identity),
            "content_sha256": _sha(drawer.content.encode()),
        }

    def _request(self, **extra: Any) -> dict[str, Any]:
        return {
            **{name: self._contract[name] for name in ("run_id", "task_id", "wing", "room")},
            "contract_sha256": self._digest,
            **extra,
        }

    def _save(
        self, key: str, kind: str, request: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        operation = f"paladin.ui.{kind}.v1"
        _canonical(result, 1048576)

        def append() -> dict[str, Any]:
            drawer = self._store.add(
                Drawer(
                    wing=self._contract["wing"],
                    room=self._contract["room"],
                    content=_canonical(
                        {
                            "operation": operation,
                            "request_sha256": request_hash(request),
                            "result": result,
                        }
                    ).decode(),
                    metadata={
                        "kind": "paladin.ui.record",
                        "run_id": self._contract["run_id"],
                        "operation": operation,
                    },
                )
            )
            if drawer.id is None:
                raise PaladinUIError("UI record has no persisted identity")
            return {"request": request, "result": result, "evidence": self._evidence(drawer.id)}

        execution = self._store.execute_once(
            idempotency_key=key, operation=operation, request=request, action=append
        )
        return execution.result

    @staticmethod
    def _approved_manifest(candidate: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
        manifest = candidate["manifest"]
        return {
            "schema": "cairntir.paladin-ui-approved-baseline.v1",
            "scope": deepcopy(manifest["scope"]),
            "generation": head["generation"] + 1,
            "previous_revision_sha256": head["revision_sha256"],
            "candidate_id": manifest["candidate_id"],
            "candidate_manifest_sha256": candidate["manifest_sha256"],
            "baseline_origin": deepcopy(manifest["origin"]),
            "images": [
                {
                    "viewport_id": row["viewport_id"],
                    "width": row["width"],
                    "height": row["height"],
                    "device_scale_factor": row["device_scale_factor"],
                    "png": deepcopy(row["current"]),
                }
                for row in manifest["images"]
            ],
        }

    def _history(
        self, rows: list[dict[str, Any]], managed: list[dict[str, Any]]
    ) -> tuple[
        dict[str, tuple[dict[str, Any], dict[str, Any]]],
        list[dict[str, Any]],
        dict[str, Any] | None,
        dict[str, dict[str, Any]],
    ]:
        candidates: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        reviews: list[dict[str, Any]] = []
        active: dict[str, Any] | None = None
        terminal: dict[str, dict[str, Any]] = {}
        plans = {
            row["result"]["request"]["run_id"]: row["result"]["request"]["contract"]
            for row in rows
            if row["operation"] == "paladin.ui.plan.v1"
        }
        for row in rows:
            if row["operation"] != "paladin.ui.result.v1":
                continue
            envelope = row["result"]
            value = envelope["result"]
            _record(
                value,
                "schema run_id attempt_id action_id contract_sha256 request_sha256 mode status "
                "families managed_result ownership artifacts candidate evidence_ids "
                "diagnostics",
            )
            _need(
                value["schema"] == "cairntir.paladin-ui-attempt-result.v1"
                and value["run_id"] == envelope["request"]["run_id"]
                and value["attempt_id"] == envelope["request"]["attempt_id"]
            )
            _wire("families", value["families"])
            _need(
                value["status"] in {"PASS", "FAIL", "INCONCLUSIVE", "UNREVIEWED"}
                and value["mode"] in {"capture-baseline", "compare"}
                and isinstance(value["evidence_ids"], list)
                and all(type(key) is int and key > 0 for key in value["evidence_ids"])
                and len(set(value["evidence_ids"])) == len(value["evidence_ids"])
            )
            if value["ownership"] is not None:
                _wire("ownership", value["ownership"])
            _need(isinstance(value["artifacts"], list) and len(value["artifacts"]) <= 4096)
            for artifact in value["artifacts"]:
                _wire("artifact", artifact)
            bundle = value["candidate"]
            if bundle is None:
                continue
            _record(bundle, "manifest manifest_sha256")
            manifest = _record(bundle["manifest"], "schema candidate_id scope origin images")
            _need(
                bundle["manifest_sha256"] == _digest(manifest)
                and manifest["schema"] == "cairntir.paladin-ui-baseline-candidate.v1"
                and manifest["candidate_id"] == value["attempt_id"]
                and manifest["candidate_id"] not in candidates
            )
            contract = plans[value["run_id"]]
            attempt = next(
                item for item in contract["attempts"] if item["attempt_id"] == value["attempt_id"]
            )
            scope = _record(
                manifest["scope"],
                "baseline_id wing room project_id route_id state_id "
                "renderer_sha256 policy_sha256 viewports",
            )
            _need(
                all(
                    scope[name] == self._contract[name]
                    for name in (
                        "baseline_id",
                        "wing",
                        "room",
                        "project_id",
                        "route_id",
                        "state_id",
                    )
                ),
                "foreign shared baseline scope",
            )
            _wire("viewports", scope["viewports"])
            for name in ("renderer_sha256", "policy_sha256"):
                _wire("sha", scope[name])
            origin = _record(
                manifest["origin"],
                "run_id task_id attempt_id action_id source preparation managed_outcome",
            )
            _need(
                origin["run_id"] == value["run_id"]
                and origin["task_id"] == contract["task_id"]
                and origin["attempt_id"] == value["attempt_id"]
                and origin["action_id"] == value["action_id"]
                and origin["preparation"] == envelope["request"]["preparation"]
                and origin["source"]
                == {
                    "revision": attempt["template"]["project"]["source_revision"],
                    "snapshot_sha256": attempt["template"]["project"]["snapshot_sha256"],
                }
                and origin["managed_outcome"]
                == self._evidence(value["managed_result"]["outcome_drawer_id"])
            )
            _need(
                all(
                    manifest["scope"][name] == contract[name]
                    for name in (
                        "baseline_id",
                        "wing",
                        "room",
                        "project_id",
                        "route_id",
                        "state_id",
                    )
                )
            )
            candidates[manifest["candidate_id"]] = (bundle, envelope["evidence"])
        head = {"generation": 0, "revision_sha256": None}
        for row in rows:
            if row["operation"] != "paladin.ui.review.v1":
                continue
            envelope = row["result"]
            request, outcome = envelope["request"], envelope["result"]
            _record(
                outcome,
                "schema review_id candidate_id candidate_manifest_sha256 decision before after "
                "review_evidence candidate approval_manifest",
            )
            identity = _uuid(outcome["candidate_id"])
            _need(
                identity in candidates and identity not in terminal,
                "review has no unreviewed candidate",
            )
            bundle, evidence = candidates[identity]
            _need(
                outcome["schema"] == "cairntir.paladin-ui-baseline-review.v1"
                and outcome["review_id"] == request["idempotency_key"]
                and outcome["candidate_manifest_sha256"] == bundle["manifest_sha256"]
                and outcome["candidate"] == request["candidate"] == evidence
                and outcome["review_evidence"] == request["review_evidence"]
                and outcome["before"] == request["expected_revision"] == head
            )
            if outcome["decision"] == "APPROVED":
                proposed = self._approved_manifest(bundle, head)
                after = {"generation": proposed["generation"], "revision_sha256": _digest(proposed)}
                _need(outcome["approval_manifest"] == proposed and outcome["after"] == after)
                head = after
                active = {
                    "head": deepcopy(head),
                    "manifest": deepcopy(proposed),
                    "approval_id": outcome["review_id"],
                    "approval": deepcopy(envelope["evidence"]),
                }
            else:
                _need(
                    outcome["decision"] == "REJECTED"
                    and outcome["after"] == head
                    and outcome["approval_manifest"] is None
                )
            terminal[identity] = envelope
            reviews.append(
                {"review": deepcopy(outcome), "evidence": deepcopy(envelope["evidence"])}
            )
        return candidates, reviews, active, terminal

    @staticmethod
    def _tool_observation(tool: dict[str, Any]) -> dict[str, Any]:
        path = _inside(_path(tool["root"]), tool["entry_path"])
        return {
            "id": tool["id"],
            "entry_path": str(path),
            "entry_sha256": _reference(path, 2147483648)["sha256"],
            "version": tool["version"],
        }

    @staticmethod
    def _families(rows: list[dict[str, Any]]) -> dict[str, str]:
        result = {}
        for family in ("accessibility", "responsive", "visual"):
            statuses = [row["status"] for row in rows if row["check"]["family"] == family]
            _need(bool(statuses), "missing check family")
            result[family] = (
                "INCONCLUSIVE"
                if "INCONCLUSIVE" in statuses
                else "FAIL"
                if "FAIL" in statuses
                else "UNREVIEWED"
                if "UNREVIEWED" in statuses
                else "PASS"
            )
        return result

    def _raw(self, attempt: dict[str, Any], report: dict[str, Any], root: Path) -> dict[str, str]:
        template, all_checks = attempt["template"], []
        expected_raw = ["producer/network.json"]
        tools = self._tools(attempt)
        _need(
            report["status"] == "COMPLETE" and all(report["browser_lifecycle"].values()),
            "browser incomplete",
        )
        _need(
            report["mode"] == template["mode"]
            and report["project_id"] == self._contract["project_id"]
            and report["current_source_revision"] == template["project"]["source_revision"]
            and report["current_snapshot_sha256"] == template["project"]["snapshot_sha256"]
            and report["baseline_reference"] == template["baseline_reference"]
            and report["selected_tools_sha256"] == template["selected_tools"]["sha256"]
        )
        old_source = (
            None
            if template["baseline_reference"] is None
            else template["baseline_reference"]["baseline_origin_snapshot_sha256"]
        )
        _need(report["baseline_origin_snapshot_sha256"] == old_source)
        expected_tools = [
            self._tool_observation(tools[name])
            for name in ("node", "playwright", "playwright-core", "chrome", "pngjs", "pixelmatch")
        ]
        _need(report["tool_observations"] == expected_tools, "actual tool observations mismatch")
        visual = next(check for check in template["checks"] if check["kind"] == "rgba-diff")
        policy = {
            "render_policy": template["render_policy"],
            "visual_policy": {
                key: value for key, value in visual.items() if key not in ("id", "kind", "family")
            },
        }
        policy_sha = _digest(policy)
        renderer = report["renderer"]
        font = template["render_policy"]["font"]
        _need(
            report["policy_sha256"] == renderer["policy_sha256"] == policy_sha
            and renderer["browser"]
            == {
                "runtime_manifest_sha256": _digest(tools["chrome"]["files"]),
                "version": tools["chrome"]["version"],
            }
            and renderer["font"]
            == {
                "file_sha256": font["sha256"],
                "custom_family": font["platform_family"],
                "postscript_name": font["postscript_name"],
            }
            and all(
                renderer[name]
                == {
                    "payload_sha256": _digest(tools[name]["files"]),
                    "version": tools[name]["version"],
                }
                for name in ("pngjs", "pixelmatch")
            )
            and report["renderer_sha256"] == _digest(renderer),
            "renderer identity mismatch",
        )
        baseline = attempt["approved_baseline"]
        if baseline is not None:
            scope = baseline["reference"]["manifest"]["scope"]
            _need(
                scope["renderer_sha256"] == report["renderer_sha256"]
                and scope["policy_sha256"] == policy_sha
                and scope["viewports"] == template["render_policy"]["viewports"],
                "incompatible baseline renderer",
            )
        selectors = []
        for check in template["checks"]:
            for key in ("selector", "start_selector", "control", "panel"):
                if key in check and check[key] not in selectors:
                    selectors.append(check[key])
            for key in ("selectors", "expected_focus"):
                for item in check.get(key, ()):
                    if item not in selectors:
                        selectors.append(item)
        for item in font["text_selectors"]:
            if item not in selectors:
                selectors.append(item)
        for viewport, target in zip(
            report["viewports"], template["render_policy"]["viewports"], strict=True
        ):
            name, width, height = target["id"], target["width"], target["height"]
            _need(
                {key: viewport[key] for key in ("id", "width", "height", "device_scale_factor")}
                == target
            )
            prefix = "producer/raw/" + name + "/"
            raw = {}
            for kind, schema in (
                ("dom", "rawDOM"),
                ("ax", "rawAX"),
                ("fonts", "rawFonts"),
                ("keyboard", "rawKeyboard"),
            ):
                relative = prefix + kind + ".json"
                expected_raw.append(relative)
                raw[kind] = _read(_inside(root, relative))
                _wire(schema, raw[kind])
                _need(raw[kind]["viewport_id"] == name)
            dom, ax, fonts, keyboard = (raw[key] for key in ("dom", "ax", "fonts", "keyboard"))
            document = dom["document"]
            _need(
                (document["inner_width"], document["inner_height"], document["device_scale_factor"])
                == (width, height, 1)
                and document["ready_state"] == "complete"
            )
            _need(
                [row["selector"] for row in dom["selectors"]] == selectors
                and [row["selector"] for row in ax["selector_mappings"]] == selectors,
                "raw selector inventory",
            )
            dom_map = {row["selector"]: row for row in dom["selectors"]}
            mappings = {row["selector"]: row for row in ax["selector_mappings"]}
            _need(len({row["nodeId"] for row in ax["nodes"]}) == len(ax["nodes"]))
            nodes = {row["nodeId"]: row for row in ax["nodes"]}
            for selector in selectors:
                row, mapping = dom_map[selector], mappings[selector]
                _need(
                    row["count"] == len(row["matches"])
                    and mapping["node_ids"] == [item["node_id"] for item in row["matches"]]
                    and mapping["backend_node_ids"]
                    == [item["backend_node_id"] for item in row["matches"]]
                    and all(
                        identity in nodes
                        and nodes[identity].get("backendDOMNodeId") in mapping["backend_node_ids"]
                        for identity in mapping["ax_node_ids"]
                    ),
                    "raw native node binding",
                )
            _need(
                fonts["font_path"] == font["path"]
                and fonts["font_sha256"] == font["sha256"]
                and fonts["license_sha256"] == font["license_sha256"]
                and fonts["css_family"] == font["css_family"]
                and fonts["platform_family"] == font["platform_family"]
                and fonts["postscript_name"] == font["postscript_name"]
                and [row["selector"] for row in fonts["observations"]] == font["text_selectors"]
                and viewport["font_observations"] == fonts["observations"],
                "font evidence mismatch",
            )
            for observation in fonts["observations"]:
                selected = dom_map[observation["selector"]]
                glyphs = [item for item in observation["fonts"] if item["glyph_count"] > 0]
                _need(
                    selected["count"] == 1
                    and observation["backend_node_id"] == selected["matches"][0]["backend_node_id"]
                    and observation["document_fonts_ready"]
                    and observation["font_face_loaded"]
                    and font["css_family"] in observation["computed_family"]
                    and bool(glyphs)
                    and all(
                        item["is_custom_font"]
                        and item["family_name"] == font["platform_family"]
                        and item["postscript_name"] == font["postscript_name"]
                        for item in glyphs
                    ),
                    "font fallback or missing glyphs",
                )
            expected_raw.append(prefix + "current.png")
            current_pixels = _png(_inside(root, prefix + "current.png"), width, height)
            observed_rows = viewport["checks"]
            _need(
                [row["check"] for row in observed_rows] == template["checks"],
                "check set/order changed",
            )
            _need(
                keyboard["initial_active_element"] == document["active_element"]
                and keyboard["results"]
                == [row for row in observed_rows if row["check"]["kind"].startswith("keyboard-")],
                "keyboard result binding",
            )
            events: list[dict[str, Any]] = []
            for row in observed_rows:
                check, observation = row["check"], row["observation"]
                kind = check["kind"]
                evidence = []
                passed: bool | None = None
                if kind == "document-equals":
                    _need(observation == {"value": document[check["property"]]})
                    passed = observation["value"] == check["expected"]
                    evidence = [prefix + "dom.json"]
                elif kind == "ax-role-name":
                    selected, mapping = dom_map[check["selector"]], mappings[check["selector"]]
                    if selected["count"] == 1:
                        _need(
                            len(mapping["ax_node_ids"]) == 1,
                            "one DOM element requires one native AX node",
                        )
                        node = nodes[mapping["ax_node_ids"][0]]
                        _need(
                            node.get("backendDOMNodeId")
                            == selected["matches"][0]["backend_node_id"],
                            "AX node does not bind the selected DOM element",
                        )
                        expected = {
                            "selector_count": 1,
                            "backend_node_id": node.get("backendDOMNodeId"),
                            "ax_node_id": node["nodeId"],
                            "ignored": node["ignored"],
                            "role": node.get("role", {}).get("value"),
                            "name": node.get("name", {}).get("value"),
                        }
                    else:
                        expected = {
                            "selector_count": selected["count"],
                            "backend_node_id": None,
                            "ax_node_id": None,
                            "ignored": None,
                            "role": None,
                            "name": None,
                        }
                    _need(observation == expected, "AX observation differs from native tree")
                    passed = (
                        observation["selector_count"] == 1
                        and observation["ignored"] is False
                        and observation["role"] == check["role"]
                        and observation["name"] == check["name"]
                    )
                    evidence = [prefix + "dom.json", prefix + "ax.json"]
                elif kind == "keyboard-tab-order":
                    _need(
                        observation["initial"] == document["active_element"]
                        and len(observation["steps"]) == len(check["expected_focus"])
                    )
                    start = dom_map[check["start_selector"]]
                    start_matches = (
                        start["count"] == 1
                        and self._element(start["matches"][0]) == observation["initial"]
                    )
                    _need(observation["start_matches"] is start_matches)
                    passed = start_matches
                    for step, selector in zip(
                        observation["steps"], check["expected_focus"], strict=True
                    ):
                        selected = dom_map[selector]
                        matches = (
                            selected["count"] == 1
                            and self._element(selected["matches"][0]) == step["actual"]
                        )
                        _need(step["key"] == "Tab" and step["expected_selector_matches"] is matches)
                        passed &= matches
                        events.append(
                            {
                                "ordinal": len(events) + 1,
                                "check_id": check["id"],
                                "key": "Tab",
                                "active_element": step["actual"],
                            }
                        )
                    evidence = [prefix + "keyboard.json"]
                elif kind == "keyboard-key-state":
                    control, panel = dom_map[check["control"]], dom_map[check["panel"]]
                    focused = (
                        control["count"] == 1
                        and self._element(control["matches"][0]) == observation["actual_focus"]
                    )
                    _need(
                        observation["control_count"] == control["count"]
                        and observation["panel_count"] == panel["count"]
                        and observation["control_focused"] is focused
                    )
                    passed = (
                        focused
                        and control["count"] == panel["count"] == 1
                        and observation["expanded"] == str(check["expanded"]).lower()
                        and observation["panel_visible"] is check["visible"]
                    )
                    events.append(
                        {
                            "ordinal": len(events) + 1,
                            "check_id": check["id"],
                            "key": check["key"],
                            "active_element": observation["actual_focus"],
                        }
                    )
                    evidence = [prefix + "keyboard.json"]
                elif kind == "required-visible":
                    _need(
                        [item["selector"] for item in observation["elements"]] == check["selectors"]
                    )
                    passed = True
                    for item in observation["elements"]:
                        selected = dom_map[item["selector"]]
                        _need(item["count"] == selected["count"])
                        if selected["count"] == 1:
                            element = selected["matches"][0]
                            rect = element["rect"]
                            tolerance = check["tolerance_css_pixels"]
                            inside = (
                                rect["width"] > 0
                                and rect["height"] > 0
                                and rect["x"] >= -tolerance
                                and rect["y"] >= -tolerance
                                and rect["x"] + rect["width"] <= width + tolerance
                                and rect["y"] + rect["height"] <= height + tolerance
                            )
                            _need(
                                item["rect"] == rect
                                and item["visible"] == element["visible"]
                                and item["within_viewport"] is inside
                            )
                            passed &= element["visible"] and inside
                        else:
                            passed = False
                    evidence = [prefix + "dom.json"]
                elif kind == "horizontal-overflow":
                    amount = max(0, document["scroll_width"] - document["client_width"])
                    _need(
                        observation
                        == {
                            "scroll_width": document["scroll_width"],
                            "client_width": document["client_width"],
                            "viewport_width": width,
                            "overflow_css_pixels": amount,
                        }
                    )
                    passed = amount <= check["maximum_css_pixels"]
                    evidence = [prefix + "dom.json"]
                else:
                    _need(kind == "rgba-diff")
                    current_ref = self._artifact(root, prefix + "current.png", 8388608)
                    _need(
                        observation["current"] == current_ref
                        and (observation["width"], observation["height"]) == (width, height)
                    )
                    if template["mode"] == "capture-baseline":
                        _need(
                            all(
                                observation[key] is None
                                for key in (
                                    "baseline",
                                    "diff",
                                    "mismatched_pixels",
                                    "exact_changed_pixels",
                                    "allowed_diff_pixels",
                                    "diff_ratio",
                                )
                            )
                            and observation["compared_pixels"] == 0
                        )
                        passed = None
                        evidence = [prefix + "current.png"]
                    else:
                        expected_raw.extend(
                            prefix + item
                            for item in ("baseline.png", "diff.png", "comparison.json")
                        )
                        comparison = _read(_inside(root, prefix + "comparison.json"))
                        _wire("rawComparison", comparison)
                        _need(comparison == observation)
                        approved = next(
                            item["png"]
                            for item in baseline["reference"]["manifest"]["images"]
                            if item["viewport_id"] == name
                        )
                        _absolute_file(approved, 8388608)
                        old = _inside(root, prefix + "baseline.png")
                        old_ref = self._artifact(root, prefix + "baseline.png", 8388608)
                        _need(
                            (old_ref["sha256"], old_ref["bytes"])
                            == (approved["sha256"], approved["bytes"])
                            and observation["baseline"] == old_ref
                            and observation["diff"]
                            == self._artifact(root, prefix + "diff.png", 8388608)
                        )
                        old_pixels = _png(old, width, height)
                        _png(_inside(root, prefix + "diff.png"), width, height)
                        exact, mismatch = _pixel_counts(
                            old_pixels, current_pixels, check["threshold"]
                        )
                        total = width * height
                        allowed = math.floor(total * check["allowed_diff_ratio"])
                        _need(
                            observation["compared_pixels"] == total
                            and observation["mismatched_pixels"] == mismatch
                            and observation["exact_changed_pixels"] == exact
                            and observation["allowed_diff_pixels"] == allowed
                            and observation["diff_ratio"] == mismatch / total,
                            "decoded pixel metrics differ",
                        )
                        passed = mismatch <= allowed
                        evidence = [prefix + "comparison.json"]
                expected_status = "UNREVIEWED" if passed is None else "PASS" if passed else "FAIL"
                _need(
                    row["status"] == expected_status and row["evidence_paths"] == evidence,
                    "check classification differs from raw evidence",
                )
                all_checks.append(row)
            _need(keyboard["events"] == events, "keyboard event sequence differs")
        network = _read(_inside(root, "producer/network.json"))
        _wire("rawNetwork", network)
        project_files = {row["path"]: row for row in template["project"]["files"]}
        for index, event in enumerate(network["events"], 1):
            path = event["project_path"]
            _need(
                event["ordinal"] == index
                and event["viewport_id"] in {"mobile", "desktop"}
                and event["decision"] == "fulfilled"
                and event["method"] == "GET"
                and path in project_files
                and event["sha256"] == project_files[path]["sha256"]
                and event["url"] == "https://cairntir.invalid/" + path,
                "blocked or unbound network resource",
            )
        for name in ("mobile", "desktop"):
            fulfilled = {
                event["project_path"] for event in network["events"] if event["viewport_id"] == name
            }
            _need(
                {template["project"]["entry_path"], font["path"]} <= fulfilled,
                "required project resources missing",
            )
        _need(
            report["raw_artifacts"]
            == [
                self._artifact(root, path, 8388608 if path.endswith(".png") else 2097152)
                for path in sorted(expected_raw)
            ],
            "raw artifact set changed",
        )
        families = self._families(all_checks)
        _need(report["families"] == families, "family classification mismatch")
        return families

    @staticmethod
    def _element(value: dict[str, Any]) -> dict[str, str]:
        return {key: value[key] for key in ("tag_name", "id")}

    @staticmethod
    def _artifact(root: Path, relative: str, limit: int = 134217728) -> dict[str, Any]:
        row = _reference(_inside(root, relative), limit)
        return {**row, "path": relative}

    def _collect(
        self,
        attempt: dict[str, Any],
        prepared: dict[str, Any],
        managed: dict[str, Any],
        evidence_ids: list[int],
    ) -> dict[str, Any]:
        request = prepared["request"]["producer_request"]
        value: dict[str, Any] = {
            "schema": "cairntir.paladin-ui-attempt-result.v1",
            "run_id": self._contract["run_id"],
            "attempt_id": attempt["attempt_id"],
            "action_id": request["action_id"],
            "contract_sha256": self._digest,
            "request_sha256": _digest(request),
            "mode": self._contract["mode"],
            "status": "INCONCLUSIVE",
            "families": dict.fromkeys(("accessibility", "responsive", "visual"), "INCONCLUSIVE"),
            "managed_result": deepcopy(managed),
            "ownership": None,
            "artifacts": [],
            "candidate": None,
            "evidence_ids": list(dict.fromkeys([*evidence_ids, prepared["evidence"]["drawer_id"]])),
            "diagnostics": [],
        }
        root = _path(attempt["template"]["output_root"])
        try:
            value["artifacts"] = _inventory(root, 4096, 134217728)
            _need(
                managed["status"] == "completed"
                and managed["exit_code"] == 0
                and managed["timed_out"] is False
                and managed["output_truncated"] is False
                and managed["outcome_drawer_id"] is not None,
                "managed execution incomplete",
            )
            self._qualify()
            _need(
                _read(root / "request.json", 262144) == request
                and (root / "request.json").read_bytes() == _canonical(request, 262144)
            )
            stdout = managed["stdout"].encode()
            _need(len(stdout) <= 65536 and len(managed["stderr"].encode()) <= 65536)
            summary = _parse(stdout, 65536)
            _wire("summary", summary)
            identities = {
                key: request[key]
                for key in (
                    "run_id",
                    "attempt_id",
                    "action_id",
                    "contract_sha256",
                    "template_sha256",
                )
            }
            identities["request_sha256"] = _digest(request)
            _need(all(summary[key] == item for key, item in identities.items()))
            for name, relative, limit in (
                ("report", "producer/ui-result.json", 1048576),
                ("ownership", "operations/OWNERSHIP-EXIT.json", 2097152),
                ("closure", "operations/CLOSURE.json", 2097152),
            ):
                _need(
                    summary[name] == self._artifact(root, relative, limit),
                    "managed summary artifact mismatch",
                )
            closure = _read(root / "operations/CLOSURE.json")
            _wire("closure", closure)
            payload = [
                row for row in value["artifacts"] if row["path"] != "operations/CLOSURE.json"
            ]
            _need(
                closure["files"] == payload
                and closure["file_count"] == len(payload)
                and closure["total_bytes"] == sum(row["bytes"] for row in payload)
                and all(
                    closure[key] == identities[key]
                    for key in ("run_id", "attempt_id", "action_id", "request_sha256")
                ),
                "owned payload closure mismatch",
            )
            ownership = _read(root / "operations/OWNERSHIP-EXIT.json")
            start = _read(root / "operations/OWNERSHIP-START.json")
            invocation = _read(root / "operations/INVOCATION.json")
            for name, record in (
                ("ownership", ownership),
                ("ownership", start),
                ("invocation", invocation),
            ):
                _wire(name, record)
                _need(all(record[key] == item for key, item in identities.items()))
            tools = self._tools(attempt)
            argv = [
                str(_inside(_path(tools[name]["root"]), tools[name]["entry_path"]))
                for name in ("node", "producer")
            ]
            argv += ["--request", str(root / "request.json")]
            _need(
                all(
                    record["argv"] == argv and record["cwd"] == attempt["command"]["cwd"]
                    for record in (ownership, start, invocation)
                )
            )
            _need(
                invocation["selected_tools_sha256"]
                == attempt["template"]["selected_tools"]["sha256"]
                and invocation["limits"] == _WIRE["limits"]["const"]
            )
            controls = invocation["environment_controls"]
            for name, setting in controls["values"].items():
                if name == "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD":
                    _need(setting == "1")
                else:
                    _need(_path(setting).is_relative_to(root / "runtime"))
            _need(
                {
                    "NODE_OPTIONS",
                    "NODE_PATH",
                    "CAIRNTIR_HOME",
                    "CAIRNTIR_GRANT_FILE",
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "ALL_PROXY",
                    "NO_PROXY",
                    "PLAYWRIGHT_DOWNLOAD_HOST",
                }
                <= set(controls["absent"])
            )
            _need(
                start["phase"] == "START"
                and start["finished_at"] is None
                and start["suspended_creation"]
                and start["assigned_owned_job"]
            )
            _need(
                ownership["phase"] == "EXIT"
                and ownership["finished_at"] is not None
                and ownership["direct_exit_code"] == 0
                and ownership["job_active_processes"] == 0
                and ownership["suspended_creation"]
                and ownership["assigned_owned_job"]
                and ownership["owned_tree_exit_observed"]
                and ownership["job_handle_closed"]
                and ownership["direct_process_handle_closed"]
                and not ownership["cleanup_uncertain"]
                and not ownership["timed_out"]
                and not ownership["cancelled"]
                and not ownership["output_truncated"]
                and ownership["errors"] == []
                and ownership["elapsed_seconds"] <= 120
                and all(
                    ownership[name] == start[name]
                    for name in (
                        "pid",
                        "direct_process_handle",
                        "job_handle",
                        "started_at",
                        "python",
                        "worker",
                    )
                ),
                "owned process incomplete",
            )
            _need(ownership["worker"] == self._tool_observation(tools["worker"]))
            python = ownership["python"]
            _need(
                {key: python[key] for key in ("id", "entry_path", "entry_sha256", "version")}
                == self._tool_observation(tools["python"])
                and python["isolated"] is True
                and python["dont_write_bytecode"] is True
                and python["optimize"] == 0
                and python["pycache_prefix"] == str(root / "runtime/python-cache")
                and python["cache_prefix_state"] in {"ABSENT", "EMPTY"}
            )
            prefix = root / "runtime/python-cache"
            _need(
                not prefix.exists() or (prefix.is_dir() and not any(prefix.iterdir())),
                "Python cache not empty",
            )
            value["ownership"] = ownership
            report = _read(root / "producer/ui-result.json", 1048576)
            _wire("report", report)
            _need(all(report[key] == item for key, item in identities.items()))
            families = self._raw(attempt, report, root)
            self._qualify()
            _need(
                _inventory(root, 4096, 134217728) == value["artifacts"],
                "output changed during collection",
            )
            value["families"] = families
            value["status"] = (
                "FAIL"
                if "FAIL" in families.values()
                else "UNREVIEWED"
                if self._contract["mode"] == "capture-baseline"
                else "PASS"
            )
            value["candidate"] = self._candidate(attempt, prepared, managed, report)
        except AccessDenied:
            raise
        except (
            CairntirError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            RuntimeError,
            StopIteration,
            struct.error,
            zlib.error,
        ) as exc:
            value["diagnostics"] = ["UI_EVIDENCE_INCOMPLETE: " + str(exc)[:2048]]
        _canonical(value, 1048576)
        return value

    def _candidate(
        self,
        attempt: dict[str, Any],
        prepared: dict[str, Any],
        managed: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        root = _path(attempt["template"]["output_root"])
        images = []
        for viewport in attempt["template"]["render_policy"]["viewports"]:
            name = viewport["id"]
            prefix = root / "producer/raw" / name
            previous: dict[str, Any] | None = None
            if attempt["approved_baseline"] is not None:
                previous = next(
                    row["png"]
                    for row in attempt["approved_baseline"]["reference"]["manifest"]["images"]
                    if row["viewport_id"] == name
                )
            images.append(
                {
                    "viewport_id": name,
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "device_scale_factor": viewport["device_scale_factor"],
                    "current": _reference(prefix / "current.png", 8388608),
                    "previous": deepcopy(previous),
                    "diff": _reference(prefix / "diff.png", 8388608) if previous else None,
                }
            )
        scope = {
            name: self._contract[name]
            for name in ("baseline_id", "wing", "room", "project_id", "route_id", "state_id")
        }
        scope.update(
            renderer_sha256=report["renderer_sha256"],
            policy_sha256=report["policy_sha256"],
            viewports=deepcopy(attempt["template"]["render_policy"]["viewports"]),
        )
        source = attempt["template"]["project"]
        manifest = {
            "schema": "cairntir.paladin-ui-baseline-candidate.v1",
            "candidate_id": attempt["attempt_id"],
            "scope": scope,
            "origin": {
                "run_id": self._contract["run_id"],
                "task_id": self._contract["task_id"],
                "attempt_id": attempt["attempt_id"],
                "action_id": managed["action_id"],
                "source": {
                    "revision": source["source_revision"],
                    "snapshot_sha256": source["snapshot_sha256"],
                },
                "preparation": deepcopy(prepared["evidence"]),
                "managed_outcome": self._evidence(managed["outcome_drawer_id"]),
            },
            "images": images,
        }
        _canonical(manifest, 1048576)
        return {"manifest": manifest, "manifest_sha256": _digest(manifest)}

    def _readiness(self, action: dict[str, Any]) -> None:
        brief = self._runtime._latest
        ack = next(
            (row for row in self._runtime._records("ack") if row["ack_id"] == action["ack_id"]),
            None,
        )
        _need(
            brief is not None
            and ack is not None
            and ack["brief_id"] == brief["brief_id"]
            and ack["epoch"] == self._runtime._epoch
            and ack["brief_sha256"] == brief["brief_sha256"],
            "action requires its current committed acknowledgement",
        )
        if brief is None:
            raise PaladinUIError("managed brief is unavailable")
        self._runtime._ack_state(brief)
        self._runtime._action_events(action)
        _need(not self._runtime._uncertain(), "uncertain managed action blocks dispatch")

    @staticmethod
    def _outcome(
        managed: list[dict[str, Any]], action_id: str
    ) -> tuple[dict[str, Any], list[int]] | None:
        for row in managed:
            if (
                row["_managed"]["operation"] in {"managed.outcome.v1", "managed.observation.v1"}
                and row["action_id"] == action_id
            ):
                return (
                    {key: value for key, value in row.items() if key != "_managed"},
                    row["_managed"]["evidence_ids"],
                )
        return None

    @_boundary
    def execute(self, attempt_id: str, action: dict[str, Any]) -> dict[str, Any]:
        """Prepare durably, dispatch once and retain the observed UI evidence."""
        _uuid(attempt_id)
        _need(attempt_id in self._attempts, "undeclared UI attempt")
        self._context()
        attempt = self._attempts[attempt_id]
        action = deepcopy(
            _record(action, "schema action_id ack_id profile claim predicted_outcome event_ids")
        )
        _need(
            action["schema"] == "cairntir.managed-action.v1"
            and action["profile"] == attempt["profile"]
        )
        for name in ("action_id", "ack_id"):
            _uuid(action[name])
        _need(
            isinstance(action["event_ids"], list)
            and bool(action["event_ids"])
            and len(set(action["event_ids"])) == len(action["event_ids"])
        )
        for event in action["event_ids"]:
            _uuid(event)
        for name in ("claim", "predicted_outcome"):
            _need(
                isinstance(action[name], str) and bool(action[name]) and "\x00" not in action[name]
            )
        records, rows, managed = self._records()
        self._history(rows, managed)
        prefix = f"attempt:{attempt_id}:"
        prepared, saved = records.get(prefix + "prepare"), records.get(prefix + "result")
        replayed = prepared is not None
        if prepared is not None:
            _need(prepared["request"]["action"] == action, "attempt action cannot be rebound")
            if saved is not None:
                self._context()
                return {
                    "result": deepcopy(saved["result"]),
                    "evidence": deepcopy(saved["evidence"]),
                    "replayed": True,
                }
            outcome = self._outcome(managed, action["action_id"])
            if outcome is None:
                raise PaladinUIError(
                    "PREPARED attempt has no committed managed outcome; relaunch refused"
                )
            self._context(active=True)
        else:
            self._context(active=True)
            self._qualify()
            _, _, active, _ = self._history(rows, managed)
            if attempt["approved_baseline"] is not None:
                _need(
                    attempt["approved_baseline"]["reference"] == active,
                    "baseline is not the authenticated active approval",
                )
                self._verify_selected_baseline(active)
            self._readiness(action)
            _need(
                not any(
                    row.get("action_id") == action["action_id"]
                    for row in self._runtime._records("dispatch")
                ),
                "action already dispatched",
            )
            root = _path(attempt["template"]["output_root"])
            _need(not root.exists(), "attempt output must be absent")
            _need(
                not (root / "runtime/python-cache").exists(), "Python cache prefix must be absent"
            )
            producer_request = {
                "schema": "cairntir.paladin-ui-producer.v1",
                "run_id": self._contract["run_id"],
                "attempt_id": attempt_id,
                "action_id": action["action_id"],
                "contract_sha256": self._digest,
                "template_sha256": attempt["template_file"]["sha256"],
                "template": deepcopy(attempt["template"]),
            }
            request_bytes = _canonical(producer_request, 262144)
            _wire("request", producer_request)
            if "plan" not in records:
                self._save(
                    self._prefix + "plan",
                    "plan",
                    self._request(contract=self._contract),
                    {"contract_sha256": self._digest},
                )
            prepared = self._save(
                self._prefix + prefix + "prepare",
                "prepare",
                self._request(
                    attempt_id=attempt_id,
                    action=action,
                    producer_request=producer_request,
                    producer_request_sha256=_sha(request_bytes),
                ),
                {
                    "status": "PREPARED",
                    "action_id": action["action_id"],
                    "producer_request_sha256": _sha(request_bytes),
                },
            )
            root.mkdir()
            with (root / "request.json").open("xb") as stream:
                stream.write(request_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            self._context(active=True)
            self._runtime.dispatch(action)
            _, _, managed = self._records()
            outcome = self._outcome(managed, action["action_id"])
            if outcome is None:
                raise PaladinUIError("managed dispatch has no committed outcome")
        managed_result, evidence_ids = outcome
        result = self._collect(attempt, prepared, managed_result, evidence_ids)
        self._context(active=True)
        saved = self._save(
            self._prefix + prefix + "result",
            "result",
            self._request(attempt_id=attempt_id, preparation=prepared["evidence"]),
            result,
        )
        self._records()
        self._context()
        return {
            "result": deepcopy(saved["result"]),
            "evidence": deepcopy(saved["evidence"]),
            "replayed": replayed,
        }

    @staticmethod
    def _images(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = bundle["manifest"]
        _need(bundle["manifest_sha256"] == _digest(manifest), "candidate manifest changed")
        _need(len(manifest["images"]) == 2, "candidate viewport inventory")
        images = []
        for row, viewport in zip(manifest["images"], manifest["scope"]["viewports"], strict=True):
            _record(row, "viewport_id width height device_scale_factor current previous diff")
            _need(
                row["viewport_id"] == viewport["id"]
                and all(
                    row[name] == viewport[name]
                    for name in ("width", "height", "device_scale_factor")
                )
            )
            _need((row["previous"] is None) == (row["diff"] is None))
            for role in ("current", "previous", "diff"):
                if row[role] is not None:
                    _absolute_file(row[role], 8388608)
                    images.append({"role": role, "viewport_id": row["viewport_id"], **row[role]})
        return images

    def _review_file(
        self,
        value: object,
        bundle: dict[str, Any],
        head: dict[str, Any],
        review_id: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        path = _absolute_file(value, 131072)
        for row in rows:
            if row["operation"] == "paladin.ui.plan.v1":
                contract = row["result"]["request"]["contract"]
                roots = [
                    Path(contract["producer_root"]),
                    *[Path(attempt["template"]["output_root"]) for attempt in contract["attempts"]],
                ]
                _need(
                    not any(path.is_relative_to(root) for root in roots),
                    "review artifact is inside a closed input/output root",
                )
        artifact: dict[str, Any] = _read(path, 131072)
        _record(
            artifact,
            "schema review_id candidate_id candidate_manifest_sha256 expected_revision scope "
            "decision reviewed_images reviewer method reason",
        )
        _need(
            artifact["schema"] == "cairntir.paladin-ui-independent-review.v1"
            and artifact["review_id"] == review_id
            and artifact["candidate_id"] == bundle["manifest"]["candidate_id"]
            and artifact["candidate_manifest_sha256"] == bundle["manifest_sha256"]
            and artifact["expected_revision"] == head
            and artifact["scope"] == bundle["manifest"]["scope"]
            and artifact["decision"] in {"APPROVE", "REJECT"}
            and artifact["reviewed_images"] == self._images(bundle),
            "independent review binding mismatch",
        )
        for name, maximum in (("reviewer", 256), ("method", 1024), ("reason", 4096)):
            _need(
                isinstance(artifact[name], str)
                and 0 < len(artifact[name]) <= maximum
                and "\x00" not in artifact[name]
            )
        return artifact

    def _review_authority(self, candidate: dict[str, Any]) -> None:
        if isinstance(self._store, ScopedStore):
            self._store._authorize_complete_wing(self._contract["wing"])
            for capability in ("read", "write", "approve"):
                self._store.authorize(
                    capability, wing=self._contract["wing"], room=self._contract["room"]
                )
                self._store.authorize(capability, drawer_id=candidate["drawer_id"])

    @staticmethod
    def _candidate_head(bundle: dict[str, Any], terminal: dict[str, Any] | None) -> str:
        return _digest(
            {"candidate": bundle, "review": None if terminal is None else terminal["result"]}
        )

    @_boundary
    def review_baseline(
        self,
        *,
        candidate_id: str,
        expected_revision: dict[str, Any],
        review_evidence: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Apply an independent reviewed decision with live authority and CAS."""
        _uuid(candidate_id)
        _uuid(idempotency_key)
        expected_revision = deepcopy(self._head(expected_revision))
        review_evidence = deepcopy(_record(review_evidence, "path sha256 bytes"))
        self._context()
        _, rows, managed = self._records()
        candidates, _, active, terminal = self._history(rows, managed)
        _need(candidate_id in candidates, "candidate is not authenticated")
        bundle, evidence = candidates[candidate_id]
        request = {
            "baseline_id": self._contract["baseline_id"],
            "wing": self._contract["wing"],
            "room": self._contract["room"],
            "task_id": self._contract["task_id"],
            "candidate_id": candidate_id,
            "candidate": deepcopy(evidence),
            "expected_revision": expected_revision,
            "review_evidence": review_evidence,
            "idempotency_key": idempotency_key,
        }
        key = f"paladin-ui-baseline:{self._contract['baseline_id']}:review:{idempotency_key}"
        existing = next((row["result"] for row in rows if row["idempotency_key"] == key), None)
        if existing is not None:
            _need(existing["request"] == request, "review idempotency key cannot be rebound")
            self._context()
            return {
                "review": deepcopy(existing["result"]),
                "evidence": deepcopy(existing["evidence"]),
                "replayed": True,
            }
        self._context(active=True, approve=True)
        self._review_authority(evidence)
        head = active["head"] if active else {"generation": 0, "revision_sha256": None}
        _need(
            expected_revision == head and candidate_id not in terminal,
            "candidate or active baseline CAS mismatch",
        )
        artifact = self._review_file(review_evidence, bundle, head, idempotency_key, rows)
        if self._approval is None:
            raise PaladinUIError("independent startup approval callback required")
        proposed = self._approved_manifest(bundle, head)
        candidate_head = self._candidate_head(bundle, terminal.get(candidate_id))
        callback_request = {
            "candidate": deepcopy(bundle["manifest"]),
            "candidate_evidence": deepcopy(evidence),
            "candidate_manifest_sha256": bundle["manifest_sha256"],
            "expected_revision": deepcopy(head),
            "candidate_head_sha256": candidate_head,
            "proposed_manifest": deepcopy(proposed),
            "proposed_revision_sha256": _digest(proposed),
            "review_evidence": deepcopy(review_evidence),
        }
        try:
            decision = self._approval(deepcopy(callback_request))
        except Exception as exc:
            raise PaladinUIError("independent review callback failed") from exc
        _need(
            type(decision) is bool and decision == (artifact["decision"] == "APPROVE"),
            "callback did not return the exact reviewed boolean decision",
        )
        self._context(active=True, approve=True)
        with self._store.transaction():
            self._review_authority(evidence)
            _, current_rows, current_managed = self._records()
            current_candidates, _, current_active, current_terminal = self._history(
                current_rows, current_managed
            )
            current_head = (
                current_active["head"]
                if current_active
                else {"generation": 0, "revision_sha256": None}
            )
            _need(
                candidate_id in current_candidates
                and current_candidates[candidate_id] == (bundle, evidence)
                and current_head == head
                and self._candidate_head(bundle, current_terminal.get(candidate_id))
                == candidate_head,
                "baseline or candidate changed during independent review",
            )
            _need(
                self._review_file(review_evidence, bundle, head, idempotency_key, current_rows)
                == artifact,
                "review artifact changed during callback",
            )
            outcome = {
                "schema": "cairntir.paladin-ui-baseline-review.v1",
                "review_id": idempotency_key,
                "candidate_id": candidate_id,
                "candidate_manifest_sha256": bundle["manifest_sha256"],
                "decision": "APPROVED" if decision else "REJECTED",
                "before": deepcopy(head),
                "after": {
                    "generation": proposed["generation"],
                    "revision_sha256": _digest(proposed),
                }
                if decision
                else deepcopy(head),
                "review_evidence": deepcopy(review_evidence),
                "candidate": deepcopy(evidence),
                "approval_manifest": deepcopy(proposed) if decision else None,
            }
            saved = self._save(key, "review", request, outcome)
            self._review_authority(evidence)
        self._records()
        self._context()
        return {
            "review": deepcopy(saved["result"]),
            "evidence": deepcopy(saved["evidence"]),
            "replayed": False,
        }

    def _verify_selected_baseline(self, selected: dict[str, Any] | None) -> None:
        if selected is None:
            return
        manifest = selected["manifest"]
        _need(selected["head"]["revision_sha256"] == _digest(manifest))
        for row in manifest["images"]:
            path = _absolute_file(row["png"], 8388608)
            _png(path, row["width"], row["height"])
        _need(
            self._evidence(selected["approval"]["drawer_id"]) == selected["approval"],
            "approval evidence changed",
        )

    @_boundary
    def report(self) -> dict[str, Any]:
        """Read current qualification and complete immutable result/review history."""
        self._context()
        records, rows, managed = self._records()
        _, reviews, active, _ = self._history(rows, managed)
        qualification: dict[str, Any] = {"status": "CURRENT", "diagnostics": []}
        try:
            self._qualify()
        except AccessDenied:
            raise
        except (CairntirError, OSError, ValueError, TypeError, KeyError, RuntimeError):
            qualification = {"status": "STALE", "diagnostics": ["INPUT_OR_TOOL_CHANGED"]}
        selected_rows = [
            item["approved_baseline"]["reference"]
            for item in self._attempts.values()
            if item["approved_baseline"] is not None
        ]
        selected = selected_rows[0] if selected_rows else None
        _need(
            all(row == selected for row in selected_rows),
            "run selects conflicting baseline approvals",
        )
        if selected is not None and selected != active:
            qualification["status"] = "STALE"
            qualification["diagnostics"].append("ACTIVE_BASELINE_CHANGED")
        try:
            self._verify_selected_baseline(active)
            if active is not None:
                approved = next(
                    row["review"]
                    for row in reviews
                    if row["review"]["review_id"] == active["approval_id"]
                )
                _absolute_file(approved["review_evidence"], 131072)
        except AccessDenied:
            raise
        except (CairntirError, OSError, ValueError, TypeError, KeyError, RuntimeError):
            qualification["status"] = "UNAVAILABLE"
            qualification["diagnostics"].append("APPROVED_BASELINE_UNAVAILABLE")
        attempts, evidence_ids = [], []
        for identity, attempt in self._attempts.items():
            prefix = f"attempt:{identity}:"
            prepared, saved = records.get(prefix + "prepare"), records.get(prefix + "result")
            status, result, evidence = "PENDING", None, None
            if prepared is not None:
                status = (
                    "RECOVERY_REQUIRED"
                    if self._outcome(managed, prepared["request"]["action"]["action_id"])
                    else "UNCERTAIN"
                )
            if saved is not None:
                result, evidence = deepcopy(saved["result"]), deepcopy(saved["evidence"])
                status = result["status"]
                try:
                    _need(
                        _inventory(_path(attempt["template"]["output_root"]), 4096, 134217728)
                        == result["artifacts"],
                        "historical output changed",
                    )
                except (CairntirError, OSError, ValueError, TypeError, KeyError, RuntimeError):
                    qualification["status"] = "STALE"
                    qualification["diagnostics"].append("ARTIFACT_CHANGED")
                evidence_ids.extend([evidence["drawer_id"], *result["evidence_ids"]])
            attempts.append(
                {"attempt_id": identity, "status": status, "result": result, "evidence": evidence}
            )
        for row in records.values():
            evidence_ids.append(row["evidence"]["drawer_id"])
        for row in reviews:
            evidence_ids.extend(
                (row["evidence"]["drawer_id"], row["review"]["candidate"]["drawer_id"])
            )
        qualification["diagnostics"] = list(dict.fromkeys(qualification["diagnostics"]))
        complete = (
            self._contract["mode"] == "compare"
            and selected is not None
            and selected == active
            and qualification["status"] == "CURRENT"
            and all(row["status"] == "PASS" for row in attempts)
        )
        report = {
            "schema": "cairntir.paladin-ui-report.v1",
            "run_id": self._contract["run_id"],
            "task_id": self._contract["task_id"],
            "contract_sha256": self._digest,
            "disposition": "COMPLETE" if complete else "BLOCKED",
            "qualification": qualification,
            "baseline": {
                "selected": deepcopy(selected),
                "active": deepcopy(active),
                "reviews": reviews,
            },
            "attempts": attempts,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
        }
        _canonical(report, 2097152)
        final_records, final_rows, final_managed = self._records()
        _, final_reviews, final_active, _ = self._history(final_rows, final_managed)
        _need(
            final_records == records and final_reviews == reviews and final_active == active,
            "history changed during report",
        )
        self._context()
        return report


_WIRE: dict[str, Any] = json.loads(r"""
{
  "sha": {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$"
  },
  "uuid": {
    "type": "string",
    "format": "uuid",
    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
  },
  "id": {
    "type": "string",
    "minLength": 2,
    "maxLength": 128,
    "pattern": "^[a-z0-9][a-z0-9._:-]*[a-z0-9]$"
  },
  "projectId": {
    "type": "string",
    "minLength": 2,
    "maxLength": 64,
    "pattern": "^[a-z0-9][a-z0-9._:-]{0,62}[a-z0-9]$"
  },
  "text": {
    "type": "string",
    "minLength": 1,
    "maxLength": 512
  },
  "selector": {
    "type": "string",
    "minLength": 1,
    "maxLength": 512
  },
  "relative": {
    "type": "string",
    "minLength": 1,
    "maxLength": 512,
    "pattern": "^[^\\\\:\\r\\n\\u0000]+$"
  },
  "absolute": {
    "type": "string",
    "minLength": 1,
    "maxLength": 2048
  },
  "artifact": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "path",
      "sha256",
      "bytes"
    ],
    "properties": {
      "path": {
        "$ref": "#/$defs/relative"
      },
      "sha256": {
        "$ref": "#/$defs/sha"
      },
      "bytes": {
        "type": "integer",
        "minimum": 0,
        "maximum": 134217728
      }
    }
  },
  "fileReference": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "path",
      "sha256",
      "bytes"
    ],
    "properties": {
      "path": {
        "$ref": "#/$defs/absolute"
      },
      "sha256": {
        "$ref": "#/$defs/sha"
      },
      "bytes": {
        "type": "integer",
        "minimum": 0,
        "maximum": 2097152
      }
    }
  },
  "projectFile": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "path",
      "sha256",
      "bytes",
      "media_type"
    ],
    "properties": {
      "path": {
        "$ref": "#/$defs/relative"
      },
      "sha256": {
        "$ref": "#/$defs/sha"
      },
      "bytes": {
        "type": "integer",
        "minimum": 0,
        "maximum": 8388608
      },
      "media_type": {
        "type": "string",
        "enum": [
          "text/html",
          "text/css",
          "text/javascript",
          "font/ttf",
          "image/png",
          "image/svg+xml",
          "text/plain"
        ]
      }
    }
  },
  "project": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "project_id",
      "route_id",
      "state_id",
      "source_revision",
      "snapshot_root",
      "snapshot_sha256",
      "files",
      "entry_path"
    ],
    "properties": {
      "project_id": {
        "$ref": "#/$defs/projectId"
      },
      "route_id": {
        "$ref": "#/$defs/id"
      },
      "state_id": {
        "const": "initial"
      },
      "source_revision": {
        "type": "string",
        "minLength": 1,
        "maxLength": 128
      },
      "snapshot_root": {
        "$ref": "#/$defs/absolute"
      },
      "snapshot_sha256": {
        "$ref": "#/$defs/sha"
      },
      "files": {
        "type": "array",
        "minItems": 1,
        "maxItems": 128,
        "items": {
          "$ref": "#/$defs/projectFile"
        }
      },
      "entry_path": {
        "$ref": "#/$defs/relative"
      }
    }
  },
  "toolFile": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "path",
      "sha256",
      "bytes"
    ],
    "properties": {
      "path": {
        "$ref": "#/$defs/relative"
      },
      "sha256": {
        "$ref": "#/$defs/sha"
      },
      "bytes": {
        "type": "integer",
        "minimum": 0,
        "maximum": 1073741824
      }
    }
  },
  "tool": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "root",
      "entry_path",
      "version",
      "files"
    ],
    "properties": {
      "id": {
        "type": "string",
        "enum": [
          "python",
          "node",
          "playwright",
          "playwright-core",
          "chrome",
          "pngjs",
          "pixelmatch",
          "worker",
          "producer"
        ]
      },
      "root": {
        "$ref": "#/$defs/absolute"
      },
      "entry_path": {
        "$ref": "#/$defs/relative"
      },
      "version": {
        "$ref": "#/$defs/text"
      },
      "files": {
        "type": "array",
        "minItems": 1,
        "maxItems": 4096,
        "items": {
          "$ref": "#/$defs/toolFile"
        }
      }
    }
  },
  "selectedTools": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "tools",
      "packaged_chromium_version"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-tools.v1"
      },
      "tools": {
        "type": "array",
        "minItems": 9,
        "maxItems": 9,
        "items": {
          "$ref": "#/$defs/tool"
        }
      },
      "packaged_chromium_version": {
        "const": "151.0.7922.34"
      }
    }
  },
  "viewports": {
    "type": "array",
    "minItems": 2,
    "maxItems": 2,
    "items": false,
    "prefixItems": [
      {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "width",
          "height",
          "device_scale_factor"
        ],
        "properties": {
          "id": {
            "const": "mobile"
          },
          "width": {
            "const": 375
          },
          "height": {
            "const": 800
          },
          "device_scale_factor": {
            "const": 1
          }
        }
      },
      {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "width",
          "height",
          "device_scale_factor"
        ],
        "properties": {
          "id": {
            "const": "desktop"
          },
          "width": {
            "const": 1280
          },
          "height": {
            "const": 800
          },
          "device_scale_factor": {
            "const": 1
          }
        }
      }
    ]
  },
  "font": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "path",
      "sha256",
      "license_path",
      "license_sha256",
      "css_family",
      "platform_family",
      "postscript_name",
      "text_selectors"
    ],
    "properties": {
      "path": {
        "$ref": "#/$defs/relative"
      },
      "sha256": {
        "const": "c4c45690b345435b2cba52ecabe275f05e49b389b39fe68ad03afbb551288d3d"
      },
      "license_path": {
        "$ref": "#/$defs/relative"
      },
      "license_sha256": {
        "const": "3361d054759a2fc686a2c058be82deaf9c2e6fe549be9004d7935a6c1736315d"
      },
      "css_family": {
        "$ref": "#/$defs/text"
      },
      "platform_family": {
        "$ref": "#/$defs/text"
      },
      "postscript_name": {
        "$ref": "#/$defs/text"
      },
      "text_selectors": {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "uniqueItems": true,
        "items": {
          "$ref": "#/$defs/selector"
        }
      }
    }
  },
  "renderPolicy": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "viewports",
      "locale",
      "timezone_id",
      "color_scheme",
      "reduced_motion",
      "font",
      "screenshot"
    ],
    "properties": {
      "viewports": {
        "$ref": "#/$defs/viewports"
      },
      "locale": {
        "const": "en-US"
      },
      "timezone_id": {
        "const": "UTC"
      },
      "color_scheme": {
        "const": "light"
      },
      "reduced_motion": {
        "const": "reduce"
      },
      "font": {
        "$ref": "#/$defs/font"
      },
      "screenshot": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "type",
          "full_page",
          "animations",
          "caret",
          "masks"
        ],
        "properties": {
          "type": {
            "const": "png"
          },
          "full_page": {
            "const": false
          },
          "animations": {
            "const": "disabled"
          },
          "caret": {
            "const": "hide"
          },
          "masks": {
            "type": "array",
            "maxItems": 0
          }
        }
      }
    }
  },
  "documentCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "property",
      "expected"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "document-equals"
      },
      "family": {
        "const": "accessibility"
      },
      "property": {
        "enum": [
          "language",
          "title"
        ]
      },
      "expected": {
        "$ref": "#/$defs/text"
      }
    }
  },
  "axCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "selector",
      "role",
      "name"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "ax-role-name"
      },
      "family": {
        "const": "accessibility"
      },
      "selector": {
        "$ref": "#/$defs/selector"
      },
      "role": {
        "$ref": "#/$defs/text"
      },
      "name": {
        "$ref": "#/$defs/text"
      }
    }
  },
  "tabCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "start_selector",
      "expected_focus"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "keyboard-tab-order"
      },
      "family": {
        "const": "accessibility"
      },
      "start_selector": {
        "$ref": "#/$defs/selector"
      },
      "expected_focus": {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "items": {
          "$ref": "#/$defs/selector"
        }
      }
    }
  },
  "keyCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "key",
      "control",
      "panel",
      "expanded",
      "visible"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "keyboard-key-state"
      },
      "family": {
        "const": "accessibility"
      },
      "key": {
        "enum": [
          "Enter",
          "Space"
        ]
      },
      "control": {
        "$ref": "#/$defs/selector"
      },
      "panel": {
        "$ref": "#/$defs/selector"
      },
      "expanded": {
        "type": "boolean"
      },
      "visible": {
        "type": "boolean"
      }
    }
  },
  "visibleCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "selectors",
      "tolerance_css_pixels"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "required-visible"
      },
      "family": {
        "const": "responsive"
      },
      "selectors": {
        "type": "array",
        "minItems": 1,
        "maxItems": 32,
        "uniqueItems": true,
        "items": {
          "$ref": "#/$defs/selector"
        }
      },
      "tolerance_css_pixels": {
        "const": 1
      }
    }
  },
  "overflowCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "maximum_css_pixels"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "horizontal-overflow"
      },
      "family": {
        "const": "responsive"
      },
      "maximum_css_pixels": {
        "const": 1
      }
    }
  },
  "visualCheck": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "kind",
      "family",
      "threshold",
      "includeAA",
      "allowed_diff_ratio",
      "alpha",
      "aaColor",
      "diffColor",
      "diffColorAlt",
      "diffMask",
      "checkerboard"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "kind": {
        "const": "rgba-diff"
      },
      "family": {
        "const": "visual"
      },
      "threshold": {
        "const": 0.1
      },
      "includeAA": {
        "const": true
      },
      "allowed_diff_ratio": {
        "const": 0.001
      },
      "alpha": {
        "const": 0.1
      },
      "aaColor": {
        "const": [
          255,
          255,
          0
        ]
      },
      "diffColor": {
        "const": [
          255,
          0,
          0
        ]
      },
      "diffColorAlt": {
        "const": null
      },
      "diffMask": {
        "const": false
      },
      "checkerboard": {
        "const": true
      }
    }
  },
  "check": {
    "oneOf": [
      {
        "$ref": "#/$defs/documentCheck"
      },
      {
        "$ref": "#/$defs/axCheck"
      },
      {
        "$ref": "#/$defs/tabCheck"
      },
      {
        "$ref": "#/$defs/keyCheck"
      },
      {
        "$ref": "#/$defs/visibleCheck"
      },
      {
        "$ref": "#/$defs/overflowCheck"
      },
      {
        "$ref": "#/$defs/visualCheck"
      }
    ]
  },
  "evidenceReference": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "drawer_id",
      "source_identity",
      "content_sha256"
    ],
    "properties": {
      "drawer_id": {
        "type": "integer",
        "minimum": 1
      },
      "source_identity": {
        "$ref": "#/$defs/uuid"
      },
      "content_sha256": {
        "$ref": "#/$defs/sha"
      }
    }
  },
  "baselineReference": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "baseline_id",
      "generation",
      "revision_sha256",
      "approval_id",
      "approval",
      "manifest_file",
      "baseline_origin_snapshot_sha256"
    ],
    "properties": {
      "baseline_id": {
        "$ref": "#/$defs/uuid"
      },
      "generation": {
        "type": "integer",
        "minimum": 1
      },
      "revision_sha256": {
        "$ref": "#/$defs/sha"
      },
      "approval_id": {
        "$ref": "#/$defs/uuid"
      },
      "approval": {
        "$ref": "#/$defs/evidenceReference"
      },
      "manifest_file": {
        "$ref": "#/$defs/fileReference"
      },
      "baseline_origin_snapshot_sha256": {
        "$ref": "#/$defs/sha"
      }
    }
  },
  "template": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "mode",
      "project",
      "output_root",
      "selected_tools",
      "render_policy",
      "checks",
      "baseline_reference"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-producer-template.v1"
      },
      "mode": {
        "enum": [
          "capture-baseline",
          "compare"
        ]
      },
      "project": {
        "$ref": "#/$defs/project"
      },
      "output_root": {
        "$ref": "#/$defs/absolute"
      },
      "selected_tools": {
        "$ref": "#/$defs/fileReference"
      },
      "render_policy": {
        "$ref": "#/$defs/renderPolicy"
      },
      "checks": {
        "type": "array",
        "minItems": 3,
        "maxItems": 64,
        "items": {
          "$ref": "#/$defs/check"
        }
      },
      "baseline_reference": {
        "oneOf": [
          {
            "type": "null"
          },
          {
            "$ref": "#/$defs/baselineReference"
          }
        ]
      }
    },
    "allOf": [
      {
        "if": {
          "properties": {
            "mode": {
              "const": "capture-baseline"
            }
          }
        },
        "then": {
          "properties": {
            "baseline_reference": {
              "type": "null"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "mode": {
              "const": "compare"
            }
          }
        },
        "then": {
          "properties": {
            "baseline_reference": {
              "$ref": "#/$defs/baselineReference"
            }
          }
        }
      }
    ]
  },
  "request": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "run_id",
      "attempt_id",
      "action_id",
      "contract_sha256",
      "template_sha256",
      "template"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-producer.v1"
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "contract_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template": {
        "$ref": "#/$defs/template"
      }
    }
  },
  "rect": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "x",
      "y",
      "width",
      "height"
    ],
    "properties": {
      "x": {
        "type": "number"
      },
      "y": {
        "type": "number"
      },
      "width": {
        "type": "number"
      },
      "height": {
        "type": "number"
      }
    }
  },
  "activeElement": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "tag_name",
      "id"
    ],
    "properties": {
      "tag_name": {
        "type": "string",
        "maxLength": 128
      },
      "id": {
        "type": "string",
        "maxLength": 512
      }
    }
  },
  "documentObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "value"
    ],
    "properties": {
      "value": {
        "type": "string",
        "maxLength": 4096
      }
    }
  },
  "axObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "selector_count",
      "backend_node_id",
      "ax_node_id",
      "ignored",
      "role",
      "name"
    ],
    "properties": {
      "selector_count": {
        "type": "integer",
        "minimum": 0,
        "maximum": 512
      },
      "backend_node_id": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "ax_node_id": {
        "type": [
          "string",
          "null"
        ],
        "maxLength": 128
      },
      "ignored": {
        "type": [
          "boolean",
          "null"
        ]
      },
      "role": {
        "type": [
          "string",
          "null"
        ],
        "maxLength": 512
      },
      "name": {
        "type": [
          "string",
          "null"
        ],
        "maxLength": 4096
      }
    }
  },
  "tabObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "initial",
      "start_matches",
      "steps"
    ],
    "properties": {
      "initial": {
        "$ref": "#/$defs/activeElement"
      },
      "start_matches": {
        "type": "boolean"
      },
      "steps": {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "key",
            "actual",
            "expected_selector_matches"
          ],
          "properties": {
            "key": {
              "const": "Tab"
            },
            "actual": {
              "$ref": "#/$defs/activeElement"
            },
            "expected_selector_matches": {
              "type": "boolean"
            }
          }
        }
      }
    }
  },
  "keyObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "actual_focus",
      "control_focused",
      "control_count",
      "panel_count",
      "expanded",
      "panel_visible"
    ],
    "properties": {
      "actual_focus": {
        "$ref": "#/$defs/activeElement"
      },
      "control_focused": {
        "type": "boolean"
      },
      "control_count": {
        "type": "integer",
        "minimum": 0,
        "maximum": 512
      },
      "panel_count": {
        "type": "integer",
        "minimum": 0,
        "maximum": 512
      },
      "expanded": {
        "type": [
          "string",
          "null"
        ],
        "maxLength": 128
      },
      "panel_visible": {
        "type": "boolean"
      }
    }
  },
  "visibleObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "elements"
    ],
    "properties": {
      "elements": {
        "type": "array",
        "minItems": 1,
        "maxItems": 32,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "selector",
            "count",
            "rect",
            "visible",
            "within_viewport"
          ],
          "properties": {
            "selector": {
              "$ref": "#/$defs/selector"
            },
            "count": {
              "type": "integer",
              "minimum": 0,
              "maximum": 512
            },
            "rect": {
              "oneOf": [
                {
                  "type": "null"
                },
                {
                  "$ref": "#/$defs/rect"
                }
              ]
            },
            "visible": {
              "type": "boolean"
            },
            "within_viewport": {
              "type": "boolean"
            }
          }
        }
      }
    }
  },
  "overflowObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "scroll_width",
      "client_width",
      "viewport_width",
      "overflow_css_pixels"
    ],
    "properties": {
      "scroll_width": {
        "type": "integer",
        "minimum": 0
      },
      "client_width": {
        "type": "integer",
        "minimum": 0
      },
      "viewport_width": {
        "type": "integer",
        "minimum": 1
      },
      "overflow_css_pixels": {
        "type": "integer",
        "minimum": 0
      }
    }
  },
  "visualObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "current",
      "baseline",
      "diff",
      "width",
      "height",
      "compared_pixels",
      "mismatched_pixels",
      "exact_changed_pixels",
      "allowed_diff_pixels",
      "diff_ratio"
    ],
    "properties": {
      "current": {
        "$ref": "#/$defs/artifact"
      },
      "baseline": {
        "oneOf": [
          {
            "type": "null"
          },
          {
            "$ref": "#/$defs/artifact"
          }
        ]
      },
      "diff": {
        "oneOf": [
          {
            "type": "null"
          },
          {
            "$ref": "#/$defs/artifact"
          }
        ]
      },
      "width": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1280
      },
      "height": {
        "const": 800
      },
      "compared_pixels": {
        "type": "integer",
        "minimum": 0,
        "maximum": 1024000
      },
      "mismatched_pixels": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 0,
        "maximum": 1024000
      },
      "exact_changed_pixels": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 0,
        "maximum": 1024000
      },
      "allowed_diff_pixels": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 0,
        "maximum": 1024000
      },
      "diff_ratio": {
        "type": [
          "number",
          "null"
        ],
        "minimum": 0,
        "maximum": 1
      }
    }
  },
  "checkResult": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "check",
      "status",
      "observation",
      "evidence_paths",
      "diagnostic"
    ],
    "properties": {
      "check": {
        "$ref": "#/$defs/check"
      },
      "status": {
        "enum": [
          "PASS",
          "FAIL",
          "UNREVIEWED",
          "UNSUPPORTED",
          "ERROR"
        ]
      },
      "observation": {},
      "evidence_paths": {
        "type": "array",
        "minItems": 1,
        "maxItems": 8,
        "uniqueItems": true,
        "items": {
          "$ref": "#/$defs/relative"
        }
      },
      "diagnostic": {
        "type": [
          "string",
          "null"
        ],
        "maxLength": 4096
      }
    },
    "allOf": [
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "document-equals"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/documentObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "ax-role-name"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/axObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "keyboard-tab-order"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/tabObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "keyboard-key-state"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/keyObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "required-visible"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/visibleObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "horizontal-overflow"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/overflowObservation"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "check": {
              "properties": {
                "kind": {
                  "const": "rgba-diff"
                }
              }
            }
          }
        },
        "then": {
          "properties": {
            "observation": {
              "$ref": "#/$defs/visualObservation"
            }
          }
        },
        "else": {
          "properties": {
            "status": {
              "enum": [
                "PASS",
                "FAIL",
                "UNSUPPORTED",
                "ERROR"
              ]
            }
          }
        }
      }
    ]
  },
  "fontUsage": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "family_name",
      "postscript_name",
      "is_custom_font",
      "glyph_count"
    ],
    "properties": {
      "family_name": {
        "$ref": "#/$defs/text"
      },
      "postscript_name": {
        "$ref": "#/$defs/text"
      },
      "is_custom_font": {
        "type": "boolean"
      },
      "glyph_count": {
        "type": "integer",
        "minimum": 0
      }
    }
  },
  "fontObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "selector",
      "backend_node_id",
      "document_fonts_ready",
      "font_face_loaded",
      "computed_family",
      "fonts"
    ],
    "properties": {
      "selector": {
        "$ref": "#/$defs/selector"
      },
      "backend_node_id": {
        "type": "integer",
        "minimum": 1
      },
      "document_fonts_ready": {
        "type": "boolean"
      },
      "font_face_loaded": {
        "type": "boolean"
      },
      "computed_family": {
        "$ref": "#/$defs/text"
      },
      "fonts": {
        "type": "array",
        "maxItems": 16,
        "items": {
          "$ref": "#/$defs/fontUsage"
        }
      }
    }
  },
  "viewportResult": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "width",
      "height",
      "device_scale_factor",
      "checks",
      "font_observations"
    ],
    "properties": {
      "id": {
        "enum": [
          "mobile",
          "desktop"
        ]
      },
      "width": {
        "enum": [
          375,
          1280
        ]
      },
      "height": {
        "const": 800
      },
      "device_scale_factor": {
        "const": 1
      },
      "checks": {
        "type": "array",
        "minItems": 3,
        "maxItems": 64,
        "items": {
          "$ref": "#/$defs/checkResult"
        }
      },
      "font_observations": {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "items": {
          "$ref": "#/$defs/fontObservation"
        }
      }
    }
  },
  "toolObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "entry_path",
      "entry_sha256",
      "version"
    ],
    "properties": {
      "id": {
        "$ref": "#/$defs/id"
      },
      "entry_path": {
        "$ref": "#/$defs/absolute"
      },
      "entry_sha256": {
        "$ref": "#/$defs/sha"
      },
      "version": {
        "$ref": "#/$defs/text"
      }
    }
  },
  "pythonObservation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "id",
      "entry_path",
      "entry_sha256",
      "version",
      "isolated",
      "dont_write_bytecode",
      "optimize",
      "pycache_prefix",
      "cache_prefix_state"
    ],
    "properties": {
      "id": {
        "const": "python"
      },
      "entry_path": {
        "$ref": "#/$defs/absolute"
      },
      "entry_sha256": {
        "$ref": "#/$defs/sha"
      },
      "version": {
        "$ref": "#/$defs/text"
      },
      "isolated": {
        "const": true
      },
      "dont_write_bytecode": {
        "const": true
      },
      "optimize": {
        "const": 0
      },
      "pycache_prefix": {
        "$ref": "#/$defs/absolute"
      },
      "cache_prefix_state": {
        "enum": [
          "ABSENT",
          "EMPTY",
          "NONEMPTY"
        ]
      }
    }
  },
  "families": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "accessibility",
      "responsive",
      "visual"
    ],
    "properties": {
      "accessibility": {
        "enum": [
          "PASS",
          "FAIL",
          "INCONCLUSIVE"
        ]
      },
      "responsive": {
        "enum": [
          "PASS",
          "FAIL",
          "INCONCLUSIVE"
        ]
      },
      "visual": {
        "enum": [
          "PASS",
          "FAIL",
          "UNREVIEWED",
          "INCONCLUSIVE"
        ]
      }
    }
  },
  "report": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "status",
      "run_id",
      "attempt_id",
      "action_id",
      "contract_sha256",
      "request_sha256",
      "template_sha256",
      "mode",
      "project_id",
      "current_source_revision",
      "current_snapshot_sha256",
      "baseline_origin_snapshot_sha256",
      "baseline_reference",
      "selected_tools_sha256",
      "tool_observations",
      "policy_sha256",
      "renderer",
      "renderer_sha256",
      "browser_lifecycle",
      "viewports",
      "families",
      "diagnostics",
      "raw_artifacts"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-producer-result.v1"
      },
      "status": {
        "enum": [
          "COMPLETE",
          "INCONCLUSIVE"
        ]
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "contract_sha256": {
        "$ref": "#/$defs/sha"
      },
      "request_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template_sha256": {
        "$ref": "#/$defs/sha"
      },
      "mode": {
        "enum": [
          "capture-baseline",
          "compare"
        ]
      },
      "project_id": {
        "$ref": "#/$defs/projectId"
      },
      "current_source_revision": {
        "type": "string",
        "minLength": 1,
        "maxLength": 128
      },
      "current_snapshot_sha256": {
        "$ref": "#/$defs/sha"
      },
      "baseline_origin_snapshot_sha256": {
        "oneOf": [
          {
            "type": "null"
          },
          {
            "$ref": "#/$defs/sha"
          }
        ]
      },
      "baseline_reference": {
        "oneOf": [
          {
            "type": "null"
          },
          {
            "$ref": "#/$defs/baselineReference"
          }
        ]
      },
      "selected_tools_sha256": {
        "$ref": "#/$defs/sha"
      },
      "tool_observations": {
        "type": "array",
        "minItems": 6,
        "maxItems": 6,
        "items": {
          "$ref": "#/$defs/toolObservation"
        }
      },
      "policy_sha256": {
        "$ref": "#/$defs/sha"
      },
      "renderer": {
        "$ref": "#/$defs/rendererFingerprint"
      },
      "renderer_sha256": {
        "$ref": "#/$defs/sha"
      },
      "browser_lifecycle": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "context_closed",
          "browser_closed",
          "disconnected_observed"
        ],
        "properties": {
          "context_closed": {
            "type": "boolean"
          },
          "browser_closed": {
            "type": "boolean"
          },
          "disconnected_observed": {
            "type": "boolean"
          }
        }
      },
      "viewports": {
        "type": "array",
        "minItems": 2,
        "maxItems": 2,
        "items": {
          "$ref": "#/$defs/viewportResult"
        }
      },
      "families": {
        "$ref": "#/$defs/families"
      },
      "diagnostics": {
        "type": "array",
        "maxItems": 128,
        "items": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4096
        }
      },
      "raw_artifacts": {
        "type": "array",
        "minItems": 11,
        "maxItems": 256,
        "items": {
          "$ref": "#/$defs/artifact"
        }
      }
    }
  },
  "rawDocument": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "language",
      "title",
      "url",
      "ready_state",
      "inner_width",
      "inner_height",
      "device_scale_factor",
      "scroll_width",
      "client_width",
      "active_element"
    ],
    "properties": {
      "language": {
        "type": "string",
        "maxLength": 4096
      },
      "title": {
        "type": "string",
        "maxLength": 4096
      },
      "url": {
        "type": "string",
        "maxLength": 2048
      },
      "ready_state": {
        "enum": [
          "loading",
          "interactive",
          "complete"
        ]
      },
      "inner_width": {
        "type": "integer",
        "minimum": 1
      },
      "inner_height": {
        "type": "integer",
        "minimum": 1
      },
      "device_scale_factor": {
        "type": "number",
        "exclusiveMinimum": 0
      },
      "scroll_width": {
        "type": "integer",
        "minimum": 0
      },
      "client_width": {
        "type": "integer",
        "minimum": 0
      },
      "active_element": {
        "$ref": "#/$defs/activeElement"
      }
    }
  },
  "rawElement": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "node_id",
      "backend_node_id",
      "tag_name",
      "id",
      "text_content",
      "rect",
      "visible",
      "display",
      "visibility",
      "opacity",
      "font_family"
    ],
    "properties": {
      "node_id": {
        "type": "integer",
        "minimum": 1
      },
      "backend_node_id": {
        "type": "integer",
        "minimum": 1
      },
      "tag_name": {
        "type": "string",
        "maxLength": 128
      },
      "id": {
        "type": "string",
        "maxLength": 512
      },
      "text_content": {
        "type": "string",
        "maxLength": 16384
      },
      "rect": {
        "$ref": "#/$defs/rect"
      },
      "visible": {
        "type": "boolean"
      },
      "display": {
        "type": "string",
        "maxLength": 128
      },
      "visibility": {
        "type": "string",
        "maxLength": 128
      },
      "opacity": {
        "type": "number",
        "minimum": 0,
        "maximum": 1
      },
      "font_family": {
        "type": "string",
        "maxLength": 512
      }
    }
  },
  "rawDOM": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "viewport_id",
      "document",
      "selectors"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-dom.v1"
      },
      "viewport_id": {
        "enum": [
          "mobile",
          "desktop"
        ]
      },
      "document": {
        "$ref": "#/$defs/rawDocument"
      },
      "selectors": {
        "type": "array",
        "minItems": 1,
        "maxItems": 32,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "selector",
            "count",
            "matches"
          ],
          "properties": {
            "selector": {
              "$ref": "#/$defs/selector"
            },
            "count": {
              "type": "integer",
              "minimum": 0,
              "maximum": 512
            },
            "matches": {
              "type": "array",
              "maxItems": 512,
              "items": {
                "$ref": "#/$defs/rawElement"
              }
            }
          }
        }
      }
    }
  },
  "cdpAXValue": {
    "type": "object",
    "required": [
      "type"
    ],
    "properties": {
      "type": {
        "type": "string",
        "maxLength": 128
      },
      "value": {
        "type": [
          "string",
          "number",
          "boolean",
          "null"
        ]
      },
      "relatedNodes": {
        "type": "array",
        "maxItems": 512
      },
      "sources": {
        "type": "array",
        "maxItems": 512
      }
    },
    "additionalProperties": true
  },
  "cdpAXNode": {
    "type": "object",
    "required": [
      "nodeId",
      "ignored"
    ],
    "properties": {
      "nodeId": {
        "type": "string",
        "maxLength": 128
      },
      "ignored": {
        "type": "boolean"
      },
      "backendDOMNodeId": {
        "type": "integer",
        "minimum": 1
      },
      "role": {
        "$ref": "#/$defs/cdpAXValue"
      },
      "chromeRole": {
        "$ref": "#/$defs/cdpAXValue"
      },
      "name": {
        "$ref": "#/$defs/cdpAXValue"
      },
      "description": {
        "$ref": "#/$defs/cdpAXValue"
      },
      "value": {
        "$ref": "#/$defs/cdpAXValue"
      },
      "parentId": {
        "type": "string",
        "maxLength": 128
      },
      "childIds": {
        "type": "array",
        "maxItems": 1024,
        "items": {
          "type": "string",
          "maxLength": 128
        }
      }
    },
    "additionalProperties": true
  },
  "rawAX": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "viewport_id",
      "nodes",
      "selector_mappings"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-ax.v1"
      },
      "viewport_id": {
        "enum": [
          "mobile",
          "desktop"
        ]
      },
      "nodes": {
        "type": "array",
        "minItems": 1,
        "maxItems": 1024,
        "items": {
          "$ref": "#/$defs/cdpAXNode"
        }
      },
      "selector_mappings": {
        "type": "array",
        "minItems": 1,
        "maxItems": 32,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "selector",
            "node_ids",
            "backend_node_ids",
            "ax_node_ids"
          ],
          "properties": {
            "selector": {
              "$ref": "#/$defs/selector"
            },
            "node_ids": {
              "type": "array",
              "maxItems": 512,
              "items": {
                "type": "integer",
                "minimum": 1
              }
            },
            "backend_node_ids": {
              "type": "array",
              "maxItems": 512,
              "items": {
                "type": "integer",
                "minimum": 1
              }
            },
            "ax_node_ids": {
              "type": "array",
              "maxItems": 1024,
              "items": {
                "type": "string",
                "maxLength": 128
              }
            }
          }
        }
      }
    }
  },
  "rawFonts": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "viewport_id",
      "font_path",
      "font_sha256",
      "license_sha256",
      "css_family",
      "platform_family",
      "postscript_name",
      "observations"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-fonts.v1"
      },
      "viewport_id": {
        "enum": [
          "mobile",
          "desktop"
        ]
      },
      "font_path": {
        "$ref": "#/$defs/relative"
      },
      "font_sha256": {
        "$ref": "#/$defs/sha"
      },
      "license_sha256": {
        "$ref": "#/$defs/sha"
      },
      "css_family": {
        "$ref": "#/$defs/text"
      },
      "platform_family": {
        "$ref": "#/$defs/text"
      },
      "postscript_name": {
        "$ref": "#/$defs/text"
      },
      "observations": {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "items": {
          "$ref": "#/$defs/fontObservation"
        }
      }
    }
  },
  "rawKeyboard": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "viewport_id",
      "initial_active_element",
      "events",
      "results"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-keyboard.v1"
      },
      "viewport_id": {
        "enum": [
          "mobile",
          "desktop"
        ]
      },
      "initial_active_element": {
        "$ref": "#/$defs/activeElement"
      },
      "events": {
        "type": "array",
        "minItems": 1,
        "maxItems": 128,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "ordinal",
            "check_id",
            "key",
            "active_element"
          ],
          "properties": {
            "ordinal": {
              "type": "integer",
              "minimum": 1,
              "maximum": 128
            },
            "check_id": {
              "$ref": "#/$defs/id"
            },
            "key": {
              "enum": [
                "Tab",
                "Enter",
                "Space"
              ]
            },
            "active_element": {
              "$ref": "#/$defs/activeElement"
            }
          }
        }
      },
      "results": {
        "type": "array",
        "minItems": 1,
        "maxItems": 64,
        "items": {
          "allOf": [
            {
              "$ref": "#/$defs/checkResult"
            },
            {
              "properties": {
                "check": {
                  "oneOf": [
                    {
                      "$ref": "#/$defs/tabCheck"
                    },
                    {
                      "$ref": "#/$defs/keyCheck"
                    }
                  ]
                }
              }
            }
          ]
        }
      }
    }
  },
  "rawNetwork": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "events"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-network.v1"
      },
      "events": {
        "type": "array",
        "maxItems": 256,
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "ordinal",
            "viewport_id",
            "url",
            "method",
            "resource_type",
            "decision",
            "project_path",
            "sha256"
          ],
          "properties": {
            "ordinal": {
              "type": "integer",
              "minimum": 1,
              "maximum": 256
            },
            "viewport_id": {
              "type": [
                "string",
                "null"
              ],
              "enum": [
                "mobile",
                "desktop",
                null
              ]
            },
            "url": {
              "type": "string",
              "minLength": 1,
              "maxLength": 2048
            },
            "method": {
              "type": "string",
              "minLength": 1,
              "maxLength": 16
            },
            "resource_type": {
              "type": "string",
              "minLength": 1,
              "maxLength": 32
            },
            "decision": {
              "enum": [
                "fulfilled",
                "blocked"
              ]
            },
            "project_path": {
              "oneOf": [
                {
                  "type": "null"
                },
                {
                  "$ref": "#/$defs/relative"
                }
              ]
            },
            "sha256": {
              "oneOf": [
                {
                  "type": "null"
                },
                {
                  "$ref": "#/$defs/sha"
                }
              ]
            }
          }
        }
      }
    }
  },
  "rawComparison": {
    "$ref": "#/$defs/visualObservation"
  },
  "rendererFingerprint": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "browser",
      "os",
      "font",
      "pngjs",
      "pixelmatch",
      "policy_sha256"
    ],
    "properties": {
      "browser": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "runtime_manifest_sha256",
          "version"
        ],
        "properties": {
          "runtime_manifest_sha256": {
            "$ref": "#/$defs/sha"
          },
          "version": {
            "$ref": "#/$defs/text"
          }
        }
      },
      "os": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "platform",
          "release",
          "arch"
        ],
        "properties": {
          "platform": {
            "$ref": "#/$defs/text"
          },
          "release": {
            "$ref": "#/$defs/text"
          },
          "arch": {
            "$ref": "#/$defs/text"
          }
        }
      },
      "font": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "file_sha256",
          "custom_family",
          "postscript_name"
        ],
        "properties": {
          "file_sha256": {
            "$ref": "#/$defs/sha"
          },
          "custom_family": {
            "$ref": "#/$defs/text"
          },
          "postscript_name": {
            "$ref": "#/$defs/text"
          }
        }
      },
      "pngjs": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "payload_sha256",
          "version"
        ],
        "properties": {
          "payload_sha256": {
            "$ref": "#/$defs/sha"
          },
          "version": {
            "$ref": "#/$defs/text"
          }
        }
      },
      "pixelmatch": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "payload_sha256",
          "version"
        ],
        "properties": {
          "payload_sha256": {
            "$ref": "#/$defs/sha"
          },
          "version": {
            "$ref": "#/$defs/text"
          }
        }
      },
      "policy_sha256": {
        "$ref": "#/$defs/sha"
      }
    }
  },
  "environmentControls": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "values",
      "absent"
    ],
    "properties": {
      "values": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "HOME",
          "USERPROFILE",
          "APPDATA",
          "LOCALAPPDATA",
          "TEMP",
          "TMP",
          "XDG_CONFIG_HOME",
          "XDG_CACHE_HOME",
          "XDG_DATA_HOME",
          "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"
        ],
        "properties": {
          "HOME": {
            "$ref": "#/$defs/absolute"
          },
          "USERPROFILE": {
            "$ref": "#/$defs/absolute"
          },
          "APPDATA": {
            "$ref": "#/$defs/absolute"
          },
          "LOCALAPPDATA": {
            "$ref": "#/$defs/absolute"
          },
          "TEMP": {
            "$ref": "#/$defs/absolute"
          },
          "TMP": {
            "$ref": "#/$defs/absolute"
          },
          "XDG_CONFIG_HOME": {
            "$ref": "#/$defs/absolute"
          },
          "XDG_CACHE_HOME": {
            "$ref": "#/$defs/absolute"
          },
          "XDG_DATA_HOME": {
            "$ref": "#/$defs/absolute"
          },
          "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": {
            "const": "1"
          }
        }
      },
      "absent": {
        "const": [
          "NODE_OPTIONS",
          "NODE_PATH",
          "HTTP_PROXY",
          "HTTPS_PROXY",
          "ALL_PROXY",
          "NO_PROXY",
          "PLAYWRIGHT_DOWNLOAD_HOST",
          "CAIRNTIR_HOME",
          "CAIRNTIR_GRANT_FILE"
        ]
      }
    }
  },
  "invocation": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "run_id",
      "attempt_id",
      "action_id",
      "contract_sha256",
      "request_sha256",
      "template_sha256",
      "selected_tools_sha256",
      "argv",
      "cwd",
      "environment_controls",
      "limits"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-invocation.v1"
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "contract_sha256": {
        "$ref": "#/$defs/sha"
      },
      "request_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template_sha256": {
        "$ref": "#/$defs/sha"
      },
      "selected_tools_sha256": {
        "$ref": "#/$defs/sha"
      },
      "argv": {
        "type": "array",
        "minItems": 3,
        "maxItems": 32,
        "items": {
          "type": "string",
          "maxLength": 2048
        }
      },
      "cwd": {
        "$ref": "#/$defs/absolute"
      },
      "environment_controls": {
        "$ref": "#/$defs/environmentControls"
      },
      "limits": {
        "$ref": "#/$defs/limits"
      }
    }
  },
  "ownershipError": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "stage",
      "type",
      "message"
    ],
    "properties": {
      "stage": {
        "enum": [
          "validate",
          "create",
          "assign",
          "resume",
          "wait",
          "cleanup",
          "close",
          "closure"
        ]
      },
      "type": {
        "$ref": "#/$defs/text"
      },
      "message": {
        "type": "string",
        "maxLength": 4096
      }
    }
  },
  "processState": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "argv",
      "cwd",
      "started_at",
      "finished_at",
      "timeout_seconds",
      "elapsed_seconds",
      "pid",
      "direct_process_handle",
      "job_handle",
      "suspended_creation",
      "assigned_owned_job",
      "direct_exit_code",
      "timed_out",
      "cancelled",
      "output_truncated",
      "job_total_processes",
      "job_active_processes",
      "owned_tree_exit_observed",
      "job_handle_closed",
      "direct_process_handle_closed",
      "cleanup_uncertain",
      "errors"
    ],
    "properties": {
      "argv": {
        "type": "array",
        "minItems": 1,
        "maxItems": 32,
        "items": {
          "type": "string",
          "maxLength": 2048
        }
      },
      "cwd": {
        "$ref": "#/$defs/absolute"
      },
      "started_at": {
        "type": [
          "string",
          "null"
        ],
        "format": "date-time"
      },
      "finished_at": {
        "type": [
          "string",
          "null"
        ],
        "format": "date-time"
      },
      "timeout_seconds": {
        "type": "number",
        "exclusiveMinimum": 0,
        "maximum": 120
      },
      "elapsed_seconds": {
        "type": "number",
        "minimum": 0
      },
      "pid": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "direct_process_handle": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "job_handle": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "suspended_creation": {
        "type": "boolean"
      },
      "assigned_owned_job": {
        "type": "boolean"
      },
      "direct_exit_code": {
        "type": [
          "integer",
          "null"
        ]
      },
      "timed_out": {
        "type": "boolean"
      },
      "cancelled": {
        "type": "boolean"
      },
      "output_truncated": {
        "type": "boolean"
      },
      "job_total_processes": {
        "type": "integer",
        "minimum": 0
      },
      "job_active_processes": {
        "type": "integer",
        "minimum": 0
      },
      "owned_tree_exit_observed": {
        "type": "boolean"
      },
      "job_handle_closed": {
        "type": "boolean"
      },
      "direct_process_handle_closed": {
        "type": "boolean"
      },
      "cleanup_uncertain": {
        "type": "boolean"
      },
      "errors": {
        "type": "array",
        "maxItems": 64,
        "items": {
          "$ref": "#/$defs/ownershipError"
        }
      }
    }
  },
  "ownership": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "phase",
      "run_id",
      "attempt_id",
      "action_id",
      "contract_sha256",
      "request_sha256",
      "template_sha256",
      "argv",
      "cwd",
      "started_at",
      "finished_at",
      "timeout_seconds",
      "elapsed_seconds",
      "python",
      "worker",
      "pid",
      "direct_process_handle",
      "job_handle",
      "suspended_creation",
      "assigned_owned_job",
      "direct_exit_code",
      "timed_out",
      "cancelled",
      "output_truncated",
      "job_total_processes",
      "job_active_processes",
      "owned_tree_exit_observed",
      "job_handle_closed",
      "direct_process_handle_closed",
      "cleanup_uncertain",
      "errors"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-ownership.v1"
      },
      "phase": {
        "enum": [
          "START",
          "EXIT"
        ]
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "contract_sha256": {
        "$ref": "#/$defs/sha"
      },
      "request_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template_sha256": {
        "$ref": "#/$defs/sha"
      },
      "argv": {
        "type": "array",
        "minItems": 3,
        "maxItems": 32,
        "items": {
          "type": "string",
          "maxLength": 2048
        }
      },
      "cwd": {
        "$ref": "#/$defs/absolute"
      },
      "started_at": {
        "type": "string",
        "format": "date-time"
      },
      "finished_at": {
        "type": [
          "string",
          "null"
        ],
        "format": "date-time"
      },
      "timeout_seconds": {
        "type": "number",
        "exclusiveMinimum": 0,
        "maximum": 120
      },
      "elapsed_seconds": {
        "type": "number",
        "minimum": 0
      },
      "python": {
        "$ref": "#/$defs/pythonObservation"
      },
      "worker": {
        "$ref": "#/$defs/toolObservation"
      },
      "pid": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "direct_process_handle": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "job_handle": {
        "type": [
          "integer",
          "null"
        ],
        "minimum": 1
      },
      "suspended_creation": {
        "type": "boolean"
      },
      "assigned_owned_job": {
        "type": "boolean"
      },
      "direct_exit_code": {
        "type": [
          "integer",
          "null"
        ]
      },
      "timed_out": {
        "type": "boolean"
      },
      "cancelled": {
        "type": "boolean"
      },
      "output_truncated": {
        "type": "boolean"
      },
      "job_total_processes": {
        "type": "integer",
        "minimum": 0
      },
      "job_active_processes": {
        "type": "integer",
        "minimum": 0
      },
      "owned_tree_exit_observed": {
        "type": "boolean"
      },
      "job_handle_closed": {
        "type": "boolean"
      },
      "direct_process_handle_closed": {
        "type": "boolean"
      },
      "cleanup_uncertain": {
        "type": "boolean"
      },
      "errors": {
        "type": "array",
        "maxItems": 64,
        "items": {
          "$ref": "#/$defs/ownershipError"
        }
      }
    }
  },
  "closure": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "run_id",
      "attempt_id",
      "action_id",
      "request_sha256",
      "files",
      "file_count",
      "total_bytes"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-closure.v1"
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "request_sha256": {
        "$ref": "#/$defs/sha"
      },
      "files": {
        "type": "array",
        "minItems": 1,
        "maxItems": 4095,
        "items": {
          "$ref": "#/$defs/artifact"
        }
      },
      "file_count": {
        "type": "integer",
        "minimum": 1,
        "maximum": 4095
      },
      "total_bytes": {
        "type": "integer",
        "minimum": 0,
        "maximum": 134217728
      }
    }
  },
  "summary": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "schema",
      "run_id",
      "attempt_id",
      "action_id",
      "contract_sha256",
      "request_sha256",
      "template_sha256",
      "report",
      "ownership",
      "closure"
    ],
    "properties": {
      "schema": {
        "const": "cairntir.paladin-ui-worker-summary.v1"
      },
      "run_id": {
        "$ref": "#/$defs/uuid"
      },
      "attempt_id": {
        "$ref": "#/$defs/uuid"
      },
      "action_id": {
        "$ref": "#/$defs/uuid"
      },
      "contract_sha256": {
        "$ref": "#/$defs/sha"
      },
      "request_sha256": {
        "$ref": "#/$defs/sha"
      },
      "template_sha256": {
        "$ref": "#/$defs/sha"
      },
      "report": {
        "$ref": "#/$defs/artifact"
      },
      "ownership": {
        "$ref": "#/$defs/artifact"
      },
      "closure": {
        "$ref": "#/$defs/artifact"
      }
    }
  },
  "limits": {
    "const": {
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
      "managed_timeout_seconds": 150
    }
  }
}
""")
