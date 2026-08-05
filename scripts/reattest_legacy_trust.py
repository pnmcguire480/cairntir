r"""Re-attest the v6-migration drawers from 'untrusted' to 'legacy_migrated'.

WHY
The v6 migration (2026-07-29) stamped every pre-provenance drawer with a
receipt whose trust is 'untrusted' -- a migration artifact, not a judgement.
It renders a security banner over drawers that are simply old, which trains
every agent to ignore the banner. This retires that stamp on exactly those
rows and no others, per P1 item 4 of plans/2026-08-04-honest-and-whole.md.

THE RULE THIS ENFORCES
Only receipts that ARE the migration stamp move (host='legacy', capture_path=
'pre-v6-migration'). 'untrusted' is also the default for new writes, so a
genuinely untrusted drawer must never be swept up. The re-attest touches trust
metadata only -- no content moves, no embedding is recomputed.

USAGE
Dry run by default; honours CAIRNTIR_HOME so it can be rehearsed against a
copy of the store before it touches the live one::

    python scripts/reattest_legacy_trust.py
    python scripts/reattest_legacy_trust.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    """Report (and optionally apply) the legacy-trust re-attestation."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = ap.parse_args()

    from cairntir.config import db_path
    from cairntir.memory.embeddings import production_embedding_provider
    from cairntir.memory.store import DrawerStore

    print(f"CAIRNTIR_HOME = {os.environ.get('CAIRNTIR_HOME') or '(default = LIVE STORE)'}")
    print(f"target db     = {db_path()}")
    print(f"mode          = {'APPLY' if args.apply else 'DRY RUN'}\n")

    store = DrawerStore(db_path(), production_embedding_provider())
    pending = store.legacy_migration_drawer_ids()
    print(f"drawers carrying the v6-migration 'untrusted' stamp: {len(pending)}")

    if not args.apply:
        print("\n--- DRY RUN, nothing written ---")
        return 0

    if not pending:
        print("nothing to re-attest; store already clean")
        return 0

    reattested = store.reattest_legacy_trust()
    store.checkpoint()
    print(f"\nre-attested {len(reattested)} drawer(s) to 'legacy_migrated'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
