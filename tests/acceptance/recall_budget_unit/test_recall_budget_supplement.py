"""Post-implementation public validation and real routing-overflow acceptance."""

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.errors import MCPError
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


class RecallBudgetValidationSupplement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DrawerStore(Path(self.temp.name) / "validation.db", HashEmbeddingProvider(32))
        self.addCleanup(self.store.close)
        self.backend = CairntirBackend(self.store)

    def reject(self, field, invalid_values):
        for value in invalid_values:
            with (
                self.subTest(field=field, value=value),
                patch.object(self.store, "search") as search,
            ):
                arguments = {"query": "valid", "limit": 10, "full_content": 1, "budget_chars": 1024}
                arguments[field] = value
                with self.assertRaises(MCPError):
                    self.backend.recall_bounded(**arguments)
                search.assert_not_called()

    def test_invalid_query_is_rejected_before_retrieval(self):
        self.reject("query", [None, False, 42, [], {}, "", " \r\n\t"])

    def test_invalid_limit_is_rejected_before_retrieval(self):
        self.reject("limit", [None, True, False, 1.0, 1.5, "10", 0, -1])

    def test_invalid_full_content_is_rejected_before_retrieval(self):
        self.reject("full_content", [None, True, False, 0.0, 1.5, "1", -1])


class RecallRoutingOverflowSupplement(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_truncates_routing_ids_explicitly_and_ids_remain_retrievable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "routing.db"
            sources = {}
            with DrawerStore(database, HashEmbeddingProvider(32)) as store:
                for index in range(600):
                    content = f"routing needle {index}: exact café evidence"
                    drawer = store.add(Drawer(wing="routing", room="overflow", content=content))
                    sources[drawer.id] = content
            env = dict(os.environ)
            env.pop("CAIRNTIR_GRANT_FILE", None)
            env.update(
                CAIRNTIR_HOME=str(root / "isolated-home"),
                CAIRNTIR_DISABLE_AUTOREGISTER="1",
                CAIRNTIR_DISABLE_UPDATE_CHECK="1",
                PYTHONIOENCODING="utf-8",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
            )
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).with_name("stdio_fixture.py")), str(database)],
                cwd=str(root),
                env=env,
            )
            async with (
                stdio_client(parameters) as (reader, writer),
                ClientSession(
                    reader, writer, read_timeout_seconds=timedelta(seconds=30)
                ) as session,
            ):
                await session.initialize()
                result = await session.call_tool(
                    "cairntir_recall",
                    {
                        "query": "routing needle",
                        "wing": "routing",
                        "limit": 600,
                        "full_content": 0,
                        "budget_chars": 1024,
                    },
                )
                self.assertFalse(result.isError)
                self.assertLessEqual(len(result.model_dump_json()), 1024)
                self.assertEqual(len(result.content), 1)
                report = json.loads(result.content[0].text)
                self.assertEqual(report["schema"], "cairntir.recall-budget.v1")
                self.assertEqual(report["status"], "omitted")
                self.assertEqual(report["evidence"], [])
                self.assertEqual(report["budget"]["limit_chars"], 1024)
                self.assertEqual(report["notification_policy"], "excluded")
                omitted = report["omitted"]
                self.assertEqual(omitted["count"], len(sources))
                identities = omitted["drawer_ids"]
                self.assertGreater(len(identities), 0)
                self.assertLess(len(identities), omitted["count"])
                self.assertEqual(len(set(identities)), len(identities))
                self.assertIs(omitted["ids_complete"], False)
                self.assertTrue(set(identities) <= sources.keys())
                for identity in identities:
                    retrieved = await session.call_tool("cairntir_get", {"drawer_id": identity})
                    self.assertFalse(retrieved.isError)
                    evidence = json.loads(retrieved.content[0].text)
                    self.assertEqual(evidence["id"], identity)
                    self.assertEqual(evidence["content"], sources[identity])


if __name__ == "__main__":
    unittest.main(verbosity=2)
