"""Tests for scripts/check_landed_commitments.py.

The script's whole value is that it **fails** when a plan promises
something the code lacks. A check that only passes is decoration, so most
of these tests construct the failure and assert it is caught.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_landed_commitments.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_landed_commitments", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations through sys.modules[cls.__module__],
    # so a module loaded from a path must be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _assertion(kind: str, target: str, detail: str = "") -> object:
    return script.Assertion(
        kind=kind,
        target=REPO_ROOT / target,
        detail=detail,
        source=REPO_ROOT / "plans" / "example.md",
        line=1,
    )


# ------------------------------------------------------------------ the repo


def test_the_real_repository_has_no_unlanded_commitments() -> None:
    """The binding gate. Every block anywhere in the repo must verify."""
    result = subprocess.run(  # noqa: S603 - argv is sys.executable plus a literal path
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_field_report_commitment_block_is_actually_being_checked() -> None:
    """Guard against the block being parsed as prose and silently ignored."""
    assertions = script.collect()
    targets = {a.detail for a in assertions}
    assert "compose:budget_chars" in targets
    assert "handoff:budget_chars" in targets


# --------------------------------------------------------------- detection


def test_a_missing_symbol_is_caught() -> None:
    failure = script.check(_assertion("symbol", "src/cairntir/handoff.py", "nonexistent_thing"))
    assert failure is not None
    assert "no symbol named 'nonexistent_thing'" in failure


def test_a_missing_parameter_is_caught_and_the_real_ones_are_listed() -> None:
    """This is the assertion kind that would have caught the v1.2 miss.

    ``session_start`` existed the whole time. It simply never grew the
    budget argument the plan committed to.
    """
    failure = script.check(_assertion("param", "src/cairntir/handoff.py", "compose:token_ceiling"))
    assert failure is not None
    assert "has no parameter 'token_ceiling'" in failure
    assert "budget_chars" in failure, "the message should show what it does accept"


def test_a_missing_file_is_caught() -> None:
    failure = script.check(_assertion("file", "docs/a-file-that-was-never-written.md"))
    assert failure is not None
    assert "does not exist" in failure


def test_a_missing_test_is_caught() -> None:
    failure = script.check(_assertion("test", "tests/unit/test_handoff.py", "test_never_written"))
    assert failure is not None
    assert "no test named 'test_never_written'" in failure


def test_a_missing_function_reports_the_function_not_the_parameter() -> None:
    failure = script.check(_assertion("param", "src/cairntir/handoff.py", "no_such_fn:x"))
    assert failure is not None
    assert "no function named 'no_such_fn'" in failure


# ------------------------------------------------------------ what passes


def test_a_satisfied_assertion_passes() -> None:
    assert script.check(_assertion("symbol", "src/cairntir/handoff.py", "compose")) is None
    assert script.check(_assertion("param", "src/cairntir/handoff.py", "compose:wing")) is None
    assert script.check(_assertion("file", "docs/release-cadence.md")) is None


def test_methods_and_keyword_only_parameters_are_found() -> None:
    """Cairntir uses keyword-only arguments almost everywhere."""
    assert script.check(_assertion("symbol", "src/cairntir/mcp/backend.py", "handoff")) is None
    assert (
        script.check(_assertion("param", "src/cairntir/mcp/backend.py", "handoff:budget_chars"))
        is None
    )


def test_self_is_not_counted_as_a_parameter() -> None:
    failure = script.check(_assertion("param", "src/cairntir/mcp/backend.py", "handoff:self"))
    assert failure is not None


# --------------------------------------------------------------- parsing


def test_comments_and_blank_lines_are_skipped() -> None:
    block = "# a note about why\n\nfile docs/release-cadence.md\n"
    parsed = script.parse_block(block, source=REPO_ROOT / "plans" / "x.md", first_line=1)
    assert len(parsed) == 1


def test_an_unknown_assertion_kind_is_a_failure_not_a_skip() -> None:
    """A block nobody can parse is a block nobody is checking.

    Precisely how the four-segment version proposal would have broken
    check_release_tags.py — a `## [1.2.0.0]` header would have been
    skipped rather than flagged.
    """
    with pytest.raises(script.MalformedCommitmentError, match="unknown assertion kind"):
        script.parse_block(
            "ensure src/cairntir/handoff.py compose",
            source=REPO_ROOT / "plans" / "x.md",
            first_line=1,
        )


def test_wrong_arity_is_rejected() -> None:
    with pytest.raises(script.MalformedCommitmentError, match="takes a path and a name"):
        script.parse_block(
            "symbol src/cairntir/handoff.py",
            source=REPO_ROOT / "plans" / "x.md",
            first_line=1,
        )
    with pytest.raises(script.MalformedCommitmentError, match="takes exactly one path"):
        script.parse_block(
            "file docs/release-cadence.md extra",
            source=REPO_ROOT / "plans" / "x.md",
            first_line=1,
        )


def test_param_without_a_colon_is_rejected() -> None:
    with pytest.raises(script.MalformedCommitmentError, match="wants `function:parameter`"):
        script.parse_block(
            "param src/cairntir/handoff.py compose",
            source=REPO_ROOT / "plans" / "x.md",
            first_line=1,
        )


def test_a_malformed_block_fails_the_whole_run(tmp_path: Path) -> None:
    """End to end: malformed input must exit non-zero, not warn and continue."""
    doc = REPO_ROOT / "plans" / "_tmp_malformed_commitment.md"
    doc.write_text(
        "# scratch\n\n```cairntir-commitments\nnonsense whatever\n```\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603 - argv is sys.executable plus a literal path
            [sys.executable, str(SCRIPT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        doc.unlink()
    assert result.returncode == 1
    assert "unknown assertion kind" in result.stderr
