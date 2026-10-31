"""Frozen real Python flow child; run only by the PALADIN managed profile."""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

stage, source_arg, output_arg = sys.argv[1:]
source, output = Path(source_arg), Path(output_arg)
folder = output / stage
folder.mkdir(parents=True, exist_ok=True)
with (output / "effects.log").open("ab") as stream:
    stream.write((stage + "\n").encode())
    stream.flush()
    os.fsync(stream.fileno())
if stage != "integration":
    raise SystemExit(0)

spec = importlib.util.spec_from_file_location("r12_flow", source / "src/flow.py")
if spec is None or spec.loader is None:
    raise RuntimeError("source module unavailable")
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
try:
    label = flow.label(-2)
    label_error = None
except Exception as exc:
    label = None
    label_error = type(exc).__name__
trace = {"input": -2, "normalize": flow.normalize(-2), "compute": flow.compute(-2),
         "label": label, "label_error": label_error}
(folder / "trace.json").write_text(json.dumps(trace, sort_keys=True), encoding="utf-8")

class FlowChecks(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(flow.compute(2), 4)

    def test_negative(self):
        self.assertEqual(flow.compute(-2), 4)

    def test_label(self):
        self.assertEqual(flow.label(-2), "4")

checks = [FlowChecks(name) for name in ("test_positive", "test_negative", "test_label")]
result = unittest.TestResult()
unittest.TestSuite(checks).run(result)
failures = {test.id(): detail for test, detail in result.failures}
errors = {test.id(): detail for test, detail in result.errors}
root = Element("testsuite", tests=str(len(checks)), failures=str(len(failures)),
               errors=str(len(errors)), skipped="0")
for test in checks:
    case = SubElement(root, "testcase", classname="r12_flow.FlowChecks",
                      name=test._testMethodName)
    if test.id() in failures:
        SubElement(case, "failure", message="actual Python assertion failed").text = failures[test.id()]
    if test.id() in errors:
        SubElement(case, "error", message="actual Python execution error").text = errors[test.id()]
(folder / "report.xml").write_bytes(tostring(root, encoding="utf-8"))
raise SystemExit(1 if failures or errors else 0)
