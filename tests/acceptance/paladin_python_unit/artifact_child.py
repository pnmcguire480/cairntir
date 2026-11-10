"""Produce deliberately inadequate public artifacts after an ordinary child run."""

import base64
import csv
import hashlib
import io
import json
import runpy
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def mutate():
    stage, source, destination = sys.argv[1:]
    mode = json.loads((Path(source) / "src/subject.json").read_text())["mode"]
    output = Path(destination) / stage
    if mode.startswith("coverage_"):
        path = output / "coverage.json"
        value = json.loads(path.read_text())
        entry = value["files"]["src/subject.json"]
        if mode == "coverage_below":
            entry["missing_lines"] = [2]
            for summary in (entry["summary"], value["totals"]):
                summary.update(num_statements=2, missing_lines=1, percent_covered=50.0)
        elif mode == "coverage_missing_source":
            value["files"] = {"src/unrelated.json": entry}
        elif mode == "coverage_zero":
            entry["executed_lines"] = []
            for summary in (entry["summary"], value["totals"]):
                summary.update(covered_lines=0, num_statements=0)
        elif mode == "coverage_nonfinite":
            entry["summary"]["percent_covered"] = float("nan")
        elif mode == "coverage_inconsistent":
            entry["summary"]["covered_lines"] = 0
        elif mode == "coverage_absolute_branch":
            value["meta"]["branch_coverage"] = True
            for summary in (entry["summary"], value["totals"]):
                summary.update(num_branches=2, covered_branches=2, missing_branches=0)
            entry["executed_branches"] = [[1, -1], [1, 2]]
            entry["missing_branches"] = []
            value["files"] = {str(Path(source) / "src/subject.json"): entry}
        else:
            raise ValueError(mode)
        path.write_text(json.dumps(value))
    elif mode.startswith("junit_"):
        path = output / "report.xml"
        root = ElementTree.fromstring(path.read_bytes())  # noqa: S314 - local synthetic fixture XML
        if mode == "junit_duplicate":
            root.append(
                ElementTree.fromstring(ElementTree.tostring(root[0]))  # noqa: S314 - local fixture XML
            )
            root.set("tests", "2")
        elif mode == "junit_contradictory":
            root.set("failures", "1")
        else:
            raise ValueError(mode)
        path.write_bytes(ElementTree.tostring(root))
    elif mode.startswith("wheel_"):
        path = output / "fixture.whl"
        with zipfile.ZipFile(path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        member = "paladin_fixture/subject.json"
        record = "paladin_fixture-0.0.1.dist-info/RECORD"
        if mode == "wheel_wrong_source":
            entries[member] = b'{"value": 99}'
        elif mode == "wheel_traversal":
            entries["../outside.txt"] = b"must never be accepted or extracted"
        elif mode not in {"wheel_bad_record", "wheel_duplicate"}:
            raise ValueError(mode)
        rows = []
        for name, content in entries.items():
            if name == record:
                continue
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            )
            if mode == "wheel_bad_record" and name == member:
                digest = base64.urlsafe_b64encode(b"\x00" * 32).rstrip(b"=").decode()
            rows.append([name, "sha256=" + digest, str(len(content))])
        rows.append([record, "", ""])
        stream = io.StringIO(newline="")
        csv.writer(stream).writerows(rows)
        entries[record] = stream.getvalue().encode()
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
            if mode == "wheel_duplicate":
                archive.writestr(member, entries[member])


try:
    runpy.run_path(str(Path(__file__).with_name("base_stage.py")), run_name="__main__")
except SystemExit:
    mutate()
    raise
