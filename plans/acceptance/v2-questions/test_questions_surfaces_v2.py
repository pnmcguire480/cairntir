"""Public R08 file, CLI and durable handoff acceptance, frozen before implementation."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.questions import open_question, resolve_question
from typer.testing import CliRunner

from cairntir import obsidian_bridge
from cairntir.cli import app
from cairntir.handoff import _open_questions, compose
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class QuestionSurfacesAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.database = self.home / "cairntir.db"
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.addCleanup(lambda: self.store.close())
        self.vault = Path(self.temp.name) / "vault"
        self.vault.mkdir()
        (self.vault / ".obsidian").mkdir()
        self.outbox = self.vault / "cairntir-sync/outbox"
        self.outbox.mkdir(parents=True)
        support = self.store.add(
            Drawer(wing="questions", room="work", content="Recorded supporting measurement.")
        )
        self.reference = {
            "drawer_id": support.id,
            "source_identity": self.store.portable_identity(support.id),
            "content_sha256": sha(support.content),
        }

    def request(self):
        return {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "room": "work",
            "content": "  Which setting produced this measurement? café\n",
            "owner": "Patrick",
            "evidence": [self.reference],
        }

    def resolution(self, receipt):
        return {
            "schema": "cairntir.question-resolve.v1",
            "request_id": str(uuid4()),
            "wing": "questions",
            "question_id": receipt["question_id"],
            "question_drawer_id": receipt["question_drawer_id"],
            "question_sha256": receipt["question_sha256"],
            "content": "  Explicit declared resolution.\n",
            "evidence": [self.reference],
        }

    def queue(self, request):
        path = self.outbox / (request["request_id"] + ".json")
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        return path

    def sync(self):
        return obsidian_bridge.sync_workspace(self.store, vault=self.vault, wing="questions")

    def result(self, report, request):
        relative = f"cairntir-sync/outbox/{request['request_id']}.json"
        matches = [entry for entry in report["results"] if entry["file"] == relative]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def register(self):
        value = json.loads(
            (self.vault / "cairntir-sync/questions.json").read_text(encoding="utf-8")
        )
        self.assertEqual(value["schema"], "cairntir.question-register.v1")
        self.assertEqual(value["wing"], "questions")
        return {entry["question_id"]: entry for entry in value["questions"]}

    def test_outbox_roundtrip_keeps_requests_and_projects_linked_question_history(self):
        request = self.request()
        queued = self.queue(request)
        original = queued.read_bytes()
        result = self.result(self.sync(), request)
        self.assertEqual(result["status"], "committed")
        self.assertIs(result["receipt_written"], True)
        receipt = result["receipt"]
        self.assertEqual(self.register()[receipt["question_id"]]["status"], "open")
        resolve = self.resolution(receipt)
        self.queue(resolve)
        report = self.sync()
        resolved = self.result(report, resolve)["receipt"]
        self.assertEqual(report["projection"]["status"], "complete")
        entry = self.register()[receipt["question_id"]]
        self.assertEqual(entry["status"], "resolved")
        self.assertEqual(entry["content"], request["content"])
        self.assertEqual(entry["resolution"]["content"], resolve["content"])
        markdown = (self.vault / "cairntir-sync/questions.md").read_text(encoding="utf-8")
        self.assertIn(receipt["question_id"], markdown)
        self.assertIn("Patrick", markdown)
        for identity in (
            receipt["question_drawer_id"],
            self.reference["drawer_id"],
            resolved["resolution_drawer_id"],
        ):
            self.assertIn(f"[[cairntir-sync/memory/drawer-{identity}", markdown)
            self.assertTrue((self.vault / f"cairntir-sync/memory/drawer-{identity}.md").exists())
        self.assertEqual(queued.read_bytes(), original)
        self.assertTrue((self.outbox / f"{resolve['request_id']}.json").exists())

    def test_acknowledgement_failure_is_committed_and_restart_retry_repairs_it(self):
        request = self.request()
        self.queue(request)
        write = obsidian_bridge._write_json

        def fail_ack(vault, path, value):
            if "acknowledgements" in path.parts:
                raise OSError("injected acknowledgement failure")
            return write(vault, path, value)

        with patch.object(obsidian_bridge, "_write_json", side_effect=fail_ack):
            result = self.result(self.sync(), request)
        self.assertEqual(result["status"], "committed")
        self.assertIs(result["receipt_written"], False)
        self.assertIn("error", result)
        receipt = result["receipt"]
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        replay = self.result(self.sync(), request)
        self.assertEqual(replay["receipt"], {**receipt, "replayed": True})
        self.assertIs(replay["receipt_written"], True)
        ack = self.vault / f"cairntir-sync/acknowledgements/{request['request_id']}.json"
        self.assertEqual(json.loads(ack.read_text(encoding="utf-8")), replay["receipt"])
        self.assertEqual(self.store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0], 2)

    def test_rejected_file_does_not_block_valid_request_or_ingest_user_notes(self):
        request = self.request()
        self.queue(request)
        (self.outbox / "malformed.json").write_text("not JSON", encoding="utf-8")
        (self.vault / "My notes.md").write_text(
            "Never ingest this private notebook automatically.", encoding="utf-8"
        )
        report = self.sync()
        self.assertEqual(self.result(report, request)["status"], "committed")
        self.assertTrue(any(entry["status"] == "rejected" for entry in report["results"]))
        self.assertEqual(self.store._conn.execute("SELECT COUNT(*) FROM drawers").fetchone()[0], 2)

    def test_register_preserves_human_bytes_and_rejects_unmarked_target(self):
        request = self.request()
        self.queue(request)
        self.sync()
        path = self.vault / "cairntir-sync/questions.md"
        suffix = b"\r\nHuman annotation.\nKeep mixed endings.\r\n"
        path.write_bytes(path.read_bytes() + suffix)
        second = self.request()
        second["content"] = "A second question."
        self.queue(second)
        self.assertEqual(self.sync()["projection"]["status"], "complete")
        self.assertTrue(path.read_bytes().endswith(suffix))
        original = b"User-owned register without generated markers.\r\n"
        path.write_bytes(original)
        self.assertEqual(self.sync()["projection"]["status"], "error")
        self.assertEqual(path.read_bytes(), original)

    def test_handoff_keeps_typed_question_until_durable_resolution_but_legacy_behavior_stays(self):
        receipt = open_question(self.store, self.request(), wing="questions")
        self.store.add(
            Drawer(
                wing="questions",
                room="work",
                content="Ordinary superseder",
                supersedes_id=receipt["question_drawer_id"],
            )
        )

        def question_ids():
            brief = compose(self.store, wing="questions", budget_chars=20000)
            return {
                drawer.id
                for section in brief.sections
                if section.key == "open_questions"
                for drawer in section.included
            }

        self.assertIn(receipt["question_drawer_id"], question_ids())
        resolve_question(self.store, self.resolution(receipt), wing="questions")
        self.store.close()
        self.store = DrawerStore(self.database, HashEmbeddingProvider(32))
        self.assertNotIn(receipt["question_drawer_id"], question_ids())
        old = Drawer(
            id=101, wing="legacy", room="work", content="Old", metadata={"open_question": True}
        )
        new = Drawer(
            id=102, wing="legacy", room="work", content="Historical superseder", supersedes_id=101
        )
        self.assertEqual(_open_questions([old, new]), [])

    def test_cli_json_resolution_errors_duplicate_keys_and_callback_purity(self):
        request = self.request()
        path = Path(self.temp.name) / "request.json"
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        with (
            patch.dict(os.environ, {"CAIRNTIR_HOME": str(self.home)}),
            patch(
                "cairntir.cli.production_embedding_provider", return_value=HashEmbeddingProvider(32)
            ),
            patch("cairntir.cli.ensure_registered") as registration,
            patch("cairntir.cli.maybe_check_in_background") as update,
            patch(
                "cairntir.cli.pending_update_banner", return_value="Unrelated update notice"
            ) as banner,
        ):
            runner = CliRunner()
            opened = runner.invoke(app, ["question", "open", str(path), "--wing", "questions"])
            self.assertEqual(opened.exit_code, 0, opened.output)
            receipt = json.loads(opened.stdout)
            self.assertEqual(receipt["schema"], "cairntir.question-receipt.v1")
            listed = runner.invoke(app, ["question", "list", "--wing", "questions"])
            self.assertEqual(listed.exit_code, 0, listed.output)
            self.assertEqual(len(json.loads(listed.stdout)["questions"]), 1)
            path.write_text(json.dumps(self.resolution(receipt)), encoding="utf-8")
            resolved = runner.invoke(app, ["question", "resolve", str(path), "--wing", "questions"])
            self.assertEqual(resolved.exit_code, 0, resolved.output)
            self.assertEqual(json.loads(resolved.stdout)["operation"], "resolve")
            stale = runner.invoke(app, ["question", "resolve", str(path), "--wing", "foreign"])
            self.assertNotEqual(stale.exit_code, 0)
            self.assertTrue(stale.output.strip())
            path.write_text(
                '{"schema":"cairntir.question-open.v1","schema":"other"}', encoding="utf-8"
            )
            malformed = runner.invoke(app, ["question", "open", str(path), "--wing", "questions"])
            self.assertNotEqual(malformed.exit_code, 0)
            self.assertIn("duplicate", malformed.output.lower())
            registration.assert_not_called()
            update.assert_not_called()
            banner.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
