"""Fail the build when a declared seam has no test proving both sides agree.

``scripts/check_landed_commitments.py`` verifies that things we said we would
build got built. This closes a different hole, found the hard way on
2026-08-05: **every component passing its own tests while the system as a
whole is wrong.** ``CairntirBackend.settle`` and ``is_open_prediction`` were
both green — each correct by its own contract — and together they meant every
prediction settled through the only sanctioned path stayed listed as open
forever. The missing guard was not another unit test; it was a test that
could see both sides at once.

The law this registry enforces:

    When two components must agree, either make them share the code that
    defines the agreement, or test them together in one test. Never only
    separately.

The codebase already applied that law by instinct twice — the anchor nudge
reuses ``extract_path_candidates`` from the backfiller, and the write guard
deliberately enforces the same line as ``check_store_health.py`` rule 3. This
script makes the rule a ratchet instead of an instinct.

Each entry in ``SEAMS`` names the components on both sides — file plus
symbol, or the file alone when one side is a script with no importable
function — and the paired test that exercises them together. The check
verifies that every declared side still exists and that the paired test still
exists. A declared seam whose test has vanished fails the build, because an
untested agreement is how the settlement seam shipped.

The ``TOOL_SURFACE_VERSION`` entry is deliberately first: that seam was
already fixed on 2026-08-04, and it is the precedent the rest of the
registry copies — a hand-maintained constant pinned to the thing it
describes by a test, instead of by convention.

Exit code 1 when any seam is unguarded. Wired into the CI lint job.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Side:
    """One component of a seam: a file, and optionally a symbol inside it.

    ``symbol`` is None when the side has no importable function to point at
    — a loose script whose agreement lives inline, for instance. The file's
    existence is then the whole assertion for that side.
    """

    path: Path
    symbol: str | None = None


@dataclass(frozen=True)
class Seam:
    """Two sides that must agree, and the one test that proves it."""

    name: str
    sides: tuple[Side, ...]
    test_path: Path
    test_name: str


SEAMS: tuple[Seam, ...] = (
    Seam(
        name="TOOL_SURFACE_VERSION tracks the tool list",
        sides=(
            Side(Path("src/cairntir/provenance.py"), "TOOL_SURFACE_VERSION"),
            Side(Path("src/cairntir/mcp/server.py")),
        ),
        test_path=Path("tests/unit/test_readme.py"),
        test_name="test_tool_surface_version_matches_the_server",
    ),
    Seam(
        name="settle writes settlements the way handoff reads them",
        sides=(
            Side(Path("src/cairntir/mcp/backend.py"), "settle"),
            Side(Path("src/cairntir/handoff.py"), "is_open_prediction"),
            Side(Path("src/cairntir/handoff.py"), "settled_prediction_ids"),
        ),
        test_path=Path("tests/integration/test_seams.py"),
        test_name="test_settling_a_prediction_closes_it_in_handoff",
    ),
    Seam(
        name="the write guard and store-health rule 3 draw the same line",
        sides=(
            Side(Path("src/cairntir/memory/store.py"), "_guard_write_integrity"),
            Side(Path("scripts/check_store_health.py")),
        ),
        test_path=Path("tests/integration/test_seams.py"),
        test_name="test_write_guard_and_store_health_enforce_the_same_line",
    ),
    Seam(
        name="anchors validated on write are the anchors read back",
        sides=(
            Side(Path("src/cairntir/memory/anchors.py"), "parse_anchors"),
            Side(Path("src/cairntir/memory/anchors.py"), "recall_for_change"),
        ),
        test_path=Path("tests/integration/test_seams.py"),
        test_name="test_anchors_accepted_on_write_are_reachable_on_read",
    ),
    Seam(
        name="vault-sync --check and apply_sync agree about drift",
        sides=(
            Side(Path("src/cairntir/vault.py"), "plan_sync"),
            Side(Path("src/cairntir/vault.py"), "apply_sync"),
        ),
        test_path=Path("tests/integration/test_seams.py"),
        test_name="test_vault_check_and_apply_agree_about_drift",
    ),
    # Found 2026-08-10 by reproducing a stranger's first two days on a
    # clean PyPI install. The tool defaulted writes to on_demand; the
    # composer gathered only IDENTITY and ESSENTIAL. Both sides green,
    # both sides tested, and between them the documented happy path
    # returned an empty brief over memory that was sitting right there.
    #
    # This one earns a permanent guard more than any other seam here,
    # because the old behaviour was not merely untested — it was
    # *asserted* by a unit test that reasoned from the layer taxonomy
    # that dropping the default write layer was correct. Anyone can
    # re-derive that argument. The seam test reads the declared default
    # off the live schema so the argument has to survive contact with
    # both sides at once.
    Seam(
        name="the default write layer is a layer handoff loads",
        sides=(
            Side(Path("src/cairntir/mcp/server.py"), "_tool_specs"),
            Side(Path("src/cairntir/handoff.py"), "_gather"),
            Side(Path("src/cairntir/handoff.py"), "RECENT_ACTIVITY"),
        ),
        test_path=Path("tests/unit/test_handoff.py"),
        test_name="test_the_default_write_layer_is_a_layer_handoff_loads",
    ),
    # Found 2026-08-10, same day and same shape as the seam above.
    # cost.py hardcoded a 512-token window, all-MiniLM-L6-v2 actually
    # truncated at 128, and fastembed's own description advertised 256.
    # Three numbers, no two agreeing, and the one the tool reported was
    # the most flattering — so a module built to measure this exact risk
    # under-reported it fourfold while 73.4% of the corpus sat invisible
    # to semantic recall.
    #
    # The guard has to read the live tokenizer, because every other
    # source of this number has already been wrong once.
    Seam(
        name="the declared embedder window matches the real model",
        sides=(
            Side(Path("src/cairntir/memory/embeddings.py"), "PRODUCTION_TOKEN_WINDOW"),
            Side(Path("src/cairntir/cost.py"), "EMBEDDER_TOKEN_LIMIT"),
        ),
        test_path=Path("tests/eval/test_embedder_window.py"),
        test_name="test_declared_embedder_window_matches_the_model",
    ),
)


def _defined_names(tree: ast.AST) -> set[str]:
    """Names defined at any nesting depth: functions, classes, assignments."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def check(seam: Seam) -> list[str]:
    """Verify one seam. Returns failure messages; empty means guarded."""
    failures: list[str] = []
    for side in seam.sides:
        if not side.path.exists():
            failures.append(f"{side.path.as_posix()} does not exist")
            continue
        if side.symbol is None:
            continue
        tree = ast.parse(side.path.read_text(encoding="utf-8"))
        if side.symbol not in _defined_names(tree):
            failures.append(f"{side.path.as_posix()} defines no {side.symbol!r}")

    if not seam.test_path.exists():
        failures.append(f"paired test file {seam.test_path.as_posix()} does not exist")
    else:
        tree = ast.parse(seam.test_path.read_text(encoding="utf-8"))
        if seam.test_name not in _defined_names(tree):
            failures.append(f"{seam.test_path.as_posix()} defines no test named {seam.test_name!r}")
    return failures


def main() -> int:
    """Entry point. Returns 1 if any declared seam is unguarded."""
    unguarded = 0
    for seam in SEAMS:
        failures = check(seam)
        if not failures:
            print(f"ok: seam guarded — {seam.name}")
            continue
        unguarded += 1
        print(f"UNGUARDED SEAM: {seam.name}", file=sys.stderr)
        for message in failures:
            print(f"    -> {message}", file=sys.stderr)

    print(f"checked {len(SEAMS)} declared seam(s)")
    if unguarded:
        print(
            f"\n{unguarded} seam(s) have no test proving both sides agree. "
            "Separate green tests are how the settlement seam shipped: "
            "settle and is_open_prediction each passed while a settled "
            "prediction stayed open forever.",
            file=sys.stderr,
        )
        return 1
    print("ok: every declared seam has a test exercising both sides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
