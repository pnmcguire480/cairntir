"""The gate that guards Cairntir's oldest governance principle, finally tested.

``scripts/check_no_silent_except.py`` shipped in v0.1.0 and was the only gate
script in the repository with no test of its own. That is exactly why it could
rot into a near-no-op unnoticed: three of its four regexes required ``pass`` on
the same line as ``except``, which ``ruff format`` never emits, and none of them
could see a *typed* handler swallowing on the next line. Two live violations sat
in ``src/cairntir/register.py`` while the script exited 0.

These tests pin the behaviour that matters: what counts as silent, what does
not, and that the tree it guards is actually clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_no_silent_except.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_no_silent_except", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(tmp_path: Path, source: str) -> list[tuple[int, str]]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return list(_load_script().check_file(target))


# ------------------------------------------------------------------ violations

SILENT_SOURCES = pytest.mark.parametrize(
    ("label", "source"),
    [
        # THE REGRESSION: a typed handler swallowing on the next line. This is
        # the form the pattern actually takes in formatted source, and the form
        # the old regex gate was completely blind to.
        ("typed multi-line", "try:\n    f()\nexcept OSError:\n    pass\n"),
        ("bare", "try:\n    f()\nexcept:\n    pass\n"),
        ("broad", "try:\n    f()\nexcept Exception:\n    pass\n"),
        ("base", "try:\n    f()\nexcept BaseException:\n    pass\n"),
        ("aliased", "try:\n    f()\nexcept OSError as exc:\n    pass\n"),
        ("ellipsis body", "try:\n    f()\nexcept ValueError:\n    ...\n"),
        ("tuple of types", "try:\n    f()\nexcept (OSError, ValueError):\n    pass\n"),
        ("dotted type", "try:\n    f()\nexcept json.JSONDecodeError:\n    pass\n"),
        (
            "all-noop body",
            "try:\n    f()\nexcept OSError:\n    pass\n    ...\n",
        ),
        (
            "nested inside a function",
            "def outer():\n    try:\n        f()\n    except KeyError:\n        pass\n",
        ),
        (
            "silent handler beside a surfacing one",
            "try:\n    f()\nexcept OSError:\n    raise\nexcept ValueError:\n    pass\n",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else "",
)


@SILENT_SOURCES
def test_silent_handlers_are_rejected(label: str, source: str, tmp_path: Path) -> None:
    violations = _check(tmp_path, source)
    assert violations, f"{label}: silent handler slipped through"


def test_the_exact_regression_that_shipped(tmp_path: Path) -> None:
    """``register.py``'s live violation, verbatim, must now be caught."""
    source = (
        "def ensure() -> str:\n"
        "    try:\n"
        '        checkpoint.write_text("ok\\n", encoding="utf-8")\n'
        "    except OSError:\n"
        "        pass\n"
        '    return "present"\n'
    )
    violations = _check(tmp_path, source)
    assert [(lineno, clause) for lineno, clause in violations] == [(4, "except OSError:")]


def test_violation_reports_the_handler_line_and_clause(tmp_path: Path) -> None:
    violations = _check(tmp_path, "x = 1\ntry:\n    f()\nexcept OSError as exc:\n    pass\n")
    assert violations == [(4, "except OSError as exc:")]


# --------------------------------------------------------------- non-violations

SURFACING_SOURCES = pytest.mark.parametrize(
    ("label", "source"),
    [
        ("re-raises", "try:\n    f()\nexcept OSError:\n    raise\n"),
        (
            "raises typed",
            "try:\n    f()\nexcept OSError as exc:\n    raise StoreError(exc) from exc\n",
        ),
        # The store's write guard: the exception becomes a value. Converting a
        # failure into an answer is surfacing it, not hiding it.
        ("returns a value", "try:\n    f()\nexcept ValueError:\n    return False\n"),
        ("logs", "try:\n    f()\nexcept OSError as exc:\n    print(exc)\n"),
        (
            "continues a loop",
            "for x in y:\n    try:\n        f()\n    except OSError:\n        continue\n",
        ),
        (
            "records then falls through",
            "try:\n    f()\nexcept OSError as exc:\n    failures.append(exc)\n",
        ),
        ("no handler at all", "try:\n    f()\nfinally:\n    g()\n"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else "",
)


@SURFACING_SOURCES
def test_surfacing_handlers_are_allowed(label: str, source: str, tmp_path: Path) -> None:
    assert not _check(tmp_path, source), f"{label}: false positive"


# ------------------------------------------------------- unreadable is not clean


def test_unparseable_file_is_a_violation_not_a_skip(tmp_path: Path) -> None:
    """A file the gate cannot inspect is one it cannot vouch for."""
    violations = _check(tmp_path, "def broken(:\n")
    assert violations
    assert "could not parse" in violations[0][1]


# ------------------------------------------------------------- the live tree


def test_src_tree_has_no_silent_handlers() -> None:
    result = subprocess.run(  # noqa: S603 - argv is sys.executable plus a literal path
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
