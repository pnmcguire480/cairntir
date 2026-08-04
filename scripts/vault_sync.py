"""Thin wrapper. The real thing is ``cairntir vault-sync``.

This started as a loose script, which is how the Obsidian->Cairntir direction
went missing for four months in the first place: a script nobody runs cannot
drift *loudly*. The logic now lives in :mod:`cairntir.vault`, is reachable as
``cairntir vault-sync``, has a ``--check`` drift gate, and is covered by
``tests/unit/test_vault_sync.py``.

The file stays because it is named by a landed-commitment assertion and because
``python scripts/vault_sync.py`` is muscle memory. It forwards, and it says so.

    python scripts/vault_sync.py [--vault PATH] [--apply | --check]
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Forward to ``cairntir vault-sync`` and return its exit code."""
    from typer.main import get_command

    from cairntir.cli import app

    args = list(sys.argv[1:] if argv is None else argv)
    print("note: this script now forwards to `cairntir vault-sync`.", file=sys.stderr)
    try:
        get_command(app).main(["vault-sync", *args])
    except SystemExit as exit_signal:
        # Click exits the process on completion. This is a library call, so
        # translate that into a return code the caller can act on.
        return int(exit_signal.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
