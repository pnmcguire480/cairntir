"""Safe, host-specific adapters for Cairntir's shared MCP memory.

The database and MCP server are host-neutral.  This module contains the
small amount of host-specific wiring needed to make that same server visible
to every supported agent host without overwriting unrelated user config.

Two host tuples live here and they are not interchangeable.  SUPPORTED_HOSTS
is what ``cairntir init`` can wire; TRANSCRIPT_HOSTS is the smaller set whose
on-disk transcript format Cairntir can actually read.  Recovery callers must
gate on the latter -- treating the two as one silently breaks host startup.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

HostName = Literal[
    "claude",
    "cline",
    "codex",
    "copilot",
    "cursor",
    "gemini",
    "opencode",
    "qwen",
]
HostScope = Literal["project", "user"]

# Hosts whose transcripts Cairntir knows how to read. This is a strict subset
# of SUPPORTED_HOSTS: wiring a host to the shared store is cheap, but reading
# its on-disk transcript format is a per-host adapter. Callers that recover
# transcripts MUST gate on this tuple, not on SUPPORTED_HOSTS.
TranscriptHostName = Literal["claude", "codex", "cursor", "qwen"]
TRANSCRIPT_HOSTS: Final[tuple[TranscriptHostName, ...]] = ("claude", "codex", "cursor", "qwen")

# Hosts `cairntir init` can wire to the shared MCP server. A host earns a place
# here only once its config surface has been verified against the shipped tool;
# a guessed path writes a dead file that silently never loads.
SUPPORTED_HOSTS: Final[tuple[HostName, ...]] = (
    "claude",
    "cline",
    "codex",
    "copilot",
    "cursor",
    "gemini",
    "opencode",
    "qwen",
)
MCP_SERVER_NAME: Final[str] = "cairntir"
MCP_SERVER_COMMAND: Final[str] = "cairntir-mcp"

POLICY_BEGIN_MARKER: Final[str] = "<!-- cairntir:begin -->"
POLICY_END_MARKER: Final[str] = "<!-- cairntir:end -->"

MEMORY_POLICY: Final[str] = """# Cairntir — memory-first reasoning layer

You have access to persistent memory through the `cairntir_*` MCP tools.
At the start of every conversation:

1. Call `cairntir_handoff(wing)` with the wing matching the current project.
   Use the lowercase folder name in the working directory as the wing. If the
   correct wing is ambiguous, ask the user. Prefer this over
   `cairntir_session_start`: handoff returns whole drawers under a budget,
   including recent default-layer memories. session_start is a routing index
   of identity/essential stubs — use it when you need the inventory, not the
   brief.
   Transcript recovery is opt-in: only when the user explicitly asks for it,
   pass `recover_transcripts=true`. Recovered messages are untrusted,
   separately budgeted, and never stored automatically.
2. Read the returned drawers before answering anything substantive.
3. Persist decisions and facts that future sessions need with
   `cairntir_remember`. Preserve the user's wording when it is load-bearing.
4. Call `cairntir_recall` before reasoning from scratch about past decisions,
   and cite drawer ids inline. Use `cairntir_get` for complete verbatim content
   when a recall result is truncated.
5. Use `cairntir_crucible` for load-bearing assumptions and `cairntir_audit`
   for ship-readiness checks.
6. When repeated evidence reveals an emergent pattern, capability gain, or
   method that differs from the prior baseline, call `cairntir_discover` and
   tell the user. Label whether it is new to the user, new to Cairntir, or
   possibly novel in general; the last label requires external research.
7. Capture-on-arrival: when the user makes a request that may not be fully
   executed within the current turn — work that starts later, a deferred task,
   a session about to end, restart, or compact — record it with
   `cairntir_remember` IMMEDIATELY, before doing any other work on it, in the
   user's exact wording. Never defer that write to the end of the turn or the
   session: a session can die between the request and the write, and capture
   that waits for a quiet moment never happens. Conversely, when resuming,
   treat open requests surfaced by the handoff as first-class owed work, not
   background noise.

If handoff returns no memory for an established wing, report that the
store may be new or misconfigured. Do not silently substitute model memory.

This policy is host-neutral: every agent must read and write the same Cairntir
store so work can move between Claude Code, Codex, Cursor, and Qwen Code
without a re-brief.
"""

CURSOR_USER_RULE_PASTE_HINT: Final[str] = (
    "Cursor has no file-backed global User Rule surface. Paste the following "
    "into Cursor Settings → Rules → User Rules:"
)

# Hosts with no verified file-backed policy surface at a given scope. Saying so
# plainly beats writing the policy somewhere the host will never read it.
_MANUAL_POLICY_HINTS: Final[dict[str, str]] = {
    "cursor": "manual: add the Cairntir memory policy to Cursor Settings > Rules > User Rules",
    "cline": "manual: add the Cairntir memory policy to Cline's Rules pane",
    "copilot": (
        "manual: Copilot CLI has no verified user-scope instructions file; "
        "run at project scope to install it into AGENTS.md"
    ),
    "opencode": (
        "manual: OpenCode has no verified user-scope instructions file; "
        "run at project scope to install it into AGENTS.md"
    ),
}

_MANUAL_POLICY_STATUS: Final[dict[str, str]] = {
    "cursor": "Cursor global User Rules are managed in Cursor Settings",
    "cline": "Cline rules are managed in its Rules pane",
    "copilot": "Copilot CLI exposes no verified user-scope instructions file",
    "opencode": "OpenCode exposes no verified user-scope instructions file",
}

_CURSOR_RULE_HEADER: Final[str] = """---
description: Use Cairntir persistent memory before reasoning
globs:
alwaysApply: true
---

"""

_CODEX_MCP_BEGIN: Final[str] = "# cairntir:mcp:begin"
_CODEX_MCP_END: Final[str] = "# cairntir:mcp:end"


class HostConfigurationError(RuntimeError):
    """A host configuration could not be changed without risking user data."""


@dataclass(frozen=True, slots=True)
class HostSetupResult:
    """Outcome of configuring one agent host."""

    host: HostName
    scope: HostScope
    registration: str
    registration_path: Path | None
    policy: str
    policy_path: Path | None


@dataclass(frozen=True, slots=True)
class HostStatus:
    """Read-only status for one host's MCP and memory-policy wiring."""

    host: HostName
    scope: HostScope
    mcp_configured: bool | None
    mcp_detail: str
    policy_configured: bool | None
    policy_detail: str


def mcp_spec(host: HostName | None = None) -> dict[str, object]:
    """Return the portable stdio MCP specification used by JSON hosts."""
    args = ["--host", host] if host is not None else []
    return {"command": MCP_SERVER_COMMAND, "args": args}


def mcp_container_key(host: HostName | None = None) -> str:
    """Return the JSON key under which this host stores its MCP servers."""
    return "mcp" if host == "opencode" else "mcpServers"


def mcp_entry(host: HostName | None = None) -> dict[str, object]:
    """Return the MCP entry shaped the way this host's own tooling writes it.

    Most hosts take the portable ``command``/``args`` spec. Two do not, and
    matching their native shape is what keeps ``init`` idempotent against a
    config the user may also have touched with the host's own ``mcp add``.
    """
    if host == "opencode":
        # OpenCode folds argv into one command array and gates on `enabled`.
        return {
            "type": "local",
            "command": [MCP_SERVER_COMMAND, "--host", host],
            "enabled": True,
        }
    if host == "copilot":
        # Copilot CLI tags the transport and carries an explicit tool allowlist.
        return {**mcp_spec(host), "type": "local", "tools": ["*"]}
    return mcp_spec(host)


def _codex_mcp_block() -> str:
    return """[mcp_servers.cairntir]
command = "cairntir-mcp"
args = ["--host", "codex"]
"""


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, returning an empty object for a missing file."""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostConfigurationError(f"{path} is not valid readable JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise HostConfigurationError(f"{path} is not a JSON object")
    return loaded


def merge_mcp_spec(
    config: dict[str, Any],
    *,
    host: HostName | None = None,
) -> tuple[dict[str, Any], bool]:
    """Merge Cairntir into a JSON MCP config while preserving other servers."""
    key = mcp_container_key(host)
    servers = config.setdefault(key, {})
    if not isinstance(servers, dict):
        raise HostConfigurationError(f"{key} in target config is not a JSON object")
    spec = mcp_entry(host)
    if servers.get(MCP_SERVER_NAME) == spec:
        return config, False
    servers[MCP_SERVER_NAME] = spec
    return config, True


def write_json_object(path: Path, data: dict[str, Any]) -> None:
    """Write a deterministic JSON object, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def upsert_marked_policy(path: Path, *, prefix: str = "", body: str = MEMORY_POLICY) -> str:
    """Install the delimited memory policy without clobbering other content.

    Returns ``created``, ``appended``, ``updated``, or ``unchanged``.
    """
    block = f"{POLICY_BEGIN_MARKER}\n{body}{POLICY_END_MARKER}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prefix + block, encoding="utf-8")
        return "created"

    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HostConfigurationError(f"could not read {path}: {exc}") from exc
    begin = existing.find(POLICY_BEGIN_MARKER)
    end = existing.find(POLICY_END_MARKER)

    if (begin == -1) != (end == -1) or (begin != -1 and end < begin):
        raise HostConfigurationError(
            f"{path} contains only one Cairntir policy marker; repair it manually"
        )
    if begin == -1:
        separator = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        path.write_text(existing + separator + block, encoding="utf-8")
        return "appended"

    end_of_block = end + len(POLICY_END_MARKER)
    if end_of_block < len(existing) and existing[end_of_block] == "\n":
        end_of_block += 1
    replacement = existing[:begin] + block + existing[end_of_block:]
    if replacement == existing:
        return "unchanged"
    path.write_text(replacement, encoding="utf-8")
    return "updated"


def _json_mcp_path(host: HostName, scope: HostScope, root: Path, home: Path) -> Path:
    if host == "claude":
        if scope == "user":
            raise HostConfigurationError("Claude user registration is managed by the Claude CLI")
        return root / ".mcp.json"
    if host == "cursor":
        return home / ".cursor" / "mcp.json" if scope == "user" else root / ".cursor" / "mcp.json"
    if host == "qwen":
        # Qwen Code reads mcpServers from settings.json at both scopes.
        return (
            home / ".qwen" / "settings.json"
            if scope == "user"
            else root / ".qwen" / "settings.json"
        )
    if host == "gemini":
        # Gemini CLI mirrors the user layout inside the project.
        return (
            home / ".gemini" / "settings.json"
            if scope == "user"
            else root / ".gemini" / "settings.json"
        )
    if host == "copilot":
        # Copilot CLI also reads a bare .mcp.json, but that file is shared with
        # Claude project scope; writing the two differently shaped entries to
        # one file would make each `init` clobber the other. Use .github/.
        return (
            home / ".copilot" / "mcp-config.json"
            if scope == "user"
            else root / ".github" / "mcp.json"
        )
    if host == "opencode":
        return (
            home / ".config" / "opencode" / "opencode.json"
            if scope == "user"
            else root / "opencode.json"
        )
    if host == "cline":
        if scope == "project":
            raise HostConfigurationError(
                "Cline has no verified project-scoped MCP config; run with --user"
            )
        return home / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
    raise HostConfigurationError(f"{host} does not use a JSON MCP configuration")


def _policy_path(host: HostName, scope: HostScope, root: Path, home: Path) -> Path | None:
    if host == "claude":
        return home / ".claude" / "CLAUDE.md" if scope == "user" else root / "CLAUDE.md"
    if host == "codex":
        return home / ".codex" / "AGENTS.md" if scope == "user" else root / "AGENTS.md"
    if host == "qwen":
        # Qwen Code loads QWEN.md at user level and from the project root.
        return home / ".qwen" / "QWEN.md" if scope == "user" else root / "QWEN.md"
    if host == "gemini":
        # Gemini CLI loads GEMINI.md as its context file at both scopes.
        return home / ".gemini" / "GEMINI.md" if scope == "user" else root / "GEMINI.md"
    if host in ("copilot", "opencode"):
        # Both read AGENTS.md from the project root. Neither exposes a
        # user-scope instructions file verified against the shipped tool, so
        # user scope reports the manual hint rather than writing a dead file.
        return root / "AGENTS.md" if scope == "project" else None
    if host == "cline":
        # Cline's rules surface is GUI-managed; nothing file-backed to verify.
        return None
    if host == "cursor":
        return root / ".cursor" / "rules" / "cairntir.mdc" if scope == "project" else None
    return None


def _run_cli(executable_name: str, *args: str) -> tuple[int, str, str]:
    executable = shutil.which(executable_name)
    if executable is None:
        return 127, "", f"could not find `{executable_name}` on PATH"
    try:
        completed = subprocess.run(  # noqa: S603 - executable resolved by shutil.which
            [executable, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", f"failed to invoke `{executable_name}`: {exc}"
    return (
        completed.returncode,
        (completed.stdout or "").strip(),
        (completed.stderr or "").strip(),
    )


def _register_cli_host(host: Literal["claude", "codex"], *, force: bool) -> str:
    remove_args: tuple[str, ...]
    add_args: tuple[str, ...]
    if host == "claude":
        remove_args = ("mcp", "remove", "-s", "user", MCP_SERVER_NAME)
        add_args = (
            "mcp",
            "add",
            "-s",
            "user",
            MCP_SERVER_NAME,
            "--",
            MCP_SERVER_COMMAND,
            "--host",
            host,
        )
    else:
        remove_args = ("mcp", "remove", MCP_SERVER_NAME)
        add_args = (
            "mcp",
            "add",
            MCP_SERVER_NAME,
            "--",
            MCP_SERVER_COMMAND,
            "--host",
            host,
        )

    if force:
        _run_cli(host, *remove_args)
    code, stdout, stderr = _run_cli(host, *add_args)
    if code == 0:
        return stdout or "registered"
    combined = stderr or stdout
    if "already exists" in combined.lower() and not force:
        return "already registered"
    raise HostConfigurationError(f"`{host} {' '.join(add_args)}` exited {code}: {combined}")


def _codex_project_config(path: Path, *, force: bool) -> str:
    block = _codex_mcp_block()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{_CODEX_MCP_BEGIN}\n{block}{_CODEX_MCP_END}\n",
            encoding="utf-8",
        )
        return "created"

    try:
        existing = path.read_text(encoding="utf-8")
        parsed = tomllib.loads(existing)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise HostConfigurationError(f"{path} is not valid readable TOML: {exc}") from exc

    servers = parsed.get("mcp_servers", {})
    cairntir = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
    expected = mcp_spec("codex")
    if cairntir == expected:
        return "unchanged"
    if cairntir is not None and _CODEX_MCP_BEGIN not in existing:
        action = "replace" if force else "change"
        raise HostConfigurationError(
            f"{path} already defines mcp_servers.cairntir outside Cairntir markers; "
            f"refusing to {action} user-owned TOML"
        )

    marked = f"{_CODEX_MCP_BEGIN}\n{block}{_CODEX_MCP_END}\n"
    begin = existing.find(_CODEX_MCP_BEGIN)
    end = existing.find(_CODEX_MCP_END)
    if (begin == -1) != (end == -1) or (begin != -1 and end < begin):
        raise HostConfigurationError(f"{path} contains an incomplete Cairntir MCP block")
    if begin == -1:
        separator = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        path.write_text(existing + separator + marked, encoding="utf-8")
        return "appended"
    end_of_block = end + len(_CODEX_MCP_END)
    if end_of_block < len(existing) and existing[end_of_block] == "\n":
        end_of_block += 1
    replacement = existing[:begin] + marked + existing[end_of_block:]
    path.write_text(replacement, encoding="utf-8")
    return "updated"


def configure_host(
    host: HostName,
    *,
    scope: HostScope,
    root: Path,
    home: Path,
    force: bool = False,
    install_policy: bool = True,
) -> HostSetupResult:
    """Configure one host to use Cairntir's shared MCP server and policy."""
    registration_path: Path | None
    if host == "codex":
        if scope == "user":
            registration_path = home / ".codex" / "config.toml"
            already, _ = _codex_status(registration_path)
            if already and not force:
                # `codex mcp add` rewrites the whole stanza, silently dropping
                # anything the user added under it -- per-tool approval_mode
                # gates, for one. Never invoke it when the entry is correct.
                registration = "unchanged"
            else:
                registration = _register_cli_host("codex", force=force)
        else:
            registration_path = root / ".codex" / "config.toml"
            registration = _codex_project_config(registration_path, force=force)
    elif host == "claude" and scope == "user":
        registration = _register_cli_host("claude", force=force)
        registration_path = None
    else:
        registration_path = _json_mcp_path(host, scope, root, home)
        existed = registration_path.exists()
        config = load_json_object(registration_path)
        config, changed = merge_mcp_spec(config, host=host)
        if changed or force:
            write_json_object(registration_path, config)
            registration = "updated" if existed else "created"
        else:
            registration = "unchanged"

    policy_path = _policy_path(host, scope, root, home) if install_policy else None
    if not install_policy:
        policy = "skipped"
    elif policy_path is None:
        policy = _MANUAL_POLICY_HINTS.get(
            host, f"manual: {host} has no verified file-backed policy surface at {scope} scope"
        )
    else:
        prefix = _CURSOR_RULE_HEADER if host == "cursor" else ""
        policy = upsert_marked_policy(policy_path, prefix=prefix)

    return HostSetupResult(
        host=host,
        scope=scope,
        registration=registration,
        registration_path=registration_path,
        policy=policy,
        policy_path=policy_path,
    )


_IDENTITY_KEYS: Final[tuple[str, ...]] = ("command", "args")


def _entry_matches(actual: object, expected: dict[str, object]) -> bool:
    """True when an existing entry names the Cairntir server for this host.

    Compared on identity keys only. Hosts and users legitimately add their own
    fields around ours -- Codex per-tool ``approval_mode``, Gemini ``trust``,
    Copilot tool filters -- and demanding exact equality made ``doctor`` report
    a correctly wired host as unconfigured.
    """
    if not isinstance(actual, dict):
        return False
    return all(actual.get(key) == expected[key] for key in _IDENTITY_KEYS if key in expected)


def _json_status(path: Path, *, host: HostName) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path}"
    try:
        config = load_json_object(path)
    except HostConfigurationError as exc:
        return False, str(exc)
    servers = config.get(mcp_container_key(host), {})
    if not isinstance(servers, dict) or not _entry_matches(
        servers.get(MCP_SERVER_NAME), mcp_entry(host)
    ):
        return False, f"{path} has no matching Cairntir MCP entry"
    return True, str(path)


def _codex_status(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path}"
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return False, f"{path} is not valid readable TOML: {exc}"
    servers = parsed.get("mcp_servers", {})
    spec = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
    if not _entry_matches(spec, mcp_spec("codex")):
        return False, f"{path} has no matching Cairntir MCP entry"
    return True, str(path)


def inspect_host(
    host: HostName,
    *,
    scope: HostScope,
    root: Path,
    home: Path,
) -> HostStatus:
    """Inspect one host without modifying config or invoking its CLI."""
    if host == "claude" and scope == "user":
        mcp_configured: bool | None = None
        mcp_detail = "use `claude mcp list`; Claude owns its user registry"
    elif host == "codex":
        config_path = (
            home / ".codex" / "config.toml" if scope == "user" else root / ".codex" / "config.toml"
        )
        mcp_configured, mcp_detail = _codex_status(config_path)
    else:
        try:
            config_path = _json_mcp_path(host, scope, root, home)
        except HostConfigurationError as exc:
            # inspect_host is read-only and must never raise on a host that
            # simply has no config surface at this scope.
            mcp_configured, mcp_detail = None, str(exc)
        else:
            mcp_configured, mcp_detail = _json_status(config_path, host=host)

    policy_path = _policy_path(host, scope, root, home)
    if policy_path is None:
        policy_configured: bool | None = None
        policy_detail = _MANUAL_POLICY_STATUS.get(
            host, f"{host} exposes no file-backed policy surface at {scope} scope"
        )
    elif not policy_path.exists():
        policy_configured = False
        policy_detail = f"missing {policy_path}"
    else:
        try:
            contents = policy_path.read_text(encoding="utf-8")
        except OSError as exc:
            policy_configured = False
            policy_detail = f"could not read {policy_path}: {exc}"
        else:
            policy_configured = POLICY_BEGIN_MARKER in contents and POLICY_END_MARKER in contents
            policy_detail = (
                str(policy_path)
                if policy_configured
                else f"{policy_path} has no complete Cairntir policy block"
            )

    return HostStatus(
        host=host,
        scope=scope,
        mcp_configured=mcp_configured,
        mcp_detail=mcp_detail,
        policy_configured=policy_configured,
        policy_detail=policy_detail,
    )
