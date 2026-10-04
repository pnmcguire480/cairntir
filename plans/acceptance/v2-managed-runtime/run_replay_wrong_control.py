"""Run an unchanged frozen crash case and retain its independent external markers."""

import json
import sys
import unittest
from pathlib import Path

from test_managed_process import ManagedProcessAcceptance


def main():
    captured = []
    original = ManagedProcessAcceptance.cleanup_processes

    def cleanup(case):
        captured.append(case.markers())
        return original(case)

    ManagedProcessAcceptance.cleanup_processes = cleanup
    suite = unittest.TestSuite(
        [ManagedProcessAcceptance("test_kill_after_external_effect_preserves_prediction_and_never_relaunches")]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "external_markers": captured,
        "meaningful_detection": len(result.failures) == 1 and not result.errors and len(captured[0]) == 2,
    }
    Path(sys.argv[1]).write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert receipt["meaningful_detection"], receipt


if __name__ == "__main__":
    main()
