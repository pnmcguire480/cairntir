"""Require the freshly prepared actual Q05 tools before any resource case."""

import os
from pathlib import Path

import pytest
from scripts.provision_q05 import verify_platform


@pytest.fixture(scope="session", autouse=True)
def _prepared_actual_tools() -> None:
    platform = os.environ.get("CAIRNTIR_Q05_PLATFORM")
    if not platform:
        pytest.fail("Q05 requires CAIRNTIR_Q05_PLATFORM from scripts/provision_q05.py")
    verify_platform(Path(platform))
