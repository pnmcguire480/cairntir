"""Provision model caches and an explicitly isolated corpus before offline evaluation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from cairntir.memory.embeddings import FastEmbedProvider, SentenceTransformerProvider
from cairntir.memory.store import DrawerStore
from cairntir.memory.taxonomy import Drawer


def main() -> None:
    """Prepare a fresh evaluation home; never open an existing memory database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    database = home / "cairntir.db"
    if database.exists():
        parser.error(f"evaluation home already contains a database: {database}")
    os.environ["CAIRNTIR_HOME"] = str(home)
    home.mkdir(parents=True, exist_ok=True)
    provider = FastEmbedProvider()
    provider.embed(["provision production model"])
    SentenceTransformerProvider().embed(["provision legacy evaluation model"])
    with DrawerStore(database, provider) as store:
        store.add(
            Drawer(
                wing="eval-fixture",
                room="synthetic",
                content="The project stores original evidence in SQLite. " * 60,
            )
        )
    print("Evaluation models provisioned; corpus-window gate uses one synthetic drawer.")


if __name__ == "__main__":
    main()
