import hashlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

packet = Path(__file__).resolve().parent
worktree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(worktree / "src"))
source = worktree / "src/cairntir/managed_projection.py"
original = source.read_bytes()
frozen = json.loads((packet / "FROZEN.json").read_text())
assert hashlib.sha256(original).hexdigest() == frozen["source_sha256"]
for name, wanted in frozen["files"].items():
    assert hashlib.sha256((packet / name).read_bytes()).hexdigest() == wanted
needle = 'raise ProjectionError("required source evidence is not currently projectable")'
text = original.decode("utf8")
assert text.count(needle) == 1
mutated = text.replace(needle, "pass")
module = types.ModuleType("projection_refusal_bypassed")
exec(compile(mutated, "<public-negative-control>", "exec"), module.__dict__)
spec = importlib.util.spec_from_file_location(
    "projection_supplement_control", packet / "test_projection_supplement.py"
)
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
tests.project_last_session = module.project_last_session
suite = unittest.TestSuite(
    [tests.ProjectionSupplementAcceptance("test_required_source_current_visibility")]
)
with (packet / "wrong-control.log").open("w", encoding="utf8") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
assert result.testsRun == 1 and len(result.failures) == 3 and not result.errors
assert all("complete" in trace and "error" in trace for _, trace in result.failures)
assert source.read_bytes() == original
receipt = {
    "status": "PASS_WRONG_CONTROL_REJECTED",
    "mutation": "Remove only the required-source current-projectability refusal",
    "test_cases": result.testsRun,
    "expected_assertion_failures": len(result.failures),
    "unexpected_errors": len(result.errors),
    "source_sha256": hashlib.sha256(original).hexdigest(),
    "mutated_text_sha256": hashlib.sha256(mutated.encode("utf8")).hexdigest(),
    "test_sha256": hashlib.sha256((packet / "test_projection_supplement.py").read_bytes()).hexdigest(),
    "control_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "log_sha256": hashlib.sha256((packet / "wrong-control.log").read_bytes()).hexdigest(),
    "product_unchanged": True,
}
(packet / "wrong-control.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
print(json.dumps(receipt))
