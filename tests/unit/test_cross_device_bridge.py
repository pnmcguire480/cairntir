"""Exercise two independent participants and an unrelated private store."""

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from starlette.testclient import TestClient

from cairntir.bridge import Access, BridgeError, Relay
from cairntir.bridge_server import make_app
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.portable import export_bundle, import_bundle


class BridgeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.relay = Relay(self.root / "relay.db")
        self.channel = self.relay.connect(None, True)
        self.phone = self.relay.invite(self.channel, Access.send, None, True)
        self.desktop = self.relay.invite(self.channel, Access.exchange, None, True)
        self.item = uuid4()

    def test_isolation_and_transfer_lifecycle(self):
        private = self.root / "private.db"
        private.write_bytes(b"private sentinel")
        self.relay.post(self.phone["bearer"], self.item, "Verbatim 🐈\nsecond line")
        self.relay.post(self.phone["bearer"], self.item, "Verbatim 🐈\nsecond line")
        with self.assertRaises(BridgeError):
            self.relay.post(self.phone["bearer"], self.item, "different")
        with self.assertRaises(BridgeError):
            self.relay.pending(self.phone["bearer"])
        other = self.relay.connect(10, False)
        token = self.relay.invite(other, Access.exchange, 5, False)["bearer"]
        self.assertEqual(self.relay.pending(token), [])
        with self.assertRaises(BridgeError):
            self.relay.read(token, self.item)
        with self.assertRaises(BridgeError):
            self.relay.finish(token, self.item, "done")
        read_only = self.relay.invite(self.channel, Access.receive, 5, False)["bearer"]
        self.assertEqual(self.relay.read(read_only, self.item)["text"], "Verbatim 🐈\nsecond line")
        with self.assertRaises(BridgeError):
            self.relay.post(read_only, uuid4(), "cannot publish")
        with self.assertRaises(BridgeError):
            self.relay.finish(read_only, self.item, "done")
        self.assertEqual(len(self.relay.pending(self.desktop["bearer"])), 1)
        self.relay.finish(self.desktop["bearer"], self.item, "prototype printed")
        self.relay.finish(self.desktop["bearer"], self.item, "prototype printed")
        with self.assertRaises(BridgeError):
            self.relay.finish(self.desktop["bearer"], self.item, "overwritten")
        self.assertEqual(self.relay.pending(self.desktop["bearer"]), [])
        self.assertEqual(private.read_bytes(), b"private sentinel")
        self.assertNotIn(b"private sentinel", self.relay.path.read_bytes())
        self.assertNotIn(self.phone["bearer"].encode(), self.relay.path.read_bytes())

    def test_expiry_and_disconnect(self):
        with patch("cairntir.bridge.time.time", return_value=100):
            short = self.relay.invite(self.channel, Access.receive, 1, False)
            temp = self.relay.connect(1, False)
            long_pass = self.relay.invite(temp, Access.exchange, None, True)
        with patch("cairntir.bridge.time.time", return_value=160):
            for pass_ in [short, long_pass]:
                with self.assertRaises(BridgeError):
                    self.relay.pending(pass_["bearer"])
        self.relay.revoke(self.phone["pass_id"])
        with self.assertRaises(BridgeError):
            self.relay.post(self.phone["bearer"], self.item, "test")
        self.assertEqual(self.relay.pending(self.desktop["bearer"]), [])
        self.relay.revoke(self.channel)
        with self.assertRaises(BridgeError):
            self.relay.pending(self.desktop["bearer"])

    def test_selected_portable_evidence_and_separate_destination_import(self):
        selected = self.root / "selected.json"
        received = self.root / "received.json"
        now = datetime.now(UTC)
        provider = HashEmbeddingProvider(dimension=16)
        with DrawerStore(self.root / "source.db", provider) as source:
            source.add(
                Drawer(wing="private", room="notes", content="hidden sentinel", created_at=now)
            )
            shared = source.add(
                Drawer(wing="work", room="ideas", content="bench idea", created_at=now)
            )
            export_bundle(source, selected, drawer_ids=[shared.id])
        self.relay.post(self.phone["bearer"], self.item, selected.read_text(encoding="utf-8"))
        with DrawerStore(self.root / "destination.db", provider) as dest:
            self.assertFalse(dest.list_by(wing="work"))
            offered = self.relay.read(self.desktop["bearer"], self.item)["text"]
            self.assertNotIn("hidden sentinel", offered)
            received.write_text(offered, encoding="utf-8")
            self.assertFalse(dest.list_by(wing="work"))
            self.assertEqual(import_bundle(dest, received)["imported"], 1)
            import_bundle(dest, received)
            self.assertEqual(len(dest.list_by(wing="work")), 1)
            self.assertEqual(dest.list_by(wing="work")[0].content, "bench idea")
            self.assertFalse(dest.list_by(wing="private"))

    def test_actual_mcp_http_tools_and_post_revocation(self):
        with TestClient(make_app(self.relay), base_url="http://127.0.0.1:8765") as peer:

            def call(method, params, token):
                return peer.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer " + token,
                    },
                    json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                )

            self.assertEqual(call("tools/list", {}, "invalid").status_code, 401)
            defs = call("tools/list", {}, self.phone["bearer"]).json()["result"]["tools"]
            self.assertEqual(
                {t["name"] for t in defs},
                {"bridge_send", "bridge_list", "bridge_read", "bridge_finish"},
            )
            posted = call(
                "tools/call",
                {
                    "name": "bridge_send",
                    "arguments": {"item_id": str(self.item), "text": "from phone"},
                },
                self.phone["bearer"],
            )
            self.assertFalse(posted.json()["result"]["isError"])
            found = call(
                "tools/call",
                {"name": "bridge_read", "arguments": {"item_id": str(self.item)}},
                self.desktop["bearer"],
            ).json()["result"]
            self.assertEqual(found["structuredContent"]["text"], "from phone")
            self.relay.revoke(self.desktop["pass_id"])
            self.assertEqual(call("tools/list", {}, self.desktop["bearer"]).status_code, 401)
