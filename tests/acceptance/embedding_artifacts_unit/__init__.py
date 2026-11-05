"""Pinned embedding artifact tests carried from draft PR 125.

The tests swap loader modules with ``patch.dict(sys.modules)``, which also unloads
anything first imported during the patch. Loading the CLI and MCP server here keeps
their third-party imports whole between tests.
"""

import cairntir.cli
import cairntir.mcp.server  # noqa: F401
