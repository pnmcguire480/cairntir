from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
IMMUTABLE_ACTION = re.compile(r"[^@\s]+@[0-9a-f]{40}")


def test_every_external_github_action_is_pinned_to_a_commit() -> None:
    unpinned: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            match = re.search(r"\buses:\s*([^\s#]+)", line)
            if match is None:
                continue
            action = match.group(1)
            if action.startswith("./"):
                continue
            if IMMUTABLE_ACTION.fullmatch(action) is None:
                unpinned.append(f"{workflow.name}:{line_number}: {action}")
    assert unpinned == []


def test_manual_release_dispatch_cannot_publish_or_create_a_release() -> None:
    workflow = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    tag_guard = "if: startsWith(github.ref, 'refs/tags/v')"
    assert workflow.count(tag_guard) == 2
    assert "actions/attest-build-provenance@" in workflow
    assert "attestations: write" in workflow
    assert "needs: verify" in workflow
    assert "uv run pytest -q" in workflow
