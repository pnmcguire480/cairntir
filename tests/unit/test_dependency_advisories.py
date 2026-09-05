from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_dependency_advisories.py"
SPEC = importlib.util.spec_from_file_location("dependency_advisories", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_active_advisories_and_yanked_releases_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "info": {"yanked": True},
        "vulnerabilities": [{"id": "active"}, {"id": "withdrawn", "withdrawn": "2026-01-01"}],
    }
    monkeypatch.setattr(CHECKER, "urlopen", lambda *a, **kw: io.StringIO(json.dumps(payload)))
    assert CHECKER.audit_package(("example", "1.0")) == [
        "example==1.0: active",
        "example==1.0: release is yanked",
    ]


def test_network_failure_is_not_a_clean_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr(CHECKER, "urlopen", unavailable)
    assert CHECKER.main() == 1


def test_incomplete_payload_is_not_a_clean_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CHECKER, "urlopen", lambda *a, **kw: io.StringIO("{}"))
    assert CHECKER.main() == 1
