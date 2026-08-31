"""Immutable finish-line contracts with independent acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class FinalizationError(ValueError):
    """The finalization contract or transition is invalid."""

    pass


class EvidenceMutationError(FinalizationError):
    """A frozen acceptance artifact changed after coder dispatch."""

    pass


class TestOutcome(StrEnum):
    """Independent tester outcomes."""

    __test__ = False
    PASS = "PASS"  # noqa: S105
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class Disposition(StrEnum):
    """Terminal roadmap dispositions."""

    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    EXHAUSTED = "EXHAUSTED"


def _items(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise FinalizationError(f"{label} must be a sequence")
    result = tuple(values)
    if not result or any(not isinstance(value, str) or not value.strip() for value in result):
        raise FinalizationError(f"{label} must contain non-empty strings")
    return result


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _path(value: str) -> str:
    result = value.replace("\\", "/").strip("/")
    invalid_part = any(part in {".", ".."} for part in result.split("/"))
    if not result or result in {".", ".."} or invalid_part:
        raise FinalizationError("artifact and write paths must be normalized relative paths")
    return result


def _overlap(left: str, right: str) -> bool:
    left_key = left.casefold()
    right_key = right.casefold()
    return (
        left_key == right_key
        or left_key.startswith(right_key + "/")
        or right_key.startswith(left_key + "/")
    )


@dataclass(frozen=True)
class FinalizationContract:
    """Hash-bound roadmap finish line frozen before implementation."""

    roadmap_modes: tuple[str, ...]
    thesis: str
    issue: str
    acceptance_criteria: tuple[str, ...]
    test_parameters: tuple[str, ...]
    non_goals: tuple[str, ...]
    verification_reserve: int
    max_repair_rounds: int
    gate_kind: str
    contract_sha256: str

    @classmethod
    def freeze(
        cls,
        *,
        roadmap_modes: Iterable[str],
        thesis: str,
        issue: str,
        acceptance_criteria: Iterable[str],
        test_parameters: Iterable[str],
        non_goals: Iterable[str],
        verification_reserve: int,
        max_repair_rounds: int,
        gate_kind: str,
    ) -> FinalizationContract:
        """Copy, validate, and bind a roadmap finalization contract."""
        modes = _items(roadmap_modes, "roadmap modes")
        if modes[-1].casefold() != "finalization":
            raise FinalizationError("finalization must be the last roadmap mode")
        if not thesis.strip() or not issue.strip():
            raise FinalizationError("thesis and issue are required")
        if type(verification_reserve) is not int or verification_reserve < 1:
            raise FinalizationError("verification reserve must be positive")
        if type(max_repair_rounds) is not int or not 1 <= max_repair_rounds <= 2:
            raise FinalizationError("repair rounds must be between one and two")
        if gate_kind not in {"offline", "protected", "billed"}:
            raise FinalizationError("gate kind must be offline, protected, or billed")
        if gate_kind != "offline" and max_repair_rounds != 1:
            raise FinalizationError("protected or billed gates permit one repair round")
        criteria = _items(acceptance_criteria, "acceptance criteria")
        parameters = _items(test_parameters, "test parameters")
        excluded = _items(non_goals, "non-goals")
        payload = {
            "roadmap_modes": modes,
            "thesis": thesis,
            "issue": issue,
            "acceptance_criteria": criteria,
            "test_parameters": parameters,
            "non_goals": excluded,
            "verification_reserve": verification_reserve,
            "max_repair_rounds": max_repair_rounds,
            "gate_kind": gate_kind,
        }
        digest = _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        return cls(
            modes,
            thesis,
            issue,
            criteria,
            parameters,
            excluded,
            verification_reserve,
            max_repair_rounds,
            gate_kind,
            digest,
        )


@dataclass(frozen=True, order=True)
class TestArtifact:
    """Path and digest of one independently authored acceptance artifact."""

    path: str
    sha256: str

    @classmethod
    def bind(cls, path: str, content: bytes) -> TestArtifact:
        """Bind an artifact path to its exact bytes."""
        if not isinstance(content, bytes):
            raise FinalizationError("test artifact content must be bytes")
        return cls(_path(path), _sha256(content))


@dataclass(frozen=True)
class AcceptanceEvidence:
    """Frozen tester identity and acceptance-artifact inventory."""

    tester_id: str
    artifacts: tuple[TestArtifact, ...]

    @classmethod
    def freeze(cls, *, tester_id: str, artifacts: Mapping[str, bytes]) -> AcceptanceEvidence:
        """Copy and hash the independent test inventory."""
        if not tester_id.strip():
            raise FinalizationError("tester identity is required")
        bound = tuple(
            sorted(TestArtifact.bind(path, content) for path, content in artifacts.items())
        )
        if not bound:
            raise FinalizationError("at least one test artifact is required")
        return cls(tester_id, bound)

    @property
    def artifact_hashes(self) -> tuple[tuple[str, str], ...]:
        """Return the immutable path-to-digest inventory."""
        return tuple((artifact.path, artifact.sha256) for artifact in self.artifacts)

    def verify(self, artifacts: Mapping[str, bytes]) -> None:
        """Reject any change to the frozen acceptance artifacts."""
        current = tuple(
            sorted(TestArtifact.bind(path, content) for path, content in artifacts.items())
        )
        if current != self.artifacts:
            raise EvidenceMutationError("test artifact hash mutation detected")


@dataclass(frozen=True)
class CoderDispatch:
    """Bounded information and write authority given to the coder."""

    thesis: str
    issue: str
    acceptance_criteria: tuple[str, ...]
    test_parameters: tuple[str, ...]
    test_artifact_hashes: tuple[tuple[str, str], ...]
    failure_evidence: tuple[str, ...]
    write_paths: tuple[str, ...]


@dataclass
class FinalizationRun:
    """Runtime-owned finalization state and repair budget."""

    contract: FinalizationContract
    evidence: AcceptanceEvidence
    coder_id: str
    implementation_paths: tuple[str, ...]
    repair_rounds_used: int = 0
    invalidated: bool = False
    disposition: Disposition = Disposition.BLOCKED
    last_outcome: TestOutcome | None = None
    _state_hashes: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def start(
        cls,
        *,
        contract: FinalizationContract,
        evidence: AcceptanceEvidence,
        coder_id: str,
        implementation_paths: Iterable[str],
    ) -> FinalizationRun:
        """Start a run only when tester identity and artifacts are independent."""
        if not coder_id.strip() or coder_id == evidence.tester_id:
            raise FinalizationError("coder and tester identities must be distinct")
        write_paths = tuple(_path(path) for path in implementation_paths)
        if not write_paths:
            raise FinalizationError("coder write scope is required")
        overlaps = any(
            _overlap(write_path, artifact.path)
            for write_path in write_paths
            for artifact in evidence.artifacts
        )
        if overlaps:
            raise FinalizationError("test artifacts must be outside coder write scope")
        return cls(contract, evidence, coder_id, write_paths)

    def coder_dispatch(self, *, failure_evidence: Iterable[str] = ()) -> CoderDispatch:
        """Expose the frozen contract and only the coder-owned write paths."""
        failures = tuple(failure_evidence)
        return CoderDispatch(
            self.contract.thesis,
            self.contract.issue,
            self.contract.acceptance_criteria,
            self.contract.test_parameters,
            self.evidence.artifact_hashes,
            failures,
            self.implementation_paths,
        )

    def authorize_repair(self, *, coder_id: str) -> None:
        """Consume one bounded implementation repair round."""
        if coder_id != self.coder_id:
            raise FinalizationError("only the assigned coder may repair implementation")
        if self.invalidated:
            raise FinalizationError("invalidated run cannot authorize repair")
        if self.repair_rounds_used >= self.contract.max_repair_rounds:
            self.disposition = Disposition.EXHAUSTED
            raise FinalizationError("repair budget exhausted")
        self.repair_rounds_used += 1

    def record_result(
        self,
        *,
        outcome: TestOutcome,
        tester_id: str,
        artifacts: Mapping[str, bytes],
        relevant_state_sha256: str,
        classification: str | None = None,
    ) -> None:
        """Accept only unchanged artifacts submitted by the independent tester."""
        if tester_id != self.evidence.tester_id:
            raise FinalizationError("only the independent tester may submit evidence")
        if classification not in {None, "transient", "flaky"}:
            raise FinalizationError("classification must be transient or flaky")
        invalid_hash = len(relevant_state_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in relevant_state_sha256
        )
        if invalid_hash:
            raise FinalizationError("relevant state must be a lowercase SHA-256")
        try:
            self.evidence.verify(artifacts)
        except EvidenceMutationError:
            self.invalidated = True
            self.disposition = Disposition.BLOCKED
            raise
        if relevant_state_sha256 in self._state_hashes and classification is None:
            raise FinalizationError("identical rerun against identical state is forbidden")
        self._state_hashes.append(relevant_state_sha256)
        self.last_outcome = outcome
        if outcome is TestOutcome.PASS:
            self.disposition = Disposition.COMPLETE
        elif self.repair_rounds_used >= self.contract.max_repair_rounds:
            self.disposition = Disposition.EXHAUSTED
        else:
            self.disposition = Disposition.BLOCKED


__all__ = [
    "AcceptanceEvidence",
    "CoderDispatch",
    "Disposition",
    "EvidenceMutationError",
    "FinalizationContract",
    "FinalizationError",
    "FinalizationRun",
    "TestArtifact",
    "TestOutcome",
]
