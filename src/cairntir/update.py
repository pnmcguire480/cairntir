"""Non-blocking update notifier.

This module checks PyPI for a newer Cairntir release at most once per 24
hours, in a background thread, and surfaces the result through
:func:`pending_update_banner`. Callers (the CLI and the MCP server) can
prepend that banner to their next user-visible response. Network failures
are intentionally swallowed and never propagate — a missing update check
must never block a tool call or interrupt the daemon.

The cache lives at ``cairntir_home() / ".update_check"`` and stores the
last checked timestamp plus the latest seen version. The cache is also
the on/off switch: deleting the file forces a recheck on the next call.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from cairntir import __version__
from cairntir.config import cairntir_home

_PYPI_URL: Final[str] = "https://pypi.org/pypi/cairntir/json"
_CACHE_FILENAME: Final[str] = ".update_check"
_CHECK_INTERVAL: Final[timedelta] = timedelta(hours=24)
_NETWORK_TIMEOUT_SECONDS: Final[float] = 2.0
_USER_AGENT: Final[str] = f"cairntir/{__version__} (+update-notifier)"

_DISABLE_ENV_VAR: Final[str] = "CAIRNTIR_DISABLE_UPDATE_CHECK"
"""Set to any truthy value to skip the PyPI check entirely.

Useful in CI, on air-gapped machines, or when the user simply wants
silence. When set, :func:`pending_update_banner` always returns
``None`` and :func:`maybe_check_in_background` is a no-op.
"""


def _cache_path() -> Path:
    return cairntir_home() / _CACHE_FILENAME


def _is_disabled() -> bool:
    """Return True iff the env var is set to a truthy value."""
    import os

    raw = os.environ.get(_DISABLE_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    """Parse a PEP 440-ish version into a tuple of ints for comparison.

    Stops at the first non-numeric segment so ``1.2.3rc1`` becomes
    ``(1, 2, 3)`` and compares as the released version. This is a
    deliberately blunt comparator — the goal is "newer or not", not a
    full PEP 440 implementation.
    """
    parts: list[int] = []
    for raw in version.split("."):
        digits = ""
        for ch in raw:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _is_newer(latest: str, current: str) -> bool:
    """Return True iff ``latest`` is strictly newer than ``current``."""
    return _parse_version_tuple(latest) > _parse_version_tuple(current)


def _load_cache() -> dict[str, str]:
    """Load the update cache; return an empty dict on any read failure.

    The cache is best-effort: a corrupted file simply triggers a fresh
    check on the next call.
    """
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(k): str(v) for k, v in loaded.items()}


def _write_cache(latest: str) -> None:
    """Persist the latest seen version + timestamp. Best-effort.

    Disk write errors are swallowed because the notifier must never
    interrupt a working tool call. The next process will simply check
    again.
    """
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "latest": latest,
    }
    try:
        _cache_path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def _cache_is_fresh(cache: dict[str, str]) -> bool:
    """Return True iff the cache was written within ``_CHECK_INTERVAL``."""
    raw = cache.get("checked_at", "")
    if not raw:
        return False
    try:
        checked_at = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - checked_at < _CHECK_INTERVAL


def _fetch_latest_from_pypi() -> str | None:
    """Hit PyPI with a 2s timeout. Return the latest version or ``None``.

    Network errors, JSON errors, and missing fields all map to ``None``
    — this is fail-silent by design.
    """
    request = urllib.request.Request(  # noqa: S310 — fixed PyPI URL, not user input
        _PYPI_URL,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — same as above
            request, timeout=_NETWORK_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    info = payload.get("info") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        return None
    latest = info.get("version")
    return latest if isinstance(latest, str) else None


def _check_now() -> None:
    """Run one PyPI check synchronously. Always writes the cache on success."""
    latest = _fetch_latest_from_pypi()
    if latest is not None:
        _write_cache(latest)


def maybe_check_in_background() -> threading.Thread | None:
    """Spawn a daemon thread that refreshes the update cache if stale.

    Returns the thread (so tests can ``join`` it) or ``None`` if the
    check was skipped (cache fresh, env var disables, or anything went
    wrong picking the cache directory). The thread is a daemon — it
    will not block process exit.
    """
    if _is_disabled():
        return None
    try:
        cache = _load_cache()
    except OSError:
        return None
    if _cache_is_fresh(cache):
        return None
    thread = threading.Thread(
        target=_check_now,
        name="cairntir-update-check",
        daemon=True,
    )
    thread.start()
    return thread


def pending_update_banner() -> str | None:
    """Return a one-line banner if a newer Cairntir is available.

    Returns ``None`` if no update is known, the cache is empty, the
    notifier is disabled, or the cached version is not strictly newer
    than the running version. The banner is meant to be appended to a
    tool response or printed at the bottom of a CLI invocation — it is
    intentionally short and self-explanatory.
    """
    if _is_disabled():
        return None
    cache = _load_cache()
    latest = cache.get("latest")
    if not latest:
        return None
    if not _is_newer(latest, __version__):
        return None
    return (
        f"[cairntir update available: {__version__} → {latest} — "
        f"run `pip install -U cairntir`]"
    )
