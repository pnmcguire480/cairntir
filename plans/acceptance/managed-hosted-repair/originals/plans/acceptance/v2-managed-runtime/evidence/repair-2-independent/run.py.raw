from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

OUT = Path(__file__).resolve().parent
PACKET = OUT.parent
ROOT = Path("C:/Users/pnmcg/.codex/worktrees/v2-foundation/Cairntir")
EXPECTED = {
    "managed.py": "301eefc5c2593f3fa466c06d84b0384dfd92294aee2e015ac68b967d82585f30",
    "cli.py": "c9ec4aec3811495803b5813d3812ba3a70f007ce968614bc2614ae154cc94448",
    "memory/store.py": "490d2e3df639556d3aff5f555c08f04568808219a34f66af2a7174ec288c6f70",
    "access.py": "084a03f9963d45aba34feb17227a8923d124c867c89017be22a2374251171c6c",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


receipt = {"schema": "cairntir.managed-repair2-independent-review.v1", "status": "FAIL", "started_at": datetime.now(timezone.utc).isoformat(), "product_sha256": EXPECTED, "calls": []}
assert not (OUT / "review.json").exists()
environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
               "PYTHONDONTWRITEBYTECODE": "1", "CAIRNTIR_HOME": str(OUT / "home"),
               "CAIRNTIR_DISABLE_AUTOREGISTER": "1", "CAIRNTIR_DISABLE_UPDATE_CHECK": "1", "HF_HUB_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1", "MANAGED_ACCEPTANCE_MODEL_CACHE": "C:/Dev/Cairntir/.cairntir/foundation-embedding-prerequisite/cache"}
environment.pop("CAIRNTIR_GRANT_FILE", None)
environment.pop("CAIRNTIR_ENABLE_EMBEDDER_WARMUP", None)


def execute(name, command, env):
    value = subprocess.run(command, cwd=OUT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=240)
    log = OUT / (name + ".log")
    log.write_text(value.stdout + value.stderr, encoding="utf-8")
    receipt["calls"].append({"name": name, "command": command, "exit_code": value.returncode, "log_sha256": sha(log)})
    assert value.returncode == 0, value.stdout + value.stderr
    return value.stdout + value.stderr


try:
    for name, wanted in EXPECTED.items():
        assert sha(ROOT / "src/cairntir" / name) == wanted, name
    before = (PACKET / "repair-2/managed-before.py").read_text(encoding="utf-8")
    after = (ROOT / "src/cairntir/managed.py").read_text(encoding="utf-8")
    assert sha(PACKET / "repair-2/managed-before.py") == "f712fcee2f6fbbc47ca46a975a29b8582959803aa68ff063d26491e1914cefc2"
    removed = '            "unclean_sessions": self._unclean_sessions(),\n'
    replaced = '"unclean_sessions": state["unclean_sessions"],'
    assert before.count(removed) == 1 and before.count(replaced) == 2
    assert before.replace(removed, "", 1).replace(replaced, '"unclean_sessions": self._unclean_sessions(),') == after
    (OUT / "source.diff").write_text("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="repair1/managed.py", tofile="repair2/managed.py")), encoding="utf-8")
    receipt["source_review"] = "Exactly one readiness-state field removed; brief/close read that authorized telemetry directly. Task/evidence/pending capture/config/action state and full brief hash/budget remain unchanged."
    receipt["original_freezes"] = {}
    for name in ["CORE-FROZEN.json", "PROCESS-FROZEN.json", "CLOSE-FROZEN.json", "CONFIG-FROZEN.json", "STATE-FROZEN.json"]:
        manifest = json.loads((PACKET / name).read_bytes())
        for file, wanted in {**manifest["files"], **manifest.get("fixture_dependency", {})}.items():
            assert sha(PACKET / file) == wanted, file
        receipt["original_freezes"][name] = sha(PACKET / name)
    assert receipt["original_freezes"]["STATE-FROZEN.json"] == "2f189ab7208a20bebfa884502ed2a28c83db15e973eccda708b849f41cd3981b"
    for name, count in [("core", 12), ("process", 10), ("close", 4), ("config", 1), ("state", 1)]:
        output = execute(name, [sys.executable, "-B", "-X", "utf8", str(PACKET / ("test_managed_" + name + ".py"))], environment)
        assert f"Ran {count} test" in output and "\nOK" in output and "skipped=" not in output
    mutant = OUT / "wrong-control"
    shutil.copytree(ROOT / "src", mutant / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    path = mutant / "src/cairntir/managed.py"
    token = "        if execution.replayed:\n            return self._action_status(intent, replayed=True)"
    assert after.count(token) == 1
    mutation = after.replace(token, "        if execution.replayed:\n            self._run(profile)\n            return self._action_status(intent, replayed=True)")
    path.write_text(mutation, encoding="utf-8")
    output = execute("replay-wrong-control", [sys.executable, "-B", "-X", "utf8", str(PACKET / "run_replay_wrong_control.py"), str(OUT / "wrong-control-result.json")], {**environment, "PYTHONPATH": str(mutant / "src")})
    wrong = json.loads((OUT / "wrong-control-result.json").read_bytes())
    assert wrong["meaningful_detection"] and wrong["failures"] == 1 and wrong["errors"] == 0
    assert len(wrong["external_markers"]) == 1 and len(wrong["external_markers"][0]) == 2
    receipt["wrong_control"] = {"status": "REJECTED", "mutant_sha256": sha(path), "external_markers": 2, "assertion_failures": 1,
                                "harness_errors": 0, "result_sha256": sha(OUT / "wrong-control-result.json")}
    for name, wanted in EXPECTED.items():
        assert sha(ROOT / "src/cairntir" / name) == wanted, name
    for name, wanted in receipt["original_freezes"].items():
        assert sha(PACKET / name) == wanted
        for file, digest in json.loads((PACKET / name).read_bytes())["files"].items():
            assert sha(PACKET / file) == digest
    receipt.update(status="PASS", original_cases=27, state_regression_cases=1, state_ack_subtests=2,
                   candidate_cases=28, skips=0, source_unchanged=True, original_frozen_assertions_unchanged=True,
                   product_edits_by_reviewer=False, source_diff_sha256=sha(OUT / "source.diff"))
except BaseException:
    receipt["error"] = traceback.format_exc()
finally:
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    (OUT / "review.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": receipt["status"], "receipt": str(OUT / "review.json"), "sha256": sha(OUT / "review.json"), "error": receipt.get("error")}))
raise SystemExit(0 if receipt["status"] == "PASS" else 1)
