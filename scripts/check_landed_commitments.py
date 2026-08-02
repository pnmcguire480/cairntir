"""Fail the build when a plan document promises something the code lacks.

The defect this closes is the oldest one in the lineage, and the only one
present in all four generations. BrainStormer's 2026-04-03 harness audit
named it: *infrastructure without the enforcement layer.* It recurred at
the level of the recovery plan itself — the 2026-07-27 evolution audit
correctly diagnosed that Cairntir had lost its context budget, wrote
"restore explicit context budgets in the v1.2 core" into the plan, and
then v1.2 shipped, was verified across three hosts, released to PyPI and
attested **without the fix**. Nobody noticed for five days.

The pattern is not "we build badly." It is **"we do not verify that a
commitment landed."**

``scripts/check_release_tags.py`` already proves the shape of the answer
for one narrow case: a changelog header is a claim, and CI fails if the
matching tag does not exist. This generalises it. A plan document may
carry a fenced ``cairntir-commitments`` block whose lines are assertions
about the codebase, and this script verifies every one::

    ```cairntir-commitments
    file   docs/release-cadence.md
    symbol src/cairntir/handoff.py compose
    param  src/cairntir/mcp/backend.py handoff:budget_chars
    test   tests/unit/test_handoff.py test_included_drawers_are_returned_whole
    ```

Four assertion kinds, deliberately few:

``file <path>``
    The path exists.
``symbol <path> <name>``
    That Python file defines a function, method, or class of that name,
    at any nesting depth.
``param <path> <function>:<parameter>``
    That function accepts that parameter — positional or keyword-only.
    This is the one that would have caught the v1.2 miss, because
    ``session_start`` existed the whole time; it just never grew a
    ``budget`` argument.
``test <path> <name>``
    That test file defines a test of that name. A commitment with no
    test is a commitment that will regress quietly.

A malformed block is a failure, never a skip. Silently ignoring an
assertion nobody can parse would reproduce the exact defect this script
exists to prevent — and that is not hypothetical: the four-segment
version proposal was rejected in drawer #177 precisely because
``check_release_tags.py`` would have *skipped* a ``## [1.2.0.0]`` header
rather than flagging it.

Exit code 1 if any assertion fails. Wired into the CI lint job.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SEARCH_GLOBS = ("plans/**/*.md", "docs/**/*.md", "*.md")

BLOCK = re.compile(
    r"^```cairntir-commitments\s*\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)

VALID_KINDS = ("file", "symbol", "param", "test")


@dataclass(frozen=True)
class Assertion:
    """One checkable promise made by a plan document."""

    kind: str
    target: Path
    detail: str
    source: Path
    line: int

    def describe(self) -> str:
        """Render as the assertion would appear in the plan, plus its origin."""
        body = f"{self.kind} {self.target.as_posix()}"
        if self.detail:
            body += f" {self.detail}"
        rel = self.source.relative_to(REPO_ROOT).as_posix()
        return f"{body}  ({rel}:{self.line})"


class MalformedCommitmentError(ValueError):
    """Raised when a commitment block cannot be parsed.

    Not caught and downgraded anywhere. An assertion nobody can read is
    an assertion nobody is checking.
    """


def _documents() -> list[Path]:
    seen: set[Path] = set()
    for pattern in SEARCH_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file():
                seen.add(path)
    return sorted(seen)


def parse_block(body: str, *, source: Path, first_line: int) -> list[Assertion]:
    """Parse one commitment block into assertions, or raise."""
    out: list[Assertion] = []
    for offset, raw in enumerate(body.splitlines()):
        line_no = first_line + offset
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        kind = parts[0]
        if kind not in VALID_KINDS:
            raise MalformedCommitmentError(
                f"{source.name}:{line_no}: unknown assertion kind {kind!r}; "
                f"expected one of {', '.join(VALID_KINDS)}"
            )
        if kind == "file":
            if len(parts) != 2:
                raise MalformedCommitmentError(
                    f"{source.name}:{line_no}: `file` takes exactly one path, got {len(parts) - 1}"
                )
            detail = ""
        else:
            if len(parts) != 3:
                raise MalformedCommitmentError(
                    f"{source.name}:{line_no}: `{kind}` takes a path and a name, "
                    f"got {len(parts) - 1} argument(s)"
                )
            detail = parts[2]
        if kind == "param" and ":" not in detail:
            raise MalformedCommitmentError(
                f"{source.name}:{line_no}: `param` wants `function:parameter`, got {detail!r}"
            )
        out.append(
            Assertion(
                kind=kind,
                target=REPO_ROOT / parts[1],
                detail=detail,
                source=source,
                line=line_no,
            )
        )
    return out


def collect() -> list[Assertion]:
    """Gather every assertion declared anywhere in the repo's documents."""
    found: list[Assertion] = []
    for doc in _documents():
        text = doc.read_text(encoding="utf-8")
        for match in BLOCK.finditer(text):
            first_line = text[: match.start(1)].count("\n") + 1
            found.extend(parse_block(match.group(1), source=doc, first_line=first_line))
    return found


def _defined_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
    return names


def _parameters(tree: ast.AST, function: str) -> set[str] | None:
    """Return the parameter names of ``function``, or None if it is absent."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != function:
            continue
        args = node.args
        return {
            a.arg
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
            if a.arg not in ("self", "cls")
        }
    return None


def check(assertion: Assertion) -> str | None:
    """Verify one assertion. Returns a failure message, or None on success."""
    if not assertion.target.exists():
        return f"{assertion.describe()}\n    -> the file does not exist"
    if assertion.kind == "file":
        return None

    try:
        tree = ast.parse(assertion.target.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return f"{assertion.describe()}\n    -> could not parse: {exc}"

    if assertion.kind in ("symbol", "test"):
        if assertion.detail in _defined_names(tree):
            return None
        noun = "test" if assertion.kind == "test" else "symbol"
        return f"{assertion.describe()}\n    -> no {noun} named {assertion.detail!r} is defined"

    function, _, parameter = assertion.detail.partition(":")
    params = _parameters(tree, function)
    if params is None:
        return f"{assertion.describe()}\n    -> no function named {function!r} is defined"
    if parameter not in params:
        listed = ", ".join(sorted(params)) or "(none)"
        return (
            f"{assertion.describe()}\n"
            f"    -> {function!r} has no parameter {parameter!r}; it accepts: {listed}"
        )
    return None


def main() -> int:
    """Entry point. Returns 1 if any commitment did not land."""
    try:
        assertions = collect()
    except MalformedCommitmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "\nA commitment block that cannot be parsed is not checked, and an "
            "unchecked commitment is how v1.2 shipped without its context budget.",
            file=sys.stderr,
        )
        return 1

    if not assertions:
        print("ok: no cairntir-commitments blocks declared.")
        return 0

    failures = [message for a in assertions if (message := check(a)) is not None]

    docs = {a.source for a in assertions}
    print(f"checked {len(assertions)} commitment(s) across {len(docs)} document(s)")

    if failures:
        print(file=sys.stderr)
        for message in failures:
            print(f"UNLANDED: {message}", file=sys.stderr)
        print(
            f"\n{len(failures)} commitment(s) are declared in a plan but absent from "
            "the code.\nCairntir policy: a plan that promises something is a claim, "
            "and a claim nobody checks is how the same regression gets rediscovered "
            "a fourth time.",
            file=sys.stderr,
        )
        return 1

    print("ok: every declared commitment landed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
