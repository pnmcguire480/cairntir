"""Visible independent E23 acceptance; temporary stores only."""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

from cairntir.errors import MCPError
from cairntir.mcp.backend import CairntirBackend
from cairntir.mcp.server import _dispatch, _tool_specs
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer
from cairntir.provenance import WriteProvenance


def envelope(text):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], isError=False)


def verify_report(case, result, budget, sources, eligible=None):
    case.assertFalse(result.isError)
    case.assertLessEqual(len(result.model_dump_json()), budget)
    case.assertEqual(len(result.content), 1)
    report = json.loads(result.content[0].text)
    case.assertEqual(report["schema"], "cairntir.recall-budget.v1")
    case.assertEqual(report["instruction_authority"], "none")
    case.assertEqual(report["notification_policy"], "excluded")
    case.assertEqual(report["budget"]["limit_chars"], budget)
    included = []
    for entry in report["evidence"]:
        identity = entry["drawer_id"]
        case.assertIn(identity, sources)
        if eligible is not None:
            case.assertIn(identity, eligible)
        content, provenance, supersedes_id = sources[identity]
        case.assertEqual(entry["content"], content)
        case.assertEqual(entry["content_sha256"], hashlib.sha256(content.encode()).hexdigest())
        case.assertEqual(entry["provenance"], provenance)
        case.assertEqual(entry["supersedes_id"], supersedes_id)
        included.append(identity)
    case.assertEqual(len(included), len(set(included)))
    omitted = report["omitted"]
    remaining = set(sources) - set(included)
    case.assertEqual(omitted["count"], len(remaining))
    case.assertIs(type(omitted["ids_complete"]), bool)
    case.assertEqual(len(omitted["drawer_ids"]), len(set(omitted["drawer_ids"])))
    case.assertTrue(set(omitted["drawer_ids"]) <= remaining)
    if omitted["ids_complete"]:
        case.assertEqual(set(omitted["drawer_ids"]), remaining)
    expected = "complete" if not remaining else "partial" if included else "omitted"
    case.assertEqual(report["status"], expected)
    return report


class RecallBudgetAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DrawerStore(Path(self.temp.name) / "test.db", HashEmbeddingProvider(32))
        self.addCleanup(self.store.close)
        self.backend = CairntirBackend(self.store)
        self.drawers = []
        self.sources = {}

    def add(self, content, provenance=None, supersedes_id=None):
        drawer = self.store.add(
            Drawer(wing="budget", room="evidence", content=content, supersedes_id=supersedes_id),
            provenance=provenance,
        )
        self.drawers.append(drawer)
        self.sources[drawer.id] = (
            content,
            self.store.get_provenance(drawer.id).to_dict(),
            supersedes_id,
        )
        return drawer.id

    def call(self, budget=8192, full_content=10, query="needle"):
        hits = [(drawer, index / 1000) for index, drawer in enumerate(self.drawers)]
        with patch.object(self.store, "search", return_value=hits):
            text = self.backend.recall_bounded(
                query=query,
                wing="budget",
                limit=max(10, len(hits)),
                full_content=full_content,
                budget_chars=budget,
            )
        eligible = {drawer.id for drawer in self.drawers[:full_content]}
        return verify_report(self, envelope(text), budget, self.sources, eligible)

    def test_schema_exposes_optional_bounded_integer(self):
        tool = next(tool for tool in _tool_specs() if tool.name == "cairntir_recall")
        prop = tool.inputSchema["properties"]["budget_chars"]
        self.assertEqual(prop["type"], "integer")
        self.assertEqual(prop["minimum"], 1024)
        self.assertEqual(prop["maximum"], 262144)
        self.assertNotIn("budget_chars", tool.inputSchema.get("required", []))

    def test_legacy_dispatch_retains_exact_recall(self):
        self.add("Original legacy text with café and a newline.\n")
        with patch.object(self.store, "search", return_value=[(self.drawers[0], 0.1)]):
            for full in (0, 1):
                args = {"query": "legacy", "full_content": full}
                self.assertEqual(
                    _dispatch(self.backend, "cairntir_recall", args), self.backend.recall(**args)
                )

    def test_budget_validation_rejects_nonintegers_and_boundaries(self):
        for invalid in (True, False, None, 1024.0, 2048.5, "2048", -1, 0, 1023, 262145):
            with self.subTest(budget=invalid), self.assertRaises(MCPError):
                self.backend.recall_bounded(query="needle", budget_chars=invalid)
        for valid in (1024, 262144):
            with self.subTest(budget=valid):
                self.call(budget=valid)

    def test_exact_unicode_whitespace_provenance_and_hash(self):
        identity = self.add('  café 雪 😀\r\nQuoted "value" and \\ path\t\n')
        report = self.call()
        self.assertEqual([entry["drawer_id"] for entry in report["evidence"]], [identity])
        self.assertTrue(report["omitted"]["ids_complete"])

    def test_cumulative_envelope_budget(self):
        for index in range(8):
            self.add(f"Evidence {index}: " + "a" * 650)
        report = self.call(budget=4096)
        self.assertEqual(report["status"], "partial")
        self.assertGreater(report["omitted"]["count"], 0)

    def test_correction_relationship_is_explicit_without_rewriting_history(self):
        original = self.add("Original specification: blue.")
        correction = self.add("Correction: green.", supersedes_id=original)
        report = self.call()
        entries = {entry["drawer_id"]: entry for entry in report["evidence"]}
        self.assertIsNone(entries[original]["supersedes_id"])
        self.assertEqual(entries[correction]["supersedes_id"], original)

    def test_escaping_overhead_cannot_be_ignored(self):
        self.add('"\\\n' * 220)
        report = self.call(budget=1024)
        self.assertEqual(report["evidence"], [])
        self.assertEqual(report["omitted"]["count"], 1)

    def test_later_eligible_evidence_survives_oversized_first(self):
        self.add("oversized " + "x" * 20000)
        small = self.add("Small complete fact.")
        self.add("Third fact is outside the requested full-content prefix.")
        report = self.call(budget=4096, full_content=2)
        self.assertEqual([entry["drawer_id"] for entry in report["evidence"]], [small])

    def test_zero_full_content_many_hits_are_explicit_omissions(self):
        for index in range(120):
            self.add(f"Routing evidence {index}")
        report = self.call(budget=1024, full_content=0)
        self.assertEqual(report["evidence"], [])
        self.assertEqual(report["omitted"]["count"], 120)

    def test_provenance_is_whole_or_omitted(self):
        self.add("Tiny fact.", WriteProvenance.create(host="h" * 20000, capture_path="public"))
        report = self.call(budget=4096)
        self.assertEqual(report["evidence"], [])

    def test_huge_query_no_hits_stays_bounded(self):
        report = self.call(budget=1024, query='"😀\\' * 15000)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["evidence"], [])


class RecallBudgetStdioAcceptance(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_bounds_complete_result_and_rejects_invalid_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "transport.db"
            sources = {}
            with DrawerStore(database, HashEmbeddingProvider(32)) as store:
                for index in range(5):
                    content = f'needle {index}: café 雪 "\\\n' + "v" * 700
                    drawer = store.add(Drawer(wing="budget", room="evidence", content=content))
                    sources[drawer.id] = (content, store.get_provenance(drawer.id).to_dict(), None)
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
                tools = await session.list_tools()
                tool = next(tool for tool in tools.tools if tool.name == "cairntir_recall")
                self.assertIn("budget_chars", tool.inputSchema["properties"])
                args = {"query": "needle", "wing": "budget", "limit": 5, "full_content": 5}
                for budget in (1024, 16384):
                    result = await session.call_tool(
                        "cairntir_recall", {**args, "budget_chars": budget}
                    )
                    report = verify_report(self, result, budget, sources)
                    if budget == 16384:
                        self.assertEqual(report["status"], "complete")
                        self.assertEqual(len(report["evidence"]), 5)
                for invalid in (True, None, 1024.5, "2048", 1023, 262145):
                    with self.subTest(budget=invalid):
                        result = await session.call_tool(
                            "cairntir_recall", {**args, "budget_chars": invalid}
                        )
                        self.assertTrue(result.isError)
                        self.assertTrue(result.content)
                result = await session.call_tool(
                    "cairntir_recall",
                    {"query": "missing" * 15000, "wing": "absent", "budget_chars": 1024},
                )
                verify_report(self, result, 1024, {})
            self.assertFalse((root / "isolated-home").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
