"""Ban silent exception handling in src/.

Cairntir's governance principle: every exception is typed, logged, and surfaced.
Silent `except: pass` blocks are what made BrainStormer's 224-exception problem.
We do not repeat that mistake.

Why this is an AST check and not a regex
----------------------------------------

It used to be four regexes. Three of them required ``pass`` on the *same line*
as ``except`` -- a one-liner that ``ruff format`` never produces, so they could
not fire on this repository's own formatted source. The fourth caught only a
bare ``except:``, which ruff's E722 already rejects. The net effect: the gate
guarding Cairntir's oldest governance principle was close to a no-op, and it
was blind to the form the pattern actually takes --

    except OSError:
        pass

-- a *typed* handler whose body swallows. Two of those were live in
``src/cairntir/register.py`` while this script exited 0. That is the house
anti-pattern exactly: a check that advertises protection it does not provide.

The rule now has no type list to keep up to date. A handler is silent when its
body does nothing at all -- only ``pass`` and/or ``...`` -- whatever it catches.
Anything that logs, warns, re-raises, returns a distinguishable value, or
records the failure is fine; the principle is that the exception must *surface*,
not that it must be fatal.

Exit code 1 if any violations are found. Used as a pre-commit hook and CI check.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _is_noop(statement: ast.stmt) -> bool:
    """True for the two statements that do nothing: ``pass`` and ``...``."""
    if isinstance(statement, ast.Pass):
        return True
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    )


def _handler_label(handler: ast.ExceptHandler) -> str:
    """Render the handler's ``except`` clause the way it reads in source."""
    if handler.type is None:
        return "except:"
    caught = ast.unparse(handler.type)
    if handler.name:
        return f"except {caught} as {handler.name}:"
    return f"except {caught}:"


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, clause) for any silent-except violations.

    A read or parse failure is a violation of its own rather than a skip: a
    file this script cannot inspect is a file it cannot vouch for, and
    returning "clean" for it is the same lie the regexes told.
    """
    violations: list[tuple[int, str]] = []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append((0, f"could not read file: {exc}"))
        return violations

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        violations.append((exc.lineno or 0, f"could not parse file: {exc.msg}"))
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if all(_is_noop(statement) for statement in node.body):
            violations.append((node.lineno, _handler_label(node)))
    return violations


def main() -> int:
    """Entry point. Returns 1 if violations exist."""
    src_root = Path(__file__).resolve().parent.parent / "src"
    if not src_root.exists():
        return 0

    total_violations = 0
    for py_file in sorted(src_root.rglob("*.py")):
        violations = check_file(py_file)
        for lineno, clause in violations:
            rel = py_file.relative_to(src_root.parent)
            print(f"{rel}:{lineno}: silent except forbidden: {clause}")
            total_violations += 1

    if total_violations:
        print(f"\n{total_violations} silent except violation(s) found.", file=sys.stderr)
        print(
            "Cairntir policy: every exception must be typed, logged, and surfaced.",
            file=sys.stderr,
        )
        return 1
    print("ok: no silent exception handlers in src/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
