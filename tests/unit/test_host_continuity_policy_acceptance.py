"""Independent policy contract and distribution checks, not model-behavior claims."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from cairntir.hosts import (
    MEMORY_POLICY,
    POLICY_BEGIN_MARKER,
    POLICY_END_MARKER,
    configure_host,
)


def _text() -> str:
    return re.sub(r"\s+", " ", MEMORY_POLICY.replace("`", "")).lower()


def _clause_containing(*patterns: str) -> bool:
    text = _text()
    for match in re.finditer(patterns[0], text):
        window = text[max(0, match.start() - 240) : match.end() + 360]
        if all(re.search(pattern, window) for pattern in patterns[1:]):
            return True
    return False


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(POLICY_BEGIN_MARKER) == text.count(POLICY_END_MARKER) == 1
    return text.split(POLICY_BEGIN_MARKER, 1)[1].split(POLICY_END_MARKER, 1)[0].strip()


def test_policy_reuses_known_project_identity_and_carries_it_across_compaction() -> None:
    text = _text()
    assert re.search(
        r"(?:reuse|preserve|keep|retain|prefer|use).{0,70}(?:known|saved|existing) wing", text
    )
    assert _clause_containing(r"summar(?:y|ies)", r"\bwing\b", r"task_id", r"revision")
    assert _clause_containing(r"(?:folder|directory)", r"(?:unknown|not known|no known|missing)")


def test_exact_corrections_are_attached_to_the_same_task_before_more_work() -> None:
    assert _clause_containing(
        r"correction",
        r"constraint",
        r"(?:exact|verbatim)",
        r"(?:same|existing|current|selected) task",
        r"checkpoint",
        r"content",
        r"outstanding",
        r"before",
    )


def test_terminal_or_unavailable_task_does_not_switch_to_another_task() -> None:
    assert _clause_containing(
        r"unavailable", r"terminal", r"(?:stop|report|check)", r"(?:identity|wing|task_id)"
    )
    assert _clause_containing(
        r"unavailable", r"(?:never|do not|don't)", r"(?:another|different|other) task"
    )


def test_open_requests_remain_within_selected_authorized_scope() -> None:
    assert _clause_containing(
        r"authoriz", r"(?:current|this|selected)", r"(?:scope|conversation|task)"
    )
    if "owed" in _text():
        assert _clause_containing(r"owed", r"(?:authoriz|selected|current conversation)")


def test_capture_has_one_creation_write_and_honest_legacy_fallback() -> None:
    assert _clause_containing(
        r"(?:creat|capture-on-arrival)", r"(?:do not|never|don't).{0,70}duplicat"
    )
    assert _clause_containing(r"(?:unsupported|lacks|older)", r"ordinary.{0,30}remember")
    assert _clause_containing(r"(?:unsupported|lacks|older)", r"ordinary.{0,30}handoff")
    assert _clause_containing(r"(?:unsupported|lacks|older)", r"(?:disclos|upgrade|limitation)")


def test_policy_retains_recovery_receipt_and_progress_honesty() -> None:
    text = _text()
    assert "compaction" in text and "continuity" in text
    for term in ("completed", "outstanding", "next_action", "idempotency_key", "expected_revision"):
        assert term in text
    assert _clause_containing(r"receipt", r"(?:success|acknowledg)", r"fail")
    assert re.search(r"(?:never|do not|don't) invent", text)
    assert _clause_containing(r"checkpoint", r"(?:current files|working state|git state)")


def test_policy_retains_evidence_and_opt_in_recovery_boundaries() -> None:
    text = _text()
    assert _clause_containing(r"approval", r"(?:no|not|never).{0,40}(?:execution|authority)")
    assert _clause_containing(r"transcript recovery", r"(?:opt-in|explicitly|only when)")
    assert _clause_containing(
        r"(?:automatically|automatic)", r"(?:not|no|never)", r"(?:capture|record|watch)"
    )
    assert "cairntir_recall" in text and "cairntir_get" in text
    assert "cairntir_crucible" in text and "cairntir_audit" in text


def test_policy_is_shorter_than_the_reviewed_775_word_draft() -> None:
    assert len(MEMORY_POLICY.split()) < 775


@pytest.mark.parametrize(
    ("host", "relative"),
    [
        ("claude", "CLAUDE.md"),
        ("codex", "AGENTS.md"),
        ("cursor", ".cursor/rules/cairntir.mdc"),
        ("qwen", "QWEN.md"),
        ("gemini", "GEMINI.md"),
        ("copilot", "AGENTS.md"),
        ("opencode", "AGENTS.md"),
    ],
)
def test_configured_project_hosts_receive_same_policy_without_rewriting_user_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: Any, relative: str
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("isolated project policy acceptance must not launch a host CLI")

    monkeypatch.setattr("cairntir.hosts._run_cli", forbidden)
    project = tmp_path / "project-with-another-folder-name"
    target = project / relative
    target.parent.mkdir(parents=True)
    prefix = "# User instructions before\nKeep my constraints.\n"
    suffix = "\n# User instructions after\nPreserve this section.\n"
    target.write_text(
        prefix + POLICY_BEGIN_MARKER + "\nStale policy\n" + POLICY_END_MARKER + suffix,
        encoding="utf-8",
    )
    result = configure_host(host, scope="project", root=project, home=tmp_path / "home")
    assert result.policy_path == target and result.policy == "updated"
    assert _body(target) == MEMORY_POLICY.strip()
    text = target.read_text(encoding="utf-8")
    assert text.startswith(prefix) and text.endswith(suffix)
    before = target.read_bytes()
    repeat = configure_host(host, scope="project", root=project, home=tmp_path / "home")
    assert repeat.policy == "unchanged"
    assert target.read_bytes() == before


@pytest.mark.parametrize("host", ["cursor", "cline"])
def test_manual_user_rule_hosts_do_not_claim_a_policy_was_installed(
    tmp_path: Path, host: Any
) -> None:
    result = configure_host(host, scope="user", root=tmp_path / "project", home=tmp_path / "home")
    assert result.policy_path is None
    assert result.policy.startswith("manual:")


@pytest.mark.parametrize(
    "relative", ["CLAUDE.md", "AGENTS.md", "QWEN.md", ".cursor/rules/cairntir.mdc"]
)
def test_repository_policy_blocks_match_the_generator(relative: str) -> None:
    root = Path(__file__).resolve().parents[2]
    assert _body(root / relative) == MEMORY_POLICY.strip()
