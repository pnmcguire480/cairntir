"""The README must not drift from the code it describes.

The README is the first thing a prospective user reads and the last thing
anyone remembers to update. It claimed **eighteen** MCP tools while the
server exposed nineteen, and listed `code-review-graph` as "in progress"
months after `recall_for_change` shipped.

Neither is a big lie. Both are the same small one this project keeps
finding: a written claim nobody checks. These tests check the claims that
are mechanically checkable — a count and a set of links — and leave the
prose to human judgement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cairntir.mcp.server import _tool_specs

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


def test_the_advertised_tool_count_matches_the_server(readme: str) -> None:
    """ "18 tools" outlived the eighteenth tool. Do not let it happen again.

    The count is load-bearing marketing — restraint is the claim — so a
    stale number undersells or oversells a deliberate design decision.
    """
    actual = len(_tool_specs())

    match = re.search(r"\*\*(\d+) tools\*\* over stdio", readme)
    assert match is not None, "README no longer states the tool count in a checkable form"
    assert int(match.group(1)) == actual, (
        f"README advertises {match.group(1)} MCP tools, server exposes {actual}"
    )


def test_every_relative_link_resolves(readme: str) -> None:
    """A broken path in the README is a broken first impression."""
    targets = re.findall(r"\]\((?!https?://|#)([^)]+)\)", readme)
    assert targets, "no relative links found — the extraction regex probably broke"

    missing = [t for t in targets if not (REPO_ROOT / t.split("#")[0]).exists()]

    assert not missing, f"README links to paths that do not exist: {missing}"


def test_documented_cli_commands_exist(readme: str) -> None:
    """The project-structure block lists CLI commands. They must be real."""
    from cairntir.cli import app

    match = re.search(r"# cairntir ([a-z0-9 |\-]+)\n", readme)
    assert match is not None, "the cli.py comment listing commands is gone or reshaped"
    advertised = {part.strip() for part in match.group(1).split("|") if part.strip()}

    registered = {
        command.name or (command.callback.__name__ if command.callback else "")
        for command in app.registered_commands
    }

    missing = advertised - registered
    assert not missing, f"README advertises CLI commands that do not exist: {sorted(missing)}"
