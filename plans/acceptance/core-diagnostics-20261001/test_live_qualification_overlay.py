"""Additive independent controls: configuration unknown is not live-health evidence."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SOURCE = Path(__file__).with_name("test_core_diagnostics.py")
_SPEC = importlib.util.spec_from_file_location("frozen_core_diagnostics", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
frozen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(frozen)
isolated = frozen.isolated


def assert_explicit_live_unverified(text):
    frozen.assert_host_unverified(text)
    # Require a connectivity subject directly attached to its qualification;
    # "agent hosts ... MCP=unknown" describes configuration, not live health.
    assert re.search(
        r"\b(?:live(?:\s+(?:host|connection|connectivity))?|"
        r"(?:host\s+)?(?:connection|connectivity))\s*(?:is\s*)?[:=]?\s*"
        r"(?:unverified|not verified|not tested|unknown)\b",
        frozen.flat(text),
    ), "EXPLICIT_LIVE_QUALIFICATION_REQUIRED"


@pytest.mark.parametrize("configured,stale", [(True, False), (False, False), (None, False), (True, True)])
def test_actual_doctor_explicitly_qualifies_live_observation(isolated, monkeypatch, configured, stale):
    frozen.doctor_fixture(monkeypatch, isolated, configured=configured, stale=stale)
    result = frozen.RUNNER.invoke(frozen.cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert_explicit_live_unverified(result.output)


def test_exact_old_unknown_configuration_text_is_rejected():
    old = "agent hosts (read-only): user codex MCP=unknown policy=ready"
    # Preserve evidence of the original oracle's real blind spot.
    frozen.assert_host_unverified(old)
    with pytest.raises(AssertionError, match="EXPLICIT_LIVE_QUALIFICATION_REQUIRED"):
        assert_explicit_live_unverified(old)


def test_explicit_unknown_live_connection_is_honest():
    assert_explicit_live_unverified("MCP=unknown; live connection: unverified")
    assert_explicit_live_unverified("MCP=configured; host connection is not tested")