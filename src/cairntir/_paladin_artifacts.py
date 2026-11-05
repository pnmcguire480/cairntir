"""Read and bind standard tool artifacts without dispatching or changing files."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import lzma
import math
import re
import stat
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

from cairntir._paladin_contract import PaladinPythonError, contained_path


@dataclass(frozen=True)
class ArtifactEvidence:
    """Observed evidence and explicit gaps, independent of the process outcome."""

    artifacts: list[dict[str, str]]
    tests: dict[str, Any] | None
    coverage: dict[str, Any] | None
    diagnostics: list[str]
    failed: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PaladinPythonError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PaladinPythonError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PaladinPythonError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaladinPythonError(f"{label} must be a finite number")
    _require(math.isfinite(value), f"{label} must be finite")
    return float(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _junit(raw: bytes, required: list[list[str]]) -> dict[str, Any]:
    declarations = raw.replace(b"\0", b"").upper()
    _require(
        b"<!DOCTYPE" not in declarations and b"<!ENTITY" not in declarations,
        "JUnit document type/entity declarations are unsupported",
    )
    root = ET.fromstring(raw)  # noqa: S314 - declarations are rejected before XML parsing.
    _require(root.tag in {"testsuite", "testsuites"}, "JUnit root is not a test suite")
    cases = list(root.iter("testcase"))
    identifiers: list[list[str]] = []
    outcomes: dict[tuple[str, str], str] = {}
    for case in cases:
        identity = (case.get("classname", ""), case.get("name", ""))
        _require(all(part.strip() for part in identity), "JUnit case lacks its exact identity")
        _require(identity not in outcomes, "duplicate JUnit test identity")
        kinds = {child.tag for child in case if child.tag in {"failure", "error", "skipped"}}
        _require(len(kinds) <= 1, "JUnit case has contradictory outcomes")
        outcomes[identity] = next(iter(kinds), "passed")
        identifiers.append(list(identity))
    for suite in root.iter():
        if suite.tag not in {"testsuite", "testsuites"}:
            continue
        children = list(suite.iter("testcase"))
        counts = {
            "tests": len(children),
            "failures": sum(case.find("failure") is not None for case in children),
            "errors": sum(case.find("error") is not None for case in children),
            "skipped": sum(case.find("skipped") is not None for case in children),
        }
        for name, observed in counts.items():
            if name in suite.attrib:
                value = suite.attrib[name]
                _require(bool(re.fullmatch(r"[0-9]+", value)), f"invalid JUnit {name} count")
                _require(int(value) == observed, f"JUnit {name} summary differs from case nodes")
    for tag in ("failure", "error", "skipped"):
        _require(
            len(list(root.iter(tag))) == sum(len(list(case.iter(tag))) for case in cases),
            "JUnit outcome is not attached to a testcase",
        )
    return {
        "collected": len(cases),
        "passed": sum(value == "passed" for value in outcomes.values()),
        "failed": sum(value == "failure" for value in outcomes.values()),
        "errors": sum(value == "error" for value in outcomes.values()),
        "skipped": sum(value == "skipped" for value in outcomes.values()),
        "ids": identifiers,
        "cases": [
            {"classname": identity[0], "name": identity[1], "outcome": outcome}
            for identity, outcome in outcomes.items()
        ],
        "missing_required": [identity for identity in required if tuple(identity) not in outcomes],
        "required_not_passed": [
            identity
            for identity in required
            if outcomes.get((identity[0], identity[1])) != "passed"
        ],
    }


def _lines(value: object, label: str) -> set[int]:
    if not isinstance(value, list):
        raise PaladinPythonError(f"{label} must be a line array")
    _require(all(type(line) is int and line > 0 for line in value), f"invalid {label}")
    _require(len(set(value)) == len(value), f"duplicate {label}")
    return set(value)


def _summary(value: object, *, branches: bool) -> dict[str, int]:
    data = _object(value, "coverage summary")
    names = ["covered_lines", "num_statements", "missing_lines", "excluded_lines"]
    if branches:
        names += ["num_branches", "covered_branches", "missing_branches"]
    counts = {name: _integer(data.get(name), name) for name in names}
    _require(
        counts["covered_lines"] + counts["missing_lines"] == counts["num_statements"],
        "coverage statement counts disagree",
    )
    if branches:
        _require(
            counts["covered_branches"] + counts["missing_branches"] == counts["num_branches"],
            "coverage branch counts disagree",
        )
    numerator = counts["covered_lines"] + counts.get("covered_branches", 0)
    denominator = counts["num_statements"] + counts.get("num_branches", 0)
    computed = 100.0 * numerator / denominator if denominator else 100.0
    reported = _number(data.get("percent_covered"), "percent_covered")
    _require(
        math.isclose(reported, computed, rel_tol=1e-9, abs_tol=1e-6),
        "coverage percentage contradicts counts",
    )
    return counts


def _coverage(
    raw: bytes, gate: dict[str, Any], snapshot: Path, inputs: Mapping[str, str]
) -> dict[str, Any]:
    data = _object(
        json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_float=lambda value: _number(float(value), "JSON number"),
            parse_constant=lambda value: _number(float(value), "JSON constant"),
        ),
        "coverage",
    )
    meta = _object(data.get("meta"), "coverage meta")
    _require(
        type(meta.get("format")) is int and meta["format"] in {1, 2, 3},
        "unsupported coverage JSON format",
    )
    _require(type(meta.get("branch_coverage")) is bool, "coverage branch mode is missing")
    branches = meta["branch_coverage"]
    files = _object(data.get("files"), "coverage files")
    summaries: dict[str, dict[str, int]] = {}
    for name, value in files.items():
        normalized = name.replace("\\", "/")
        path = Path(normalized)
        if path.is_absolute():
            _require(
                path.resolve().is_relative_to(snapshot.resolve()),
                "coverage source escapes snapshot",
            )
            normalized = path.resolve().relative_to(snapshot.resolve()).as_posix()
        contained_path(snapshot, normalized)
        _require(normalized not in summaries, "duplicate normalized coverage source")
        item = _object(value, "coverage file")
        counts = _summary(item.get("summary"), branches=branches)
        executed = _lines(item.get("executed_lines"), "executed_lines")
        missing = _lines(item.get("missing_lines"), "missing_lines")
        excluded = _lines(item.get("excluded_lines"), "excluded_lines")
        _require(
            not (executed & missing or executed & excluded or missing & excluded),
            "coverage line sets overlap",
        )
        _require(
            len(executed) == counts["covered_lines"]
            and len(missing) == counts["missing_lines"]
            and len(excluded) == counts["excluded_lines"],
            "coverage line arrays contradict counts",
        )
        summaries[normalized] = counts
    totals = _summary(data.get("totals"), branches=branches)
    _require(
        all(
            sum(summary[name] for summary in summaries.values()) == count
            for name, count in totals.items()
        ),
        "coverage totals differ from files",
    )
    paths = gate["source_paths"]
    _require(
        all(path in summaries and path in inputs for path in paths),
        "required bound coverage source is missing",
    )
    covered = sum(summaries[path]["covered_lines"] for path in paths)
    total = sum(summaries[path]["num_statements"] for path in paths)
    _require(total > 0, "required coverage denominator is empty")
    return {
        "covered_statements": covered,
        "total_statements": total,
        "percent": 100.0 * covered / total,
        "source_paths": list(paths),
    }


def _zip_name(value: str) -> str:
    _require(
        bool(value) and "\\" not in value and ":" not in value and "\0" not in value,
        "invalid wheel member path",
    )
    path = PurePosixPath(value)
    _require(
        not path.is_absolute() and all(part not in {"", ".", ".."} for part in value.split("/")),
        "wheel member path escapes or is ambiguous",
    )
    return value


def _wheel(
    raw: bytes, members: list[dict[str, str]], snapshot: Path, inputs: Mapping[str, str]
) -> None:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        contents: dict[str, bytes] = {}
        seen: set[str] = set()
        for info in archive.infolist():
            _require(info.orig_filename == info.filename, "truncated wheel member name")
            name = _zip_name(info.filename.removesuffix("/") if info.is_dir() else info.filename)
            _require(name.casefold() not in seen, "duplicate wheel member")
            seen.add(name.casefold())
            _require(
                not stat.S_ISLNK(info.external_attr >> 16), "wheel symlink member is unsupported"
            )
            if not info.is_dir():
                contents[name] = archive.read(info)
    metadata_roots = {
        name.split("/")[0] for name in contents if name.split("/")[0].endswith(".dist-info")
    }
    _require(len(metadata_roots) == 1, "wheel must contain one distribution metadata directory")
    info_root = next(iter(metadata_roots))
    _require(
        all(f"{info_root}/{name}" in contents for name in ("METADATA", "WHEEL", "RECORD")),
        "wheel metadata is incomplete",
    )
    metadata = BytesParser().parsebytes(contents[f"{info_root}/METADATA"])
    wheel = BytesParser().parsebytes(contents[f"{info_root}/WHEEL"])
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
        info_root.lower() == expected_root.lower(), "wheel distribution identity is inconsistent"
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
        and all(re.fullmatch(r"[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+", tag) for tag in tags),
        "invalid wheel compatibility tags",
    )
    record_name = f"{info_root}/RECORD"
    records: dict[str, tuple[str, str]] = {}
    for row in csv.reader(
        io.StringIO(contents[record_name].decode("utf-8"), newline=""), strict=True
    ):
        _require(len(row) == 3, "invalid wheel RECORD row")
        entry = _zip_name(row[0])
        _require(entry not in records, "duplicate wheel RECORD entry")
        records[entry] = (row[1], row[2])
    signatures = {f"{info_root}/RECORD.jws", f"{info_root}/RECORD.p7s"}
    _require(
        set(records) == set(contents) - signatures, "wheel RECORD inventory differs from archive"
    )
    for entry, (digest, size) in records.items():
        if entry == record_name:
            _require(not digest and not size, "wheel RECORD cannot hash itself")
            continue
        _require(
            bool(re.fullmatch(r"[0-9]+", size)) and int(size) == len(contents[entry]),
            "wheel RECORD size differs from member",
        )
        algorithm, separator, encoded = digest.partition("=")
        _require(bool(separator), "wheel RECORD lacks a secure hash")
        hasher = hashlib.new(algorithm)
        _require(hasher.digest_size >= 32, "wheel RECORD hash algorithm is too weak")
        hasher.update(contents[entry])
        computed = base64.urlsafe_b64encode(hasher.digest()).rstrip(b"=").decode("ascii")
        _require(encoded == computed, "wheel RECORD hash differs from member")
    for binding in members:
        member, source = binding["member"], binding["source_path"]
        _require(member in contents and source in inputs, "required wheel source/member is missing")
        source_bytes = contained_path(snapshot, source).read_bytes()
        _require(
            hashlib.sha256(source_bytes).hexdigest() == inputs[source],
            "wheel source binding changed",
        )
        _require(contents[member] == source_bytes, "wheel member differs from bound source")


def collect_artifacts(
    stage: dict[str, Any],
    *,
    output_root: Path,
    snapshot_root: Path,
    input_hashes: Mapping[str, str],
) -> ArtifactEvidence:
    """Bind each observed output and preserve failures even beside malformed evidence."""
    artifacts: list[dict[str, str]] = []
    tests: dict[str, Any] | None = None
    coverage: dict[str, Any] | None = None
    diagnostics: list[str] = []
    failed = False
    for artifact in stage["artifacts"]:
        name, kind = artifact["path"], artifact["format"]
        try:
            raw = contained_path(output_root, name).read_bytes()
            artifacts.append(
                {"path": name, "format": kind, "sha256": hashlib.sha256(raw).hexdigest()}
            )
            if kind == "junit":
                _require(tests is None, "multiple JUnit reports have ambiguous test ownership")
                tests = _junit(raw, stage["required_test_ids"])
                required_not_passed = tests.pop("required_not_passed")
                failed = failed or bool(tests["failed"] or tests["errors"])
                if not tests["collected"] or required_not_passed:
                    diagnostics.append(f"{name}: required tests were not all collected and passed")
                if tests["failed"] or tests["errors"]:
                    diagnostics.append(f"{name}: test failures or errors were observed")
            elif kind == "coverage-json":
                _require(
                    coverage is None and stage["coverage"] is not None,
                    "coverage report has no unique declared gate",
                )
                coverage = _coverage(raw, stage["coverage"], snapshot_root, input_hashes)
                if coverage["percent"] < stage["coverage"]["minimum_percent"]:
                    failed = True
                    diagnostics.append(
                        f"{name}: required statement coverage is below the frozen minimum"
                    )
            elif kind == "wheel":
                _wheel(raw, artifact["required_members"], snapshot_root, input_hashes)
            else:
                _require(kind == "file", "unsupported artifact format")
        except (
            PaladinPythonError,
            OSError,
            ValueError,
            OverflowError,
            ET.ParseError,
            csv.Error,
            zipfile.BadZipFile,
            zlib.error,
            lzma.LZMAError,
            RuntimeError,
        ) as exc:
            diagnostics.append(f"{name}: {exc}")
    return ArtifactEvidence(artifacts, tests, coverage, diagnostics, failed)
