"""Public file protocol acceptance frozen before file-flow implementation."""

import hashlib
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import Sensitivity, WriteProvenance


class WorkspaceAcceptance(unittest.TestCase):
    def setUp(self):
        self.bridge = importlib.import_module("cairntir.obsidian_bridge")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.home / "cairntir.db"
        self.store = self.open_store()
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.sync_root = self.vault / "cairntir-sync"
        self.outbox = self.sync_root / "outbox"
        self.outbox.mkdir(parents=True)

    def open_store(self):
        store = DrawerStore(self.db, HashEmbeddingProvider(dimension=16))
        self.addCleanup(store.close)
        return store

    def source(self, **changes):
        values = dict(wing="cairntir", room="notes", content="Original exact content.\r\n")
        values.update(changes)
        return self.store.add(Drawer(**values))

    def request(self, source, content="  Corrected café.\r\n"):
        return {
            "schema": "cairntir.obsidian-correction.v1",
            "request_id": str(uuid4()),
            "wing": source.wing,
            "source_drawer_id": source.id,
            "source_identity": self.store.portable_identity(source.id),
            "source_sha256": hashlib.sha256(source.content.encode()).hexdigest(),
            "content": content,
        }

    def submit(self, request, name=None):
        path = self.outbox / (name or f"{request['request_id']}.json")
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        return path

    def sync(self, wing="cairntir"):
        return self.bridge.sync_workspace(self.store, vault=self.vault, wing=wing)

    def manifest(self):
        return json.loads((self.sync_root / "workspace.json").read_text(encoding="utf-8"))

    def result_for(self, report, path):
        return next(
            item
            for item in report["results"]
            if item["file"] == path.relative_to(self.vault).as_posix()
        )

    def test_inventory_is_exact_scoped_and_excludes_secret(self):
        source = self.source()
        foreign = self.source(wing="foreign-wing", content="Foreign private text")
        secret = self.store.add(
            Drawer(wing="cairntir", room="private", content="Secret payload"),
            provenance=WriteProvenance.create(
                host="fixture", capture_path="fixture", sensitivity=Sensitivity.SECRET
            ),
        )
        structured = self.source(
            metadata={"task_checkpoint": {"task_id": str(uuid4()), "revision": 1}}
        )
        report = self.sync()
        self.assertEqual(report["schema"], "cairntir.obsidian-sync.v1")
        self.assertEqual(report["wing"], "cairntir")
        self.assertEqual(report["projection"]["status"], "complete")
        data = self.manifest()
        self.assertEqual(data["schema"], "cairntir.obsidian-workspace.v1")
        self.assertEqual(data["wing"], "cairntir")
        entries = {row["drawer_id"]: row for row in data["drawers"]}
        self.assertNotIn(foreign.id, entries)
        self.assertNotIn(secret.id, entries)
        row = entries[source.id]
        self.assertEqual(row["source_identity"], self.store.portable_identity(source.id))
        self.assertEqual(row["content_sha256"], hashlib.sha256(source.content.encode()).hexdigest())
        self.assertEqual(row["content"], source.content)
        self.assertEqual(
            (row["wing"], row["room"], row["layer"]), (source.wing, source.room, source.layer.value)
        )
        self.assertIs(row["current"], True)
        self.assertIs(row["editable"], True)
        self.assertIsNone(row["supersedes_id"])
        self.assertIs(entries[structured.id]["editable"], False)
        self.assertEqual(row["note"], f"cairntir-sync/memory/drawer-{source.id}.md")
        self.assertTrue((self.vault / row["note"]).is_file())
        self.assertTrue((self.sync_root / "index.md").is_file())

    def test_apply_reopen_retry_receipt_and_bidirectional_history(self):
        source = self.source()
        request = self.request(source)
        path = self.submit(request)
        original_bytes = path.read_bytes()
        first = self.result_for(self.sync(), path)
        self.assertEqual(first["status"], "committed")
        self.assertIs(first["receipt_written"], True)
        receipt = first["receipt"]
        ack = self.sync_root / "acknowledgements" / f"{request['request_id']}.json"
        self.assertEqual(
            json.loads(ack.read_text())["correction_drawer_id"], receipt["correction_drawer_id"]
        )
        self.assertEqual(path.read_bytes(), original_bytes)
        self.store.close()
        self.store = self.open_store()
        retry = self.result_for(self.sync(), path)
        self.assertIs(retry["receipt"]["replayed"], True)
        self.assertEqual(retry["receipt"]["correction_drawer_id"], receipt["correction_drawer_id"])
        self.assertEqual(len(self.store.list_by(limit=None)), 2)
        rows = {row["drawer_id"]: row for row in self.manifest()["drawers"]}
        old, new = rows[source.id], rows[receipt["correction_drawer_id"]]
        self.assertIs(old["current"], False)
        self.assertIs(old["editable"], False)
        self.assertIs(new["current"], True)
        self.assertEqual(new["supersedes_id"], source.id)
        self.assertEqual(new["content"], request["content"])
        self.assertIn(f"drawer-{new['drawer_id']}", (self.vault / old["note"]).read_text())
        self.assertIn(f"drawer-{old['drawer_id']}", (self.vault / new["note"]).read_text())
        self.assertIn("[[", (self.vault / new["note"]).read_text())

    def test_bad_json_and_duplicate_keys_do_not_block_valid_requests(self):
        source = self.source()
        valid = self.submit(self.request(source))
        malformed = self.outbox / "malformed.json"
        malformed.write_text("{broken")
        duplicate = self.outbox / "duplicate.json"
        duplicate.write_text('{"schema":"x","schema":"cairntir.obsidian-correction.v1"}')
        ordinary = self.vault / "My Notes.md"
        ordinary.write_text("A human note must never be silently imported")
        report = self.sync()
        self.assertEqual(self.result_for(report, valid)["status"], "committed")
        for path in (malformed, duplicate):
            row = self.result_for(report, path)
            self.assertEqual(row["status"], "rejected")
            self.assertTrue(row["error"])
            self.assertTrue(path.exists())
        self.assertEqual(len(self.store.list_by(limit=None)), 2)
        self.assertEqual(ordinary.read_text(), "A human note must never be silently imported")

    def test_stale_outbox_edit_has_visible_rejection_and_no_extra_append(self):
        source = self.source()
        first = self.submit(self.request(source), "a.json")
        second = self.submit(self.request(source, "Conflicting second edit"), "b.json")
        report = self.sync()
        statuses = [self.result_for(report, path)["status"] for path in (first, second)]
        self.assertCountEqual(statuses, ["committed", "rejected"])
        self.assertEqual(len(self.store.list_by(limit=None)), 2)

    def test_failed_acknowledgement_reports_commit_and_retry_repairs_it(self):
        request = self.request(self.source())
        path = self.submit(request)
        ack = self.sync_root / "acknowledgements" / f"{request['request_id']}.json"
        ack.mkdir(parents=True)
        first = self.result_for(self.sync(), path)
        self.assertEqual(first["status"], "committed")
        self.assertIs(first["receipt_written"], False)
        self.assertTrue(first["error"])
        self.assertEqual(len(self.store.list_by(limit=None)), 2)
        ack.rmdir()
        second = self.result_for(self.sync(), path)
        self.assertIs(second["receipt_written"], True)
        self.assertIs(second["receipt"]["replayed"], True)
        self.assertEqual(
            second["receipt"]["correction_drawer_id"], first["receipt"]["correction_drawer_id"]
        )
        self.assertTrue(ack.is_file())
        self.assertEqual(len(self.store.list_by(limit=None)), 2)

    def test_failed_projection_preserves_unmarked_note_and_durable_commit(self):
        source = self.source()
        request = self.request(source)
        path = self.submit(request)
        note = self.sync_root / "memory" / f"drawer-{source.id}.md"
        note.parent.mkdir()
        note.write_text("Entirely user-owned file")
        report = self.sync()
        self.assertEqual(self.result_for(report, path)["status"], "committed")
        self.assertEqual(report["projection"]["status"], "error")
        self.assertTrue(report["projection"]["error"])
        self.assertEqual(note.read_text(), "Entirely user-owned file")
        note.unlink()
        retried = self.sync()
        self.assertEqual(retried["projection"]["status"], "complete")
        self.assertEqual(len(self.store.list_by(limit=None)), 2)

    def test_refresh_preserves_annotations_and_escapes_only_markdown(self):
        text = "Raw <!-- cairntir:generated:begin -->\r\n<!-- cairntir:generated:end --> evidence"
        source = self.source(content=text)
        self.assertEqual(self.sync()["projection"]["status"], "complete")
        note = self.sync_root / "memory" / f"drawer-{source.id}.md"
        annotation = "\nHuman annotation: café remains exact.\n"
        with note.open("a", encoding="utf-8") as stream:
            stream.write(annotation)
        before = note.read_bytes()
        self.assertEqual(self.sync()["projection"]["status"], "complete")
        self.assertEqual(note.read_bytes(), before)
        self.assertEqual(self.manifest()["drawers"][0]["content"], text)
        rendered = note.read_text()
        self.assertEqual(rendered.count("<!-- cairntir:generated:begin -->"), 1)
        self.assertEqual(rendered.count("<!-- cairntir:generated:end -->"), 1)
        self.assertIn(annotation.strip(), rendered)

    def test_bound_vault_rejects_another_wing_without_replacing_inventory(self):
        self.source()
        self.sync()
        before = (self.sync_root / "workspace.json").read_bytes()
        try:
            report = self.sync(wing="foreign-wing")
        except self.bridge.CorrectionError:
            pass
        else:
            self.assertEqual(report["projection"]["status"], "error")
            self.assertFalse(any(row["status"] == "committed" for row in report["results"]))
        self.assertEqual((self.sync_root / "workspace.json").read_bytes(), before)

    def test_symlinked_outbox_request_cannot_import_external_content(self):
        source = self.source()
        external = self.root / "external.json"
        external.write_text(json.dumps(self.request(source)))
        link = self.outbox / "external.json"
        try:
            link.symlink_to(external)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable on this host: {exc}")
        before = external.read_bytes()
        try:
            report = self.sync()
        except self.bridge.CorrectionError:
            pass
        else:
            row = self.result_for(report, link)
            self.assertEqual(row["status"], "rejected")
        self.assertEqual(len(self.store.list_by(limit=None)), 1)
        self.assertEqual(external.read_bytes(), before)

    def test_cli_json_and_exit_status_report_success_and_rejection(self):
        from typer.testing import CliRunner
        from cairntir.cli import app

        request = self.request(self.source())
        self.submit(request)
        self.store.close()
        environment = {
            "CAIRNTIR_HOME": str(self.home),
            "CAIRNTIR_DISABLE_AUTOREGISTER": "1",
            "CAIRNTIR_DISABLE_UPDATE_CHECK": "1",
        }
        with (
            patch.dict(os.environ, environment),
            patch(
                "cairntir.cli.production_embedding_provider",
                return_value=HashEmbeddingProvider(dimension=16),
            ),
        ):
            first = CliRunner().invoke(
                app, ["obsidian-sync", str(self.vault), "--wing", "cairntir"]
            )
            self.assertEqual(first.exit_code, 0, first.output)
            self.assertEqual(json.loads(first.stdout)["projection"]["status"], "complete")
            (self.outbox / "malformed.json").write_text("not json")
            second = CliRunner().invoke(
                app, ["obsidian-sync", str(self.vault), "--wing", "cairntir"]
            )
            self.assertNotEqual(second.exit_code, 0)
            self.assertTrue(
                any(row["status"] == "rejected" for row in json.loads(second.stdout)["results"])
            )


if __name__ == "__main__":
    unittest.main()
