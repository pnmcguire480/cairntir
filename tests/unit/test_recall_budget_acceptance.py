"""Run independently frozen complete-response recall acceptance."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ACCEPTANCE = Path(__file__).resolve().parents[2] / "plans/acceptance/recall-budget-1.13"
manifest = (ACCEPTANCE / "FROZEN-20261003.json").read_bytes()
assert hashlib.sha256(manifest).hexdigest() == (
    "6d923f4708c8c818a22bd8349cc281393cb04dbd8cac2f8d867da11f2a724c52"
)
for name, expected in json.loads(manifest)["files"].items():
    assert hashlib.sha256((ACCEPTANCE / name).read_bytes()).hexdigest() == expected, name


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ACCEPTANCE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_original = _load("test_recall_budget")
_supplement = _load("test_recall_budget_supplement")
_adversaries = _load("test_recall_adversaries")


class TestRecallBudget(_original.RecallBudgetAcceptance):
    pass


class TestRecallBudgetStdio(_original.RecallBudgetStdioAcceptance):
    pass


class TestRecallBudgetValidation(_supplement.RecallBudgetValidationSupplement):
    pass


class TestRecallBudgetOverflow(_supplement.RecallRoutingOverflowSupplement):
    pass


class TestRecallBudgetAdversaries(_adversaries.RecallAdversaries):
    pass
