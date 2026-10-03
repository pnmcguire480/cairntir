"""Finite independently owned fixture routing and negative controls."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKET = Path(__file__).resolve().parent
CANDIDATE = Path(r"C:\Users\pnmcg\AppData\Local\Temp\cairntir-managed-work-20261003")
PUBLIC = CANDIDATE / "plans/acceptance/managed-session-port"
PYTHON = sys.executable


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    path = PACKET / name
    if path.exists():
        raise RuntimeError(f"append-only output already exists: {path}")
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def environment(label):
    root = PACKET / "runtime-final" / label
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(CANDIDATE / "src"),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        CAIRNTIR_HOME=str(root / "home"),
        CAIRNTIR_DISABLE_AUTOREGISTER="1",
        CAIRNTIR_DISABLE_UPDATE_CHECK="1",
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        XDG_CACHE_HOME=str(root / "cache"),
        HF_HOME=str(root / "hf"),
        TEMP=str(root),
        TMP=str(root),
    )
    return env


def run(label, arguments, env, expected):
    result = subprocess.run(arguments, cwd=CANDIDATE, env=env, capture_output=True, timeout=60)
    log = PACKET / (label + ".log")
    if log.exists():
        raise RuntimeError("existing log")
    log.write_bytes(result.stdout + result.stderr)
    write(label + "-execution.json", {"argv": arguments, "exit_code": result.returncode,
          "expected_exit": expected, "stdout_stderr_sha256": sha(log)})
    print(result.stdout.decode("utf-8", errors="replace"))
    print(result.stderr.decode("utf-8", errors="replace"))
    if result.returncode != expected:
        raise RuntimeError(f"unexpected control outcome {result.returncode}, expected {expected}")


def pytest_args():
    return [PYTHON, "-m", "pytest", "-c", str(CANDIDATE / "pyproject.toml"),
            "--rootdir", str(CANDIDATE), "--confcutdir", str(PUBLIC),
            "--override-ini", "addopts=", "-p", "no:cacheprovider"]


def router():
    source = (PACKET / "test_managed_port_acceptance_v3.py").read_text(encoding="utf-8")
    before = '_CONTROLS = _load('
    addition = ('_verify(\n    _PACKET / "visibility-v2",\n'
                '    "5334505390aa967d2e2f02e0825fe2bc51effd9cd5c2cc0bd37582847b37e330",\n)\n')
    assert source.count(before) == 1
    source = source.replace(before, addition + before)
    source = source.replace('visibility-v1/test_hidden_event.py', 'visibility-v2/test_hidden_event_v2.py')
    out = PACKET / "test_managed_port_acceptance_v4.py"
    assert not out.exists()
    out.write_text(source, encoding="utf-8", newline="\n")
    result = subprocess.run([PYTHON, "-m", "ruff", "format", "--config", str(CANDIDATE / "pyproject.toml"), str(out)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    old = CANDIDATE / "tests/unit/test_managed_port_acceptance.py"
    history = PUBLIC / "router-history/v3/test_managed_port_acceptance.py"
    history.parent.mkdir(parents=True, exist_ok=True)
    assert not history.exists()
    shutil.copyfile(old, history)
    assert sha(history) == "f28672def5ba4c3c773c5309eb4ccd05c3a175ce65b4c778bc664489ea2cc796"
    for file in (PACKET / "visibility-v2").iterdir():
        if file.is_file():
            destination = PUBLIC / "visibility-v2" / file.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            assert not destination.exists()
            shutil.copyfile(file, destination)
    shutil.copyfile(out, old)
    receipt = {"version": 4, "maintained_router_sha256": sha(out),
               "prior_router_sha256": sha(history), "visibility_freeze_sha256": sha(PACKET / "visibility-v2/FREEZE.json")}
    write("ROUTER-v4-FROZEN.json", receipt)
    shutil.copyfile(out, PUBLIC / out.name)
    shutil.copyfile(PACKET / "ROUTER-v4-FROZEN.json", PUBLIC / "ROUTER-v4-FROZEN.json")
    run("router-v4-format", [PYTHON, "-m", "ruff", "format", "--check", "--config", str(CANDIDATE / "pyproject.toml"), str(old)], environment("format"), 0)
    run("router-v4-lint", [PYTHON, "-m", "ruff", "check", "--config", str(CANDIDATE / "pyproject.toml"), str(old)], environment("lint"), 0)
    run("router-v4-final25", pytest_args() + [str(old), "--junitxml", str(PACKET / "router-v4-final25.xml")], environment("router25"), 0)


def guard():
    env = environment("guard")
    env["PYTHONPATH"] = str(PACKET) + os.pathsep + str(CANDIDATE / "src")
    write("ambient-guard-control-FROZEN.json", {"source_binding": json.loads((PACKET / "candidate-repair2-source.json").read_text()),
          "plugin_sha256": sha(PACKET / "bypass_guard_control.py"),
          "router_sha256": sha(CANDIDATE / "tests/unit/test_managed_port_acceptance.py"),
          "mutation": "Mask transaction_active only while invoking product operation; all assertions unchanged"})
    run("ambient-guard-wrong-control", pytest_args() + ["-p", "bypass_guard_control", str(CANDIDATE / "tests/unit/test_managed_port_acceptance.py"),
        "-k", "test_caller_transaction_cannot_issue_managed_durable_receipts and explicit and capture and owner",
        "--junitxml", str(PACKET / "ambient-guard-wrong-control.xml")], env, 1)


def oracle():
    script = CANDIDATE / "plans/acceptance/v2-managed-runtime/oracle_controls.py"
    write("oracle-control-FROZEN.json", {"runner_sha256": sha(script), "source_imported": False,
          "assertions": "Original child denies invisible uncommitted prediction and accepts committed prediction"})
    run("pre-action-oracle-controls", [PYTHON, str(script)], environment("oracle"), 0)


def replay():
    mutation = PACKET.parent / "controls/replay-mutated/src/cairntir"
    assert not mutation.exists()
    shutil.copytree(CANDIDATE / "src/cairntir", mutation, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    file = mutation / "managed.py"
    raw = file.read_bytes()
    text = raw.decode("utf-8")
    guard = "        if execution.replayed:\n            return self._action_status(intent, replayed=True)\n"
    normalized = text.replace("\r\n", "\n")
    assert normalized.count(guard) == 1
    file.write_text(normalized.replace(guard, ""), encoding="utf-8", newline="\n")
    historical = CANDIDATE / "plans/acceptance/v2-managed-runtime"
    script = historical / "run_replay_wrong_control.py"
    write("replay-control-FROZEN.json", {"original_managed_sha256": hashlib.sha256(raw).hexdigest(),
          "mutated_managed_sha256": sha(file), "mutation": guard, "candidate_source_edited": False,
          "unchanged_harness_sha256": {name: sha(historical / name) for name in ["run_replay_wrong_control.py", "test_managed_process.py", "process_driver.py", "process_child.py"]}})
    env = environment("replay")
    env["PYTHONPATH"] = str(mutation.parent)
    run("replay-wrong-control", [PYTHON, str(script), str(PACKET / "replay-wrong-control-result.json")], env, 0)


if __name__ == "__main__":
    {"router": router, "guard": guard, "oracle": oracle, "replay": replay}[sys.argv[1]]()
