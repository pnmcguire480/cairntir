"""Independent finite acceptance for invocation paths and executable identity."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import venv
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.managed import ManagedRuntime, ManagedRuntimeError, _configuration
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class ManagedEnvironmentAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="managed-environment-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def config(self, argv):
        return {
            "schema": "cairntir.managed-config.v1",
            "wing": "environment",
            "room": "synthetic",
            "project_root": str(self.root),
            "brief_budget_chars": 16384,
            "profiles": {"check": {
                "argv": argv,
                "cwd": str(self.root),
                "timeout_seconds": 10,
                "output_limit_bytes": 8192,
            }},
        }

    def alias_fixture(self):
        alias = self.root / "configured-interpreter.bin"
        targets = [self.root / "target-a.bin", self.root / "target-b.bin"]
        for path in [alias, *targets]:
            path.write_bytes(b"inert identical executable bytes; never execute\n")
        selection = [targets[0]]
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == alias:
                return selection[0]
            return original_resolve(path, *args, **kwargs)

        return alias, targets, selection, patch.object(Path, "resolve", resolve)

    def ready(self, store, config):
        session = str(uuid4())
        runtime = ManagedRuntime(store, config=config)
        runtime.start(session)
        event = runtime.capture({
            "schema": "cairntir.managed-event.v1",
            "event_id": str(uuid4()), "session_id": session, "sequence": 1,
            "task_id": None, "expected_revision": 0,
            "content": "Run only the explicitly configured interpreter environment.",
        })
        brief = runtime.brief()
        ack = runtime.acknowledge({
            "schema": "cairntir.managed-ack.v1",
            "brief_id": brief["brief_id"], "brief_sha256": brief["brief_sha256"],
        })
        action = {
            "schema": "cairntir.managed-action.v1", "action_id": str(uuid4()),
            "ack_id": ack["ack_id"], "profile": "check",
            "claim": "The configured interpreter retains its own module environment.",
            "predicted_outcome": "The synthetic environment witness succeeds.",
            "event_ids": [event["event_id"]],
        }
        return runtime, action

    def test_exact_invocation_and_input_preserved_but_canonical_target_is_bound(self):
        alias, targets, selection, resolver = self.alias_fixture()
        config = self.config([str(alias), "-c", "print('exact argument tail')", "space arg"])
        original = deepcopy(config)
        with resolver:
            first = _configuration(config)
            selection[0] = targets[1]
            second = _configuration(config)
        self.assertEqual(config, original, "normalization mutated operator input")
        for normalized in (first, second):
            profile = normalized["profiles"]["check"]
            self.assertEqual(profile["argv"], original["profiles"]["check"]["argv"])
            self.assertEqual(profile["executable_sha256"], hashlib.sha256(alias.read_bytes()).hexdigest())
        self.assertNotEqual(canonical(first), canonical(second), "same-byte target retargeting lost its identity binding")

    def test_same_byte_target_retarget_after_ack_refuses_dispatch_without_writes(self):
        alias, targets, selection, resolver = self.alias_fixture()
        config = self.config([str(alias), "-c", "never execute this inert file"])
        original = deepcopy(config)
        with DrawerStore(self.root / "guard.db", HashEmbeddingProvider(32)) as store, resolver:
            runtime, action = self.ready(store, config)
            before = list(store._conn.iterdump())
            selection[0] = targets[1]
            with patch("subprocess.Popen", side_effect=AssertionError("forbidden dispatch")) as spawn:
                with self.assertRaises(ManagedRuntimeError):
                    runtime.dispatch(action)
                spawn.assert_not_called()
            self.assertEqual(list(store._conn.iterdump()), before)
        self.assertEqual(config, original)

    @unittest.skipUnless(os.name == "posix", "actual symlinked venv proof is a required POSIX hosted gate")
    def test_posix_managed_child_retains_venv_prefix_and_private_module(self):
        environment = self.root / "synthetic-venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
        interpreter = environment / "bin" / "python"
        self.assertTrue(interpreter.is_symlink(), "the hosted control must exercise an actual interpreter symlink")
        self.assertNotEqual(interpreter, interpreter.resolve())
        site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        site.mkdir(parents=True, exist_ok=True)
        module_name = "managed_environment_witness_" + uuid4().hex
        module_path = site / (module_name + ".py")
        token = "private-environment-" + uuid4().hex
        module_path.write_text("VALUE = " + repr(token) + "\n", encoding="utf-8")
        code = (
            "import json, sys, importlib; m=importlib.import_module(" + repr(module_name) + "); "
            "print(json.dumps({'prefix':sys.prefix,'origin':m.__file__,'value':m.VALUE}))"
        )
        argv = [str(interpreter), "-I", "-c", code]
        clean_env = {key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"}}
        # Direct success proves the synthetic venv/module fixture is usable.
        direct = subprocess.run(argv, capture_output=True, text=True, timeout=10, env=clean_env, check=True)
        expected = json.loads(direct.stdout)
        self.assertEqual(Path(expected["prefix"]).resolve(), environment.resolve())
        self.assertEqual(Path(expected["origin"]).resolve(), module_path.resolve())
        self.assertEqual(expected["value"], token)
        # Negative control proves canonical-target invocation loses this private module.
        wrong = subprocess.run([str(interpreter.resolve()), *argv[1:]], capture_output=True, text=True, timeout=10, env=clean_env)
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn(module_name, wrong.stderr)
        with patch.dict(os.environ, clean_env, clear=True), DrawerStore(self.root / "environment.db", HashEmbeddingProvider(32)) as store:
            runtime, action = self.ready(store, self.config(argv))
            result = runtime.dispatch(action)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(json.loads(result["stdout"]), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
