"""Background daemon: auto-capture conversation state into drawers without ceremony.

Anything that wants to persist a drawer simply drops a JSON file in the
spool directory (see :mod:`cairntir.daemon.spool`). The
:class:`CaptureDaemon` polls the spool, persists each file as a drawer,
and quarantines anything malformed.
"""

from __future__ import annotations

from cairntir.daemon.capture import CaptureDaemon, DaemonStats
from cairntir.daemon.spool import (
    parse_capture,
    pending_files,
    quarantine,
    spool_dir,
    write_capture,
)

__all__ = [
    "CaptureDaemon",
    "DaemonStats",
    "parse_capture",
    "pending_files",
    "quarantine",
    "spool_dir",
    "write_capture",
]
