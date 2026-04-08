"""Entry point: ``python -m cairntir.daemon``.

Wires the production store (sentence-transformers + platform db path) and
the platform-default spool directory, then runs the capture loop forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from cairntir.config import cairntir_home, db_path
from cairntir.daemon.capture import CaptureDaemon
from cairntir.daemon.spool import spool_dir
from cairntir.memory.embeddings import SentenceTransformerProvider
from cairntir.memory.store import DrawerStore


async def _amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    store = DrawerStore(db_path(), SentenceTransformerProvider())
    daemon = CaptureDaemon(store, spool_dir(cairntir_home()))
    await daemon.run()


def main() -> None:
    """Run the capture daemon until SIGINT."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_amain())


if __name__ == "__main__":
    main()
