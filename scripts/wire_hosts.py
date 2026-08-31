#!/usr/bin/env python3
"""Wire every agent host present on this machine to the shared Cairntir store.

For hosts in SUPPORTED_HOSTS this is a thin driver over `cairntir init`: the
registry in cairntir.hosts owns every config path and entry shape, so this
script cannot drift from it. Its own job is the part the registry does not do
-- deciding which hosts are actually installed, and probing agents whose config
surface has never been verified rather than guessing one.

A guessed config path writes a dead file that silently never loads, which is
worse than no file at all. Unverified hosts are reported, never written.

Usage:
    python scripts/wire_hosts.py --dry-run   # report, change nothing
    python scripts/wire_hosts.py             # wire every host present
    python scripts/wire_hosts.py --no-policy # MCP only, skip instruction files
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from cairntir.hosts import (
    MCP_SERVER_COMMAND,
    MCP_SERVER_NAME,
    SUPPORTED_HOSTS,
    HostConfigurationError,
    configure_host,
    inspect_host,
)

HOME = Path.home()

# A host counts as present if its binary is on PATH or its config dir exists --
# GUI hosts (Cline, Cursor) never land a binary on PATH.
BINARIES: dict[str, str] = {
    "claude": "claude",
    "cline": "cline",
    "codex": "codex",
    "copilot": "copilot",
    "cursor": "cursor-agent",
    "gemini": "gemini",
    "opencode": "opencode",
    "qwen": "qwen",
}

CONFIG_DIRS: dict[str, Path] = {
    "claude": HOME / ".claude",
    "cline": HOME / ".cline",
    "codex": HOME / ".codex",
    "copilot": HOME / ".copilot",
    "cursor": HOME / ".cursor",
    "gemini": HOME / ".gemini",
    "opencode": HOME / ".config" / "opencode",
    "qwen": HOME / ".qwen",
}

# Agents with no verified config surface. If one ships its own `mcp add` we use
# it; otherwise we say so and stop. Add a host to cairntir.hosts.SUPPORTED_HOSTS
# once its surface has been checked against the shipped tool, and drop it here.
UNVERIFIED: dict[str, str] = {
    "droid": "droid",
    "openclaw": "openclaw",
    "hermes": "hermes",
    "pi": "pi",
    "omp": "omp",
    "dsh": "dsh",
}


def present(host: str) -> bool:
    """Return whether a supported host is installed or configured."""
    binary = BINARIES.get(host)
    if binary and shutil.which(binary):
        return True
    config_dir = CONFIG_DIRS.get(host)
    return config_dir is not None and config_dir.exists()


def wire_supported(host: str, *, dry_run: bool, install_policy: bool) -> tuple[str, str]:
    """Inspect or configure one host from the verified registry."""
    if dry_run:
        status = inspect_host(host, scope="user", root=Path.cwd(), home=HOME)
        if status.mcp_configured is True:
            policy = "installed" if status.policy_configured else "missing"
            return "already", f"{status.mcp_detail}  |  policy: {policy}"
        if status.mcp_configured is None:
            # Claude owns its own user registry; we cannot read it from here.
            return "host-owned", status.mcp_detail
        return "would wire", status.mcp_detail
    try:
        result = configure_host(
            host,
            scope="user",
            root=Path.cwd(),
            home=HOME,
            install_policy=install_policy,
        )
    except HostConfigurationError as exc:
        return "skipped", str(exc)
    where = str(result.registration_path) if result.registration_path else "host-owned registry"
    return result.registration, f"{where}  |  policy: {result.policy}"


def probe_native(binary: str) -> bool:
    """True when an unverified host ships its own `mcp add` subcommand."""
    try:
        proc = subprocess.run(  # noqa: S603 - binary resolved by shutil.which
            [binary, "mcp", "add", "--help"], capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def wire_unverified(host: str, binary: str, *, dry_run: bool) -> tuple[str, str]:
    """Probe an unverified host and use only its native registration command."""
    resolved = shutil.which(binary)
    if resolved is None:
        return "absent", "-"
    if not probe_native(binary):
        return "unmapped", "no `mcp add`; config surface not verified"
    argv = [resolved, "mcp", "add", MCP_SERVER_NAME, "--", MCP_SERVER_COMMAND, "--host", host]
    if dry_run:
        return "would wire", " ".join(argv)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)  # noqa: S603
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return "failed", detail[-1][:80] if detail else f"exit {proc.returncode}"
    return "wired", " ".join(argv)


def run(*, dry_run: bool, install_policy: bool) -> int:
    """Wire or inspect the complete known host fleet."""
    rows: list[tuple[str, str, str]] = []
    for host in SUPPORTED_HOSTS:
        if not present(host):
            rows.append((host, "absent", "-"))
            continue
        rows.append((host, *wire_supported(host, dry_run=dry_run, install_policy=install_policy)))

    for host, binary in UNVERIFIED.items():
        rows.append((host, *wire_unverified(host, binary, dry_run=dry_run)))

    width = max(len(row[0]) for row in rows)
    for host, status, detail in rows:
        print(f"{host:<{width}}  {status:<12}  {detail}")
    return 0


def main() -> int:
    """Parse command-line options and run the fleet wiring pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument(
        "--no-policy",
        action="store_true",
        help="register the MCP server only; do not install the memory policy",
    )
    args = parser.parse_args()
    return run(dry_run=args.dry_run, install_policy=not args.no_policy)


if __name__ == "__main__":
    raise SystemExit(main())
