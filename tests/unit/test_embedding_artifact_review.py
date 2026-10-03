"""Run frozen independent E22 review controls in normal repository CI."""

import importlib.util
from pathlib import Path

PACKET = Path(__file__).resolve().parents[2] / "plans/acceptance/embedding-artifacts-1.14/review"
SPEC = importlib.util.spec_from_file_location(
    "cairntir_frozen_e22_review", PACKET / "test_e22_review.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
test_frozen_e22_review = MODULE.test_frozen_e22_review
