"""Self-healing user-scope MCP registration.

This module is the runtime answer to "cairntir TRUE until cairntir
FALSE." Once cairntir is pip-installed, every CLI invocation calls
:func:`ensure_registered` which silently re-registers the MCP server at
user scope if it is missing. Uninstalling the package removes the
``cairntir-mcp`` console script from PATH, which is what FALSE looks
like — Claude Code surfaces the missing command and the user knows.

Registration is keyed on a checkpoint file at
``cairntir_home() / ".registered"`` so the helper is a no-op on the
fast path. The checkpoint is opportunistic, not authoritative: if the
file exists but the user has manually removed the cairntir entry from
``claude mcp list``, the next ``cairntir`` invocation after deletion
of the checkpoint (or after :func:`ensure_registered` is called with
``force=True``) will re-register.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from cairntir.config import cairntir_home

_CHECKPOINT_FILENAME: Final[str] = ".registered"
_MCP_SERVER_COMMAND: Final[str] = "cairntir-mcp"
_MCP_SERVER_NAME: Final[str] = "cairntir"
_DISABLE_ENV_VAR: Final[str] = "CAIRNTIR_DISABLE_AUTOREGISTER"
"""Set to a truthy value to skip the silent re-registration entirely.

For users who manage their MCP registry by hand and do not want
cairntir to touch it. When set, :func:`ensure_registered` is a no-op
and returns ``"disabled"``.
"""


def _is_disabled() -> bool:
    import os

    raw = os.environ.get(_DISABLE_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _checkpoint_path() -> Path:
    return cairntir_home() / _CHECKPOINT_FILENAME


def _write_checkpoint(path: Path) -> bool:
    """Record that registration is done. Return whether the write landed.

    Best-effort by design — a failure here costs a ``claude mcp list``
    subprocess on the next invocation, not correctness — but it is *said*
    rather than swallowed. A silently unwritable checkpoint turns the fast
    path off forever and looks like nothing at all from the outside.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(
            f"cairntir: could not write the registration checkpoint {path}: {exc}. "
            "Registration itself is fine; every command will re-check until "
            "this path is writable.",
            file=sys.stderr,
        )
        return False
    return True


def _claude_path() -> str | None:
    """Locate the ``claude`` CLI on PATH, or ``None`` if unavailable."""
    return shutil.which("claude")


def _list_user_mcps(claude: str) -> str | None:
    """Return the raw stdout of ``claude mcp list``, or ``None`` on failure.

    The command is intentionally invoked without ``-s user`` because
    older Claude Code versions reject the flag for ``list``. The output
    is searched for the cairntir server name regardless of scope; a
    project-scope-only registration will not satisfy the check, which
    is the correct behavior — we want the *user* scope guarantee.
    """
    try:
        result = subprocess.run(  # noqa: S603 — argv fully constructed
            [claude, "mcp", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def _listing_contains_cairntir(listing: str) -> bool:
    """Return True iff ``listing`` lists ``cairntir`` as a server name.

    The Claude Code ``mcp list`` output prints one server per line, in
    the shape ``<name>:<rest>`` or ``<name><whitespace><rest>``. A naive
    substring search would false-positive on a description that
    mentions cairntir; we anchor on the start of the line.
    """
    for raw_line in listing.splitlines():
        line = raw_line.strip()
        if not line.startswith(_MCP_SERVER_NAME):
            continue
        rest = line[len(_MCP_SERVER_NAME) :]
        if not rest or rest[0] in {":", " ", "\t"}:
            return True
    return False


def _add_user_mcp(claude: str) -> bool:
    """Run ``claude mcp add -s user cairntir -- cairntir-mcp``. Return success."""
    try:
        result = subprocess.run(  # noqa: S603 — argv fully constructed
            [
                claude,
                "mcp",
                "add",
                "-s",
                "user",
                _MCP_SERVER_NAME,
                "--",
                _MCP_SERVER_COMMAND,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode == 0:
        return True
    combined = ((result.stderr or "") + (result.stdout or "")).lower()
    # "already exists" is success from our perspective: the entry is there.
    return "already exists" in combined


def ensure_registered(*, force: bool = False) -> str:
    """Idempotently ensure user-scope cairntir registration. Return a status code.

    Returns one of:

    * ``"disabled"`` — the env var disables the auto-register
    * ``"checkpoint"`` — the local checkpoint says we are registered;
      no claude CLI call was made (fast path)
    * ``"present"`` — ``claude mcp list`` already shows cairntir
    * ``"registered"`` — we just added the entry
    * ``"no-claude"`` — the ``claude`` CLI is not on PATH
    * ``"failed"`` — the add command failed for some other reason

    Never raises. The caller decides whether to surface the result.
    """
    if _is_disabled():
        return "disabled"

    checkpoint = _checkpoint_path()
    if not force and checkpoint.exists():
        return "checkpoint"

    claude = _claude_path()
    if claude is None:
        return "no-claude"

    listing = _list_user_mcps(claude)
    if listing is not None and _listing_contains_cairntir(listing):
        # Already registered — record the fact for the next invocation.
        _write_checkpoint(checkpoint)
        return "present"

    if _add_user_mcp(claude):
        _write_checkpoint(checkpoint)
        return "registered"

    return "failed"


def clear_checkpoint() -> None:
    """Delete the registered-checkpoint so the next call re-checks.

    Useful after an uninstall, after a manual ``claude mcp remove``,
    or before a forced re-registration. Best-effort; missing file is
    not an error.

    A failed *unlink* is not silent, though. The checkpoint surviving means
    the next invocation takes the fast path and skips the re-registration
    the caller just asked for — the opposite of what was requested, and
    invisible unless it is said out loud.
    """
    path = _checkpoint_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        print(
            f"cairntir: could not clear the registration checkpoint {path}: {exc}. "
            "The next invocation will still take the fast path; remove the file "
            "by hand to force a re-check.",
            file=sys.stderr,
        )
