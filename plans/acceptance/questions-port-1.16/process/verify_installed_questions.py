"""Additive R08 proof inside the existing disposable installed-wheel verifier."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from uuid import uuid4


async def verify_installed_questions(
    *, cli, mcp, home, peer_factory, execute, environment, version
):
    """Use supplied installed entrypoints and the existing verifier's real MCP peer."""
    import cairntir

    assert cairntir.__version__ == version
    home.mkdir(parents=True, exist_ok=False)
    wing = "installed-question-proof"
    support_text = "  Installed supporting evidence café\r\n\r\nlast space \r\n"
    question_text = "  Which exact measurement explains the result? café\r\n  "
    resolution_text = "  Declared evidence-linked answer café\r\n  "
    cli_calls = 0
    tool_calls = 0

    def call(*args):
        nonlocal cli_calls
        cli_calls += 1
        output = execute([str(cli), "question", *args], home, environment(home), timeout=60)
        return json.loads(output)

    def raw_row(drawer_id):
        with closing(sqlite3.connect(home / "cairntir.db")) as connection:
            return connection.execute(
                "SELECT content,metadata,provenance,room,supersedes_id FROM drawers WHERE id=?",
                (drawer_id,),
            ).fetchone()

    async with peer_factory(mcp, home, "codex") as first:
        await first.initialize(version)
        tools = (await first.request("tools/list", {}))["tools"]
        assert len(tools) == len({tool["name"] for tool in tools}) == 21
        await first.tool("cairntir_remember", wing=wing, room="evidence", content=support_text)
        tool_calls += 1
        with closing(sqlite3.connect(home / "cairntir.db")) as connection:
            rows = connection.execute(
                "SELECT id FROM drawers WHERE wing=? AND room='evidence' AND content=?",
                (wing, support_text),
            ).fetchall()
            assert len(rows) == 1
            support_id = rows[0][0]
            identity = connection.execute(
                "SELECT identity FROM portable_records WHERE drawer_id=?", (support_id,)
            ).fetchone()[0]
        support = await first.json("cairntir_get", drawer_id=support_id)
        tool_calls += 1
        assert support["content"] == support_text
        evidence = {
            "drawer_id": support_id,
            "source_identity": identity,
            "content_sha256": hashlib.sha256(support_text.encode()).hexdigest(),
        }
        opening = {
            "schema": "cairntir.question-open.v1",
            "request_id": str(uuid4()),
            "wing": wing,
            "room": "work",
            "content": question_text,
            "owner": "  Declared installed owner  ",
            "evidence": [evidence],
        }
        opening_file = home / "opening.json"
        opening_file.write_text(json.dumps(opening, ensure_ascii=False), encoding="utf-8")
        opened = call("open", str(opening_file), "--wing", wing)
        assert opened["status"] == "committed" and opened["replayed"] is False
        assert opened["question_sha256"] == hashlib.sha256(question_text.encode()).hexdigest()
        assert call("open", str(opening_file), "--wing", wing) == {**opened, "replayed": True}
        listed = call("list", "--wing", wing)
        assert len(listed["questions"]) == 1
        assert listed["questions"][0]["question_id"] == opened["question_id"]
        assert listed["questions"][0]["content"] == question_text
        assert listed["questions"][0]["owner"] == opening["owner"]
        assert listed["questions"][0]["evidence"] == [evidence]
        original = raw_row(opened["question_drawer_id"])
        brief = (await first.tool("cairntir_handoff", wing=wing))["content"][0]["text"]
        tool_calls += 1
        assert "## Open questions (1)" in brief
        section = brief.split("## Open questions (1)", 1)[1].split("\n## ", 1)[0]
        assert f"#{opened['question_drawer_id']}  " in section
    # A fresh MCP process and fresh CLI invocations must observe durable resolution.
    resolution = {
        "schema": "cairntir.question-resolve.v1",
        "request_id": str(uuid4()),
        "wing": wing,
        "question_id": opened["question_id"],
        "question_drawer_id": opened["question_drawer_id"],
        "question_sha256": opened["question_sha256"],
        "content": resolution_text,
        "evidence": [evidence],
    }
    resolution_file = home / "resolution.json"
    resolution_file.write_text(json.dumps(resolution, ensure_ascii=False), encoding="utf-8")
    resolved = call("resolve", str(resolution_file), "--wing", wing)
    assert resolved["status"] == "committed" and resolved["replayed"] is False
    assert resolved["question_id"] == opened["question_id"]
    assert resolved["question_drawer_id"] == opened["question_drawer_id"]
    assert call("resolve", str(resolution_file), "--wing", wing) == {**resolved, "replayed": True}
    assert call("list", "--wing", wing)["questions"] == []
    history = call("list", "--wing", wing, "--include-resolved")["questions"]
    assert len(history) == 1 and history[0]["status"] == "resolved"
    assert history[0]["resolution"]["content"] == resolution_text
    assert history[0]["resolution"]["evidence"] == [evidence]
    assert raw_row(opened["question_drawer_id"]) == original
    assert raw_row(support_id)[0] == support_text
    async with peer_factory(mcp, home, "claude-code") as second:
        await second.initialize(version)
        stored = await second.json("cairntir_get", drawer_id=resolved["resolution_drawer_id"])
        tool_calls += 1
        assert stored["content"] == resolution_text
        brief = (await second.tool("cairntir_handoff", wing=wing))["content"][0]["text"]
        tool_calls += 1
        assert "## Open questions" not in brief
    with closing(sqlite3.connect(home / "cairntir.db")) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM drawers WHERE wing=?", (wing,)
        ).fetchone() == (3,)
    assert cli_calls == 7 and tool_calls == 5
    return {
        "status": "PASS",
        "installed_module": str(cairntir.__file__),
        "cli_calls": cli_calls,
        "mcp_processes": 2,
        "mcp_tool_calls": tool_calls,
        "mcp_tools": 21,
        "opening_and_resolution_exact_replay": "PASS",
        "original_evidence_and_question_preserved": "PASS",
        "restart_handoff_classification": "PASS",
        "native_graphical_obsidian": "not exercised",
    }
