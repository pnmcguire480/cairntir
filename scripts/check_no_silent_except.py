"""Ban silent exception handling in src/.

Cairntir's governance principle: every exception is typed, logged, and surfaced.
Silent `except: pass` blocks are what made BrainStormer's 224-exception problem.
We do not repeat that mistake.

Exit code 1 if any violations are found. Used as a pre-commit hook and CI check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SILENT_EXCEPT_PATTERNS = [
    re.compile(r"^\s*except\s*:\s*$", re.MULTILINE),
    re.compile(r"^\s*except\s*:\s*pass\s*$", re.MULTILINE),
    re.compile(r"^\s*except\s+Exception\s*:\s*pass\s*$", re.MULTILINE),
    re.compile(r"^\s*except\s+BaseException\s*:\s*pass\s*$", re.MULTILINE),
]


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, line) for any silent-except violations."""
    violations: list[tuple[int, str]] = []
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"WARN: could not read {path}: {exc}", file=sys.stderr)
        return violations

    for lineno, line in enumerate(content.splitlines(), start=1):
        for pattern in SILENT_EXCEPT_PATTERNS:
            if pattern.match(line):
                violations.append((lineno, line.rstrip()))
                break
    return violations


def main() -> int:
    """Entry point. Returns 1 if violations exist."""
    src_root = Path(__file__).resolve().parent.parent / "src"
    if not src_root.exists():
        return 0

    total_violations = 0
    for py_file in src_root.rglob("*.py"):
        violations = check_file(py_file)
        if violations:
            for lineno, line in violations:
                rel = py_file.relative_to(src_root.parent)
                print(f"{rel}:{lineno}: silent except forbidden: {line}")
                total_violations += 1

    if total_violations:
        print(f"\n{total_violations} silent except violation(s) found.", file=sys.stderr)
        print(
            "Cairntir policy: every exception must be typed, logged, and surfaced.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
