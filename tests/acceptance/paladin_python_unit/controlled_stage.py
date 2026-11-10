"""Public parser/lifecycle child; not evidence that Ruff/pytest/build ran."""

import base64
import csv
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

stage, snapshot_arg, output_arg = sys.argv[1:]
snapshot, output = Path(snapshot_arg), Path(output_arg)
source = snapshot / "src/subject.json"
candidate = json.loads(source.read_text())
folder = output / stage
folder.mkdir(parents=True, exist_ok=True)
with (output / "effects.log").open("ab") as stream:
    stream.write((stage + "\n").encode())
    stream.flush()
    os.fsync(stream.fileno())
mode = candidate.get("mode", "normal")
if mode == "timeout":
    time.sleep(10)
if mode == "overflow":
    sys.stdout.write("x" * 1048577)
if mode == "mutate":
    source.write_text(source.read_text() + " ")
if stage in {"lint", "types"}:
    raise SystemExit(0)
if stage == "build":
    members = {
        "paladin_fixture/subject.json": source.read_bytes(),
        "paladin_fixture-0.0.1.dist-info/METADATA": (
            b"Metadata-Version: 2.1\nName: paladin_fixture\nVersion: 0.0.1\n"
        ),
        "paladin_fixture-0.0.1.dist-info/WHEEL": (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    rows = []
    for name, content in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        rows.append([name, "sha256=" + digest, str(len(content))])
    rows.append(["paladin_fixture-0.0.1.dist-info/RECORD", "", ""])
    record = io.StringIO(newline="")
    csv.writer(record).writerows(rows)
    members[rows[-1][0]] = record.getvalue().encode()
    with zipfile.ZipFile(folder / "fixture.whl", "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    raise SystemExit(0)
passed = candidate["value"] == 7
empty = mode == "no_tests"
skipped = mode == "skip"
root = Element(
    "testsuite",
    tests="0" if empty else "1",
    failures="0" if passed else "1",
    errors="0",
    skipped="1" if skipped else "0",
)
if not empty:
    case = SubElement(root, "testcase", classname="public_oracle", name=stage)
    if mode == "wrong_id":
        case.set("name", "unrelated")
    if skipped:
        SubElement(case, "skipped", message="required case did not execute")
    elif not passed:
        SubElement(case, "failure", message="independent expected value is seven")
if mode == "summary_mismatch":
    root.set("tests", "2")
if mode != "missing":
    (folder / "report.xml").write_bytes(b"not XML" if mode == "malformed" else tostring(root))
if stage == "unit" and mode != "missing_coverage":
    summary = {
        "covered_lines": 1,
        "num_statements": 1,
        "percent_covered": 100.0,
        "missing_lines": 0,
        "excluded_lines": 0,
    }
    coverage = {
        "meta": {"format": 3, "version": "7.13.5", "branch_coverage": False},
        "files": {
            "src/subject.json": {
                "executed_lines": [1],
                "missing_lines": [],
                "excluded_lines": [],
                "summary": summary,
            }
        },
        "totals": summary,
    }
    (folder / "coverage.json").write_text(json.dumps(coverage))
raise SystemExit(0 if passed else 1)
