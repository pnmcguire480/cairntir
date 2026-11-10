"""Exact versioned amendments retain historical evidence and reject unrelated drift."""

import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path("plans/acceptance/alpha-ci-contracts-20261029")
TARGET = "tests/unit/test_store.py"
BEFORE = "eecf66a7db47a02dc54f24bc0633840f45a1289d7f48c69b075383e9be23f053"
CHECK = runpy.run_path(str(ROOT / "scripts/check_verification_preservation.py"))[
    "_accepted_alpha_test_amendment"
]


@pytest.fixture
def amended_copy(tmp_path: Path) -> Path:
    for relative in (FOLDER / "AMENDMENT.json", FOLDER / "original" / TARGET, Path(TARGET)):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def test_exact_archived_contract_replacement_is_accepted(amended_copy: Path) -> None:
    assert CHECK(amended_copy, TARGET, BEFORE)


@pytest.mark.parametrize(
    "mutation",
    [
        "archive_missing",
        "archive_changed",
        "live_changed",
        "manifest_changed",
        "other_path",
        "other_baseline",
    ],
)
def test_amendment_rejects_missing_evidence_and_unrelated_drift(
    amended_copy: Path, mutation: str
) -> None:
    if mutation == "archive_missing":
        (amended_copy / FOLDER / "original" / TARGET).unlink()
    elif mutation in {"archive_changed", "live_changed", "manifest_changed"}:
        relative = {
            "archive_changed": FOLDER / "original" / TARGET,
            "live_changed": Path(TARGET),
            "manifest_changed": FOLDER / "AMENDMENT.json",
        }[mutation]
        path = amended_copy / relative
        path.write_bytes(path.read_bytes() + b"\n")
    target = "tests/unit/unrelated.py" if mutation == "other_path" else TARGET
    before = "0" * 64 if mutation == "other_baseline" else BEFORE
    assert not CHECK(amended_copy, target, before)
