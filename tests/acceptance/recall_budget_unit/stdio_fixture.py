"""Public isolated transport fixture: real server/backend, synthetic embeddings."""

import asyncio
import sys
from pathlib import Path

from mcp.server.stdio import stdio_server

from cairntir.mcp import server as server_module
from cairntir.mcp.backend import CairntirBackend
from cairntir.memory.embeddings import HashEmbeddingProvider
from cairntir.memory.store import DrawerStore


async def main():
    with DrawerStore(Path(sys.argv[1]), HashEmbeddingProvider(dimension=32)) as store:
        server_module.pending_update_banner = lambda: "PUBLIC UPDATE CANARY " + "U" * 20000
        server = server_module.build_server(CairntirBackend(store))
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
