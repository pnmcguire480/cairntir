from __future__ import annotations

import inspect
import json
import sys

import pytest

from cairntir import obsidian


class Results:
    def __init__(self) -> None:
        self.calls = []

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            self.calls.append(report)


original = inspect.getsource(obsidian._upsert_generated)
target = '        raise ProjectionError(f"could not read projection {path}: {exc}") from exc'
assert original.count(target) == 1, "expected read-error handler must exist"
obsidian._read_fault_mutation_hits = 0
mutant = original.replace(
    target,
    '        globals()["_read_fault_mutation_hits"] += 1\n        return',
)
exec(compile(mutant, "<swallowed-projection-read-failure>", "exec"), obsidian.__dict__)
results = Results()
exit_code = pytest.main(
    [
        sys.argv[1]
        + "::test_projection_filesystem_failure_preserves_user_notes_and_allows_retry[read]",
        "-q",
        "--no-cov",
        "-p",
        "no:cacheprovider",
    ],
    plugins=[results],
)
assert exit_code == 1, "mutant must fail its intended test"
assert obsidian._read_fault_mutation_hits == 1, "the injected read failure must reach the mutant"
assert len(results.calls) == 1 and results.calls[0].failed
failure = str(results.calls[0].longrepr)
assert "DID NOT RAISE" in failure and "ProjectionError" in failure, failure
print(
    json.dumps(
        {
            "result": "PASS",
            "wrong_control": "swallowed projection read failure",
            "mutation_reached": obsidian._read_fault_mutation_hits,
            "detected_by": "expected ProjectionError was not raised",
            "production_file_changed": False,
        }
    )
)
