"""Turn a Crucible falsifiable claim into an executed, independently authored test.

Crucible makes a claim falsifiable: a drawer carries ``claim`` and
``predicted_outcome``. This module carries that claim to a separate test
author and executes what comes back. The flow has four steps, each a plain
directory operation so any host or person can act as the author:

1. ``export_packet`` writes a packet holding the claim, the prediction and
   the interface name the subject must provide. It never holds subject
   source or candidate answers, so the author's assertions cannot be copied
   from the thing under test.
2. A separate author writes stdlib ``unittest`` files under ``tests/``.
3. ``freeze_tests`` binds those files by SHA-256 under an author identity
   that must differ from the claimant's.
4. ``run_claim_tests`` re-verifies the frozen bytes, executes exactly those
   bytes in an isolated interpreter against a subject directory, and reports
   ``FALSIFIED``, ``HELD``, ``NOT_EXECUTED`` or ``INCONCLUSIVE``.

``qualify_claim_tests`` closes the loop: the tests count as an independent
oracle only when a known-bad subject is falsified and the corrected subject
holds. A test that passes against known-bad behavior proves nothing.

Prompt text alone is never an executed test: a packet with no test file, or
whose cases are all skipped or never collected, is ``NOT_EXECUTED``.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cairntir.errors import CairntirError
from cairntir.finalization import (
    AcceptanceEvidence,
    EvidenceMutationError,
    FinalizationError,
    TestArtifact,
)

if TYPE_CHECKING:
    from cairntir.memory.taxonomy import Drawer

PACKET_SCHEMA = "cairntir.claim-test-packet/1"
FREEZE_SCHEMA = "cairntir.claim-test-freeze/1"
RUN_SCHEMA = "cairntir.claim-test-run/1"
QUALIFY_SCHEMA = "cairntir.claim-test-qualify/1"

CLAIM_FILE = "CLAIM.json"
AUTHOR_FILE = "AUTHOR.md"
FREEZE_FILE = "FROZEN.json"
RUNS_FILE = "RUNS.jsonl"
TESTS_DIR = "tests"

DEFAULT_TIMEOUT_SECONDS = 120.0
_INTERFACE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_OUTPUT_LIMIT = 4000


class ClaimTestError(CairntirError):
    """A claim packet, its frozen tests, or a run request is invalid."""


class Verdict(StrEnum):
    """What executing the frozen tests against one subject showed."""

    HELD = "HELD"
    FALSIFIED = "FALSIFIED"
    NOT_EXECUTED = "NOT_EXECUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class RunResult:
    """One execution of frozen claim tests against one subject directory."""

    verdict: Verdict
    reason: str
    subject: str
    tests_run: int
    failures: int
    errors: int
    skipped: int
    artifacts: tuple[tuple[str, str], ...]
    claim_sha256: str
    command: tuple[str, ...]
    output: str = ""
    cases: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready receipt."""
        data = asdict(self)
        data["schema"] = RUN_SCHEMA
        data["verdict"] = self.verdict.value
        data["artifacts"] = [list(item) for item in self.artifacts]
        data["command"] = list(self.command)
        data["cases"] = list(self.cases)
        return data


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimTestError(f"{label} is required")
    return value.strip()


def _same_identity(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def _author_brief(claim: str, predicted: str, interface: str) -> str:
    return f"""# Claim test packet

You are the independent test author for one falsifiable claim. You have not
seen the subject's source and must not ask for it.

## Claim

{claim}

## Predicted outcome (what must be observed if the claim is true)

{predicted}

## Interface

The subject is importable as `{interface}`.

## What to write

- One or more files named `tests/test_*.py`, using only the Python standard
  library `unittest` module.
- Each test must fail if the predicted outcome does not hold.
- Derive every expected value from the claim and prediction above. Never
  compute an expected value by calling the subject, and never compare the
  subject's answer with itself.
- Do not skip tests and do not use `expectedFailure`.

When you are done, the claimant freezes your files with
`cairntir claim-test freeze PACKET --author YOUR_ID`. Your identity must differ
from the claimant's.
"""


def export_packet(
    packet_dir: Path,
    *,
    claim: str,
    predicted_outcome: str,
    interface: str,
    claimant_id: str,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a new test-author packet for one falsifiable claim.

    The packet directory must not exist yet or must be empty, so an old
    packet's tests can never be reused for a different claim.
    """
    claim_text = _required_text(claim, "claim")
    predicted = _required_text(predicted_outcome, "predicted outcome")
    claimant = _required_text(claimant_id, "claimant identity")
    if not isinstance(interface, str) or not _INTERFACE_RE.match(interface):
        raise ClaimTestError("interface must be a dotted Python module name")
    if packet_dir.exists() and (not packet_dir.is_dir() or any(packet_dir.iterdir())):
        raise ClaimTestError(f"packet directory must be new or empty: {packet_dir}")
    record: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "claim": claim_text,
        "predicted_outcome": predicted,
        "interface": interface,
        "claimant_id": claimant,
        "source": dict(source or {}),
        "created_at": datetime.now(UTC).isoformat(),
    }
    (packet_dir / TESTS_DIR).mkdir(parents=True, exist_ok=True)
    (packet_dir / CLAIM_FILE).write_bytes(_canonical(record) + b"\n")
    (packet_dir / AUTHOR_FILE).write_text(
        _author_brief(claim_text, predicted, interface), encoding="utf-8"
    )
    return {**record, "packet": str(packet_dir), "claim_sha256": _claim_sha(packet_dir)}


def export_drawer_packet(
    packet_dir: Path,
    drawer: Drawer | None,
    *,
    interface: str,
    claimant_id: str,
) -> dict[str, Any]:
    """Export a stored Crucible claim; refuse drawers that are not falsifiable."""
    if drawer is None or drawer.id is None:
        raise ClaimTestError("drawer not found")
    if not (drawer.claim or "").strip():
        raise ClaimTestError(f"drawer {drawer.id} has no claim")
    if not (drawer.predicted_outcome or "").strip():
        raise ClaimTestError(
            f"drawer {drawer.id} has no predicted outcome, so its claim is not falsifiable"
        )
    return export_packet(
        packet_dir,
        claim=drawer.claim or "",
        predicted_outcome=drawer.predicted_outcome or "",
        interface=interface,
        claimant_id=claimant_id,
        source={
            "drawer_id": drawer.id,
            "wing": drawer.wing,
            "room": drawer.room,
            "content_sha256": _sha256(drawer.content.encode("utf-8")),
        },
    )


def _claim_sha(packet_dir: Path) -> str:
    try:
        return _sha256((packet_dir / CLAIM_FILE).read_bytes())
    except OSError as exc:
        raise ClaimTestError(f"packet has no readable {CLAIM_FILE}: {exc}") from exc


def _read_claim(packet_dir: Path) -> dict[str, Any]:
    path = packet_dir / CLAIM_FILE
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClaimTestError(f"packet has no readable {CLAIM_FILE}: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != PACKET_SCHEMA:
        raise ClaimTestError(f"{CLAIM_FILE} is not a {PACKET_SCHEMA} record")
    for key in ("claim", "predicted_outcome", "interface", "claimant_id"):
        _required_text(record.get(key), key)
    return record


def _test_files(packet_dir: Path) -> dict[str, bytes]:
    tests = packet_dir / TESTS_DIR
    if not tests.is_dir():
        return {}
    found: dict[str, bytes] = {}
    for path in sorted(tests.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise ClaimTestError(f"test files must be regular files: {path}")
        found[path.relative_to(packet_dir).as_posix()] = path.read_bytes()
    return found


def freeze_tests(packet_dir: Path, *, author_id: str) -> dict[str, Any]:
    """Bind the author's test files and the claim they answer by SHA-256."""
    record = _read_claim(packet_dir)
    author = _required_text(author_id, "author identity")
    if _same_identity(author, record["claimant_id"]):
        raise ClaimTestError("the test author must not be the claimant")
    if (packet_dir / FREEZE_FILE).exists():
        raise ClaimTestError("tests are already frozen; export a new packet to change them")
    files = _test_files(packet_dir)
    if not files:
        raise ClaimTestError("there are no test files to freeze")
    try:
        evidence = AcceptanceEvidence.freeze(tester_id=author, artifacts=files)
    except FinalizationError as exc:
        raise ClaimTestError(str(exc)) from exc
    frozen: dict[str, Any] = {
        "schema": FREEZE_SCHEMA,
        "author_id": author,
        "claimant_id": record["claimant_id"],
        "claim_sha256": _claim_sha(packet_dir),
        "artifacts": [list(item) for item in evidence.artifact_hashes],
        "frozen_at": datetime.now(UTC).isoformat(),
    }
    (packet_dir / FREEZE_FILE).write_bytes(_canonical(frozen) + b"\n")
    return frozen


def _load_frozen(packet_dir: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    path = packet_dir / FREEZE_FILE
    try:
        frozen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClaimTestError(f"tests are not frozen: {exc}") from exc
    if not isinstance(frozen, dict) or frozen.get("schema") != FREEZE_SCHEMA:
        raise ClaimTestError(f"{FREEZE_FILE} is not a {FREEZE_SCHEMA} record")
    if frozen.get("claim_sha256") != _claim_sha(packet_dir):
        raise ClaimTestError("the claim changed after its tests were frozen")
    artifacts = frozen.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ClaimTestError(f"{FREEZE_FILE} lists no artifacts")
    try:
        bound = tuple(sorted(TestArtifact(str(path), str(sha)) for path, sha in artifacts))
    except (TypeError, ValueError) as exc:
        raise ClaimTestError(f"{FREEZE_FILE} has malformed artifacts") from exc
    evidence = AcceptanceEvidence(str(frozen.get("author_id", "")), bound)
    files = _test_files(packet_dir)
    try:
        evidence.verify(files)
    except EvidenceMutationError as exc:
        raise ClaimTestError(
            "frozen test files changed after freezing; refusing to execute them"
        ) from exc
    return frozen, files


_WORKER = r"""
import json, sys, unittest
tests_dir, subject_dir, out_path = sys.argv[1:4]
sys.path[:0] = [subject_dir, tests_dir]
loader = unittest.TestLoader()
suite = loader.discover(tests_dir, pattern="test_*.py", top_level_dir=tests_dir)
result = unittest.TestResult()
suite.run(result)
def cases(items, outcome):
    return [{"id": test.id(), "outcome": outcome, "detail": str(detail)[-1500:]}
            for test, detail in items]
loader_errors = [str(error)[-1500:] for error in loader.errors]
payload = {
    "tests_run": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skipped": len(result.skipped),
    "expected_failures": len(result.expectedFailures),
    "unexpected_successes": len(result.unexpectedSuccesses),
    "loader_errors": loader_errors,
    "cases": cases(result.failures, "failure") + cases(result.errors, "error")
    + cases(result.skipped, "skipped"),
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
"""


def _count(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise ClaimTestError(f"worker report has an invalid {key} count")
    return value


def _verdict(payload: Mapping[str, Any]) -> tuple[Verdict, str]:
    run = _count(payload, "tests_run")
    failures = _count(payload, "failures")
    errors = _count(payload, "errors")
    skipped = _count(payload, "skipped")
    marked = _count(payload, "expected_failures") + _count(payload, "unexpected_successes")
    if failures:
        return Verdict.FALSIFIED, f"{failures} of {run} executed test(s) failed their assertion"
    if errors or payload.get("loader_errors"):
        return Verdict.INCONCLUSIVE, f"{errors} test(s) raised before reaching an assertion"
    if marked:
        return Verdict.INCONCLUSIVE, "expectedFailure markers hide the real outcome"
    if run - skipped <= 0:
        return Verdict.NOT_EXECUTED, "no test case executed; prompt text is not a test"
    if skipped:
        return Verdict.INCONCLUSIVE, f"{skipped} of {run} test(s) were skipped"
    return Verdict.HELD, f"all {run} executed test(s) passed"


def _tail(text: str) -> str:
    return text[-_OUTPUT_LIMIT:]


def _record(packet_dir: Path, result: RunResult) -> None:
    with (packet_dir / RUNS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.as_dict(), sort_keys=True, ensure_ascii=False) + "\n")


def run_claim_tests(
    packet_dir: Path,
    subject_dir: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RunResult:
    """Execute the frozen tests against one subject and append the receipt."""
    _read_claim(packet_dir)
    claim_sha = _claim_sha(packet_dir)
    if not subject_dir.is_dir():
        raise ClaimTestError(f"subject directory does not exist: {subject_dir}")
    if not (packet_dir / FREEZE_FILE).exists() and not _test_files(packet_dir):
        result = RunResult(
            Verdict.NOT_EXECUTED,
            "the packet holds no test file; prompt text is not a test",
            str(subject_dir),
            0,
            0,
            0,
            0,
            (),
            claim_sha,
            (),
        )
        _record(packet_dir, result)
        return result
    frozen, files = _load_frozen(packet_dir)
    artifacts = tuple((str(item[0]), str(item[1])) for item in frozen["artifacts"])
    with tempfile.TemporaryDirectory(prefix="cairntir-claim-") as scratch:
        root = Path(scratch)
        tests_root = root / TESTS_DIR
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if any(_sha256((root / rel).read_bytes()) != sha for rel, sha in artifacts):
            raise ClaimTestError("copied test bytes differ from the frozen hashes")
        report = root / "report.json"
        command = (
            sys.executable,
            "-I",
            "-c",
            _WORKER,
            str(tests_root),
            str(subject_dir.resolve()),
            str(report),
        )
        shown = (sys.executable, "-I", "-c", "<claim-test worker>", *command[4:])
        try:
            completed = subprocess.run(  # noqa: S603 - fixed interpreter and argument vector.
                command,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result = RunResult(
                Verdict.INCONCLUSIVE,
                f"tests did not finish within {timeout:g} seconds",
                str(subject_dir),
                0,
                0,
                0,
                0,
                artifacts,
                claim_sha,
                shown,
            )
            _record(packet_dir, result)
            return result
        output = _tail((completed.stdout or "") + (completed.stderr or ""))
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
    if not isinstance(payload, dict):
        result = RunResult(
            Verdict.INCONCLUSIVE,
            f"the test worker exited {completed.returncode} without a report",
            str(subject_dir),
            0,
            0,
            0,
            0,
            artifacts,
            claim_sha,
            shown,
            output,
        )
        _record(packet_dir, result)
        return result
    verdict, reason = _verdict(payload)
    raw_cases = payload.get("cases")
    cases = tuple(
        {str(key): str(value) for key, value in case.items()}
        for case in (raw_cases if isinstance(raw_cases, list) else [])
        if isinstance(case, dict)
    )
    result = RunResult(
        verdict,
        reason,
        str(subject_dir),
        _count(payload, "tests_run"),
        _count(payload, "failures"),
        _count(payload, "errors"),
        _count(payload, "skipped"),
        artifacts,
        claim_sha,
        shown,
        output,
        cases,
    )
    _record(packet_dir, result)
    return result


def qualify_claim_tests(
    packet_dir: Path,
    *,
    known_bad: Path,
    corrected: Path,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Accept the tests as an independent oracle only if bad fails and fixed passes."""
    bad = run_claim_tests(packet_dir, known_bad, timeout=timeout)
    good = run_claim_tests(packet_dir, corrected, timeout=timeout)
    reasons: list[str] = []
    if bad.verdict is not Verdict.FALSIFIED:
        reasons.append(
            f"known-bad subject was {bad.verdict.value}, not FALSIFIED: "
            "the tests do not detect the bad behavior"
        )
    if good.verdict is not Verdict.HELD:
        reasons.append(f"corrected subject was {good.verdict.value}, not HELD")
    if bad.artifacts != good.artifacts:
        reasons.append("the two runs executed different test bytes")
    return {
        "schema": QUALIFY_SCHEMA,
        "status": "NOT_QUALIFIED" if reasons else "QUALIFIED",
        "reasons": reasons,
        "known_bad": bad.as_dict(),
        "corrected": good.as_dict(),
    }


__all__ = [
    "ClaimTestError",
    "RunResult",
    "Verdict",
    "export_drawer_packet",
    "export_packet",
    "freeze_tests",
    "qualify_claim_tests",
    "run_claim_tests",
]
