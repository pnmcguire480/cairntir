"""Entry point: ``python -m cairntir.daemon``.

Wires the production store (fastembed + platform db path) and the
platform-default spool directory, then runs the capture loop forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from cairntir.config import cairntir_home, db_path
from cairntir.daemon.capture import CaptureDaemon
from cairntir.daemon.spool import spool_dir
from cairntir.memory.embeddings import production_embedding_provider
from cairntir.memory.store import DrawerStore
from cairntir.provenance import TrustLevel, WriteProvenance


async def _amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    store = DrawerStore(
        db_path(),
        production_embedding_provider(),
        provenance=WriteProvenance.create(
            host="daemon",
            capture_path="spool",
            trust=TrustLevel.UNTRUSTED,
        ),
    )
    daemon = CaptureDaemon(store, spool_dir(cairntir_home()))
    await daemon.run()


def main() -> None:
    """Run the capture daemon until SIGINT."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_amain())


if __name__ == "__main__":
    main()
