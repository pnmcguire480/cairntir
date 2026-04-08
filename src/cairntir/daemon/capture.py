"""The auto-capture daemon loop.

:class:`CaptureDaemon` polls a spool directory at a fixed interval, turns
each pending file into a drawer, and persists it via a
:class:`~cairntir.memory.store.DrawerStore`. Malformed files are quarantined
instead of crashing the loop.

Running ``python -m cairntir.daemon`` wires the production store and the
platform-default spool path and runs forever. Tests drive :meth:`tick`
directly so they don't need to spin up the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cairntir.daemon.spool import parse_capture, pending_files, quarantine
from cairntir.errors import CairntirError

if TYPE_CHECKING:
    from cairntir.memory.store import DrawerStore

_LOG = logging.getLogger("cairntir.daemon")
_DEFAULT_INTERVAL = 0.5


@dataclass
class DaemonStats:
    """Counters updated by :meth:`CaptureDaemon.tick`."""

    processed: int = 0
    failed: int = 0
    quarantined: list[Path] = field(default_factory=list)


class CaptureDaemon:
    """Poll a spool directory and persist captured drawers."""

    def __init__(
        self,
        store: DrawerStore,
        spool: Path,
        *,
        poll_interval: float = _DEFAULT_INTERVAL,
    ) -> None:
        """Wire the daemon to an existing store and spool directory."""
        self._store = store
        self._spool = spool
        self._poll_interval = poll_interval
        self._stats = DaemonStats()
        self._stop = asyncio.Event()

    @property
    def stats(self) -> DaemonStats:
        """Return the current stats counters (live reference)."""
        return self._stats

    def tick(self) -> int:
        """Process every pending spool file once. Returns the number persisted."""
        processed_this_tick = 0
        for path in pending_files(self._spool):
            try:
                drawer = parse_capture(path)
            except CairntirError as exc:
                quarantine(path, self._spool, str(exc))
                self._stats.failed += 1
                self._stats.quarantined.append(path)
                _LOG.warning("quarantined spool file %s: %s", path.name, exc)
                continue
            try:
                self._store.add(drawer)
            except CairntirError as exc:
                quarantine(path, self._spool, f"store.add failed: {exc}")
                self._stats.failed += 1
                self._stats.quarantined.append(path)
                _LOG.error("store.add failed for %s: %s", path.name, exc)
                continue
            path.unlink(missing_ok=True)
            self._stats.processed += 1
            processed_this_tick += 1
        return processed_this_tick

    def request_stop(self) -> None:
        """Ask the async run loop to exit after the current tick."""
        self._stop.set()

    async def run(self) -> None:
        """Poll forever until :meth:`request_stop` is called."""
        _LOG.info("cairntir daemon watching %s", self._spool)
        while not self._stop.is_set():
            self.tick()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except TimeoutError:
                continue
