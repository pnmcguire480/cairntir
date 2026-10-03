"""Execute public question acceptance with immutable artifact verification."""

import hashlib
import importlib.util
import json
from pathlib import Path

ACCEPTANCE = Path(__file__).resolve().parents[2] / "plans/acceptance/v2-questions"


def _verify():
    raw = (ACCEPTANCE / "PACKAGE-FROZEN.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "44213394900601e3b83a2a1861b5f97fc3b464087e5d25b2d6c1ae4abe6b4781"
    )
    for name, digest in json.loads(raw)["files"].items():
        assert hashlib.sha256((ACCEPTANCE / name).read_bytes()).hexdigest() == digest, name
    for path in ACCEPTANCE.glob("*-FROZEN.json"):
        for name, digest in json.loads(path.read_bytes())["files"].items():
            assert hashlib.sha256((ACCEPTANCE / name).read_bytes()).hexdigest() == digest, name


def _load(name):
    spec = importlib.util.spec_from_file_location("frozen_questions_" + name, ACCEPTANCE / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verify()
_core = _load("test_questions_core.py")
_scoped = _load("test_questions_scoped.py")
_surfaces = _load("test_questions_surfaces_v2.py")
_expiry = _load("test_questions_expiry.py")
_replay = _load("test_questions_expiry_replay.py")
_supplement = _load("supplement/test_questions_supplement.py")


class TestQuestionCore(_core.QuestionsCoreAcceptance):
    pass


class TestQuestionScope(_scoped.ScopedQuestionAcceptance):
    pass


class TestQuestionSurfaces(_surfaces.QuestionSurfacesAcceptance):
    pass


class TestQuestionExpiry(_expiry.QuestionExpiryAcceptance):
    pass


class TestQuestionExpiryReplay(_replay.QuestionExpiryReplayAcceptance):
    pass


class TestQuestionBoundarySupplement(_supplement.QuestionBoundarySupplement):
    pass
