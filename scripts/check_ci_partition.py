"""Prove the pull-request test partition dropped no test.

Pull requests run the suite as parallel parts (the core set plus the
acceptance parts) instead of one long job. This gate collects the complete
``not slow`` suite, reads the JUnit report each part retained, and fails
unless the parts ran exactly the collected tests: none missing, none twice.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

_COLLECTED = re.compile(r"^(\d+)(?:/\d+)? tests? collected")


def collected_count() -> int:
    """Return how many tests the complete ``not slow`` suite selects."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            "not slow",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"FAIL: collection exited {result.returncode}\n{result.stdout}")
    lines = result.stdout.splitlines()
    ids = {line.strip() for line in lines if "::" in line}
    summary = next((m for line in lines if (m := _COLLECTED.match(line))), None)
    if summary is None or int(summary.group(1)) != len(ids):
        raise SystemExit("FAIL: could not reconcile the collection summary with its ids")
    return len(ids)


def report_cases(paths: list[Path]) -> Counter[tuple[str, str]]:
    """Count each (classname, name) case across the retained JUnit reports."""
    cases: Counter[tuple[str, str]] = Counter()
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):  # noqa: S314 - own CI output
            cases[(case.get("classname", ""), case.get("name", ""))] += 1
    return cases


def main() -> int:
    """Compare the parts with the complete collection and report the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="JUnit XML from every part")
    args = parser.parse_args()

    expected = collected_count()
    cases = report_cases(args.reports)
    ran = sum(cases.values())
    repeated = sorted(key for key, count in cases.items() if count > 1)

    if repeated:
        print(f"FAIL: {len(repeated)} tests ran in more than one part, e.g. {repeated[:5]}")
        return 1
    if ran != expected:
        print(f"FAIL: the parts ran {ran} tests; the complete suite selects {expected}")
        return 1
    print(f"OK: {len(args.reports)} parts ran all {ran} selected tests exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
