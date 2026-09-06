"""Local bearer grants, bound by trusted startup and checked at every store boundary."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, NoReturn

from cairntir.durability import WorkflowExecution, WorkflowReceipt
from cairntir.errors import CairntirError
from cairntir.memory.belief import rerank_results
from cairntir.memory.store import DrawerStore, _context_record, _row_to_drawer
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.provenance import TrustLevel, WriteProvenance

_CAPABILITIES = frozenset({"read", "write", "export", "approve", "manage"})
_DENIED = "access denied"


class AccessDenied(CairntirError):  # noqa: N818 - frozen public API
    """The bound grant does not authorize this operation."""


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def startup_token() -> str | None:
    """Read the configured token once; absence alone selects owner mode."""
    configured = os.environ.get("CAIRNTIR_GRANT_FILE")
    if configured is None:
        return None
    try:
        token = Path(configured).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise AccessDenied(_DENIED) from exc
    if not token:
        raise AccessDenied(_DENIED)
    return token


def validate_startup(path: Path, token: str) -> None:
    """Reject an invalid configured grant before store initialization can write."""
    _active(_authoritative_grant(path, _digest(token)))


def _authoritative_grant(path: Path, token_hash: str) -> sqlite3.Row | None:
    try:
        with TemporaryDirectory(prefix="cairntir-grant-") as directory:
            copied = Path(directory) / "grant.db"
            subprocess.run(  # noqa: S603 - fixed interpreter/code and explicit path arguments
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; import sys; "
                    "from cairntir.memory.store import _copy_locked_database; "
                    "_copy_locked_database(Path(sys.argv[1]), Path(sys.argv[2]))",
                    str(path.resolve()),
                    str(copied),
                ],
                capture_output=True,
                check=True,
                timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with closing(sqlite3.connect(copied)) as conn:
                conn.row_factory = sqlite3.Row
                row: sqlite3.Row | None = conn.execute(
                    "SELECT * FROM access_grants WHERE token_hash=?", (token_hash,)
                ).fetchone()
                return row
    except (OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        raise AccessDenied(_DENIED) from exc


def _active(row: sqlite3.Row | None) -> sqlite3.Row:
    if (
        row is None
        or row["revoked"]
        or (row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC))
    ):
        raise AccessDenied(_DENIED)
    return row


def issue_grant(
    owner_store: DrawerStore,
    *,
    scopes: Sequence[dict[str, Any]],
    capabilities: Sequence[str],
    expires_at: datetime | None = None,
    principal: str = "local",
) -> str:
    """Issue an owner-created grant and persist only its token hash."""
    if isinstance(owner_store, ScopedStore):
        raise AccessDenied(_DENIED)
    copied = json.loads(json.dumps(scopes))
    if not isinstance(copied, list) or any(
        not isinstance(scope, dict)
        or set(scope) - {"wing", "rooms", "drawer_ids"}
        or not isinstance(scope.get("wing"), str)
        or not scope["wing"]
        or (
            "rooms" in scope
            and (
                not isinstance(scope["rooms"], list)
                or any(not isinstance(room, str) for room in scope["rooms"])
            )
        )
        or (
            "drawer_ids" in scope
            and (
                not isinstance(scope["drawer_ids"], list)
                or any(type(key) is not int or key <= 0 for key in scope["drawer_ids"])
            )
        )
        for scope in copied
    ):
        raise AccessDenied("invalid grant scope")
    if isinstance(capabilities, str) or not set(capabilities) <= _CAPABILITIES:
        raise AccessDenied("invalid grant capabilities")
    if expires_at is not None and expires_at.tzinfo is None:
        raise AccessDenied("grant expiry must include a timezone")
    token = secrets.token_urlsafe(32)
    with owner_store.transaction():
        owner_store._conn.execute(
            "CREATE TABLE IF NOT EXISTS access_grants ("
            "token_hash TEXT PRIMARY KEY, scopes TEXT NOT NULL, capabilities TEXT NOT NULL, "
            "expires_at TEXT, principal TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)"
        )
        owner_store._conn.execute(
            "INSERT INTO access_grants(token_hash,scopes,capabilities,expires_at,principal) "
            "VALUES (?,?,?,?,?)",
            (
                _digest(token),
                json.dumps(copied),
                json.dumps(sorted(set(capabilities))),
                expires_at.astimezone(UTC).isoformat() if expires_at else None,
                principal,
            ),
        )
    return token


def revoke_grant(owner_store: DrawerStore, token: str) -> None:
    """Revoke future access without changing the underlying evidence."""
    if isinstance(owner_store, ScopedStore):
        raise AccessDenied(_DENIED)
    with owner_store.transaction():
        try:
            owner_store._conn.execute(
                "UPDATE access_grants SET revoked=1 WHERE token_hash=?", (_digest(token),)
            )
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc


def bind_grant(store: DrawerStore, token: str) -> ScopedStore:
    """Bind one validated token to a store without widening its authority."""
    if isinstance(store, ScopedStore) or not isinstance(token, str) or not token.strip():
        raise AccessDenied(_DENIED)
    scoped = ScopedStore(store, _digest(token))
    scoped._grant()
    return scoped


class ScopedStore:
    """A capability-limited store; raw owner SQL is never exposed through this view."""

    def __init__(self, owner: DrawerStore, token_hash: str) -> None:
        """Bind an owner store and a token digest without opening another store."""
        self._owner = owner
        self._token_hash = token_hash
        self._export_depth = 0
        self._import_depth = 0

    def __getattr__(self, name: str) -> NoReturn:
        """Deny unsupported operations instead of exposing owner state."""
        raise AccessDenied(_DENIED)

    def __enter__(self) -> ScopedStore:
        """Enter the bound view without opening another store."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the owner store on context exit."""
        self.close()

    def _grant(self) -> dict[str, Any]:
        try:
            if self._owner._read_snapshot is None:
                row = self._owner._conn.execute(
                    "SELECT * FROM access_grants WHERE token_hash=?", (self._token_hash,)
                ).fetchone()
            else:
                # A private task snapshot is not the authority for live revocation.
                row = _authoritative_grant(self._owner._path, self._token_hash)
        except sqlite3.Error as exc:
            raise AccessDenied(_DENIED) from exc
        row = _active(row)
        return {
            "scopes": json.loads(row["scopes"]),
            "capabilities": json.loads(row["capabilities"]),
        }

    @staticmethod
    def _matches(scope: dict[str, Any], wing: str, room: str | None, key: int | None) -> bool:
        return (
            scope["wing"] == wing
            and (
                "rooms" not in scope
                or (room in scope["rooms"] if room is not None else bool(scope["rooms"]))
            )
            and (
                "drawer_ids" not in scope
                or (key in scope["drawer_ids"] if key is not None else bool(scope["drawer_ids"]))
            )
        )

    def _rows(self, *, capability: str = "read") -> dict[int, sqlite3.Row]:
        grant = self._grant()
        if capability not in grant["capabilities"]:
            raise AccessDenied(_DENIED)
        rows = self._owner._conn.execute("SELECT * FROM drawers ORDER BY id DESC").fetchall()
        allowed = {
            int(row["id"]): row
            for row in rows
            if any(
                self._matches(scope, row["wing"], row["room"], int(row["id"]))
                for scope in grant["scopes"]
            )
        }
        dependencies: dict[int, set[int]] = {}
        for key in allowed:
            try:
                dependencies[key] = {
                    item["target_drawer_id"] for item in self._owner.portable_relations(key)
                }
            except CairntirError:
                dependencies[key] = {-1}
        while True:
            withheld = {key for key in allowed if not dependencies[key] <= allowed.keys()}
            if not withheld:
                return allowed
            for key in withheld:
                del allowed[key]

    def authorize(
        self,
        capability: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        drawer_id: int | None = None,
    ) -> None:
        """Check the live grant capability and any requested scope."""
        grant = self._grant()
        if capability not in grant["capabilities"]:
            raise AccessDenied(_DENIED)
        if drawer_id is not None:
            if drawer_id not in self._rows(capability=capability):
                raise AccessDenied(_DENIED)
        elif wing is not None and not any(
            self._matches(scope, wing, room, None) for scope in grant["scopes"]
        ):
            raise AccessDenied(_DENIED)

    def _creation(self, drawer: Drawer) -> None:
        grant = self._grant()
        if "write" not in grant["capabilities"] or not any(
            "drawer_ids" not in scope and self._matches(scope, drawer.wing, drawer.room, None)
            for scope in grant["scopes"]
        ):
            raise AccessDenied(_DENIED)

    def _references(self, drawer: Drawer) -> None:
        from cairntir.portable import _reference_specs

        for reference in _reference_specs(drawer.model_dump(mode="json")):
            self.authorize("read", drawer_id=reference["source_target_id"])

    def close(self) -> None:
        """Close the owned connection and any private snapshot."""
        self._owner.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write")
        with self._owner.transaction():
            yield
            self.authorize("write")

    def add(
        self, drawer: Drawer, *, provenance: WriteProvenance | None = None, model: str | None = None
    ) -> Drawer:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self._creation(drawer)
        self._references(drawer)
        with self.transaction():
            return self._owner.add(drawer, provenance=provenance, model=model)

    def get(self, drawer_id: int) -> Drawer | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        row = self._rows().get(drawer_id)
        if row is None:
            raise AccessDenied(_DENIED)
        return _row_to_drawer(row)

    def get_provenance(self, drawer_id: int) -> WriteProvenance | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        return self._owner.get_provenance(drawer_id)

    def _list(
        self,
        *,
        capability: str = "read",
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        now = datetime.now(UTC).isoformat()
        rows = [
            row
            for row in self._rows(capability=capability).values()
            if (wing is None or row["wing"] == wing)
            and (room is None or row["room"] == room)
            and (layer is None or row["layer"] == layer.value)
            and (include_expired or row["valid_until"] > now)
        ]
        return [_row_to_drawer(row) for row in (rows if limit is None else rows[:limit])]

    def list_by(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return self._list(
            wing=wing, room=room, layer=layer, limit=limit, include_expired=include_expired
        )

    def list_for_export(
        self,
        *,
        wing: str | None = None,
        room: str | None = None,
        limit: int | None = 100,
        include_expired: bool = False,
    ) -> list[Drawer]:
        """List whole permitted records under the independent export capability."""
        return self._list(
            capability="export", wing=wing, room=room, limit=limit, include_expired=include_expired
        )

    @contextmanager
    def _portable_export(self) -> Iterator[None]:
        self.authorize("export")
        self._export_depth += 1
        try:
            yield
            self.authorize("export")
        finally:
            self._export_depth -= 1

    def _portable_capability(self) -> str:
        return "export" if self._export_depth else "write" if self._import_depth else "read"

    def portable_identity(self, drawer_id: int) -> str:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_identity(drawer_id)

    def portable_source(self, drawer_id: int) -> dict[str, Any]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_source(drawer_id)

    def portable_relations(self, drawer_id: int) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize(self._portable_capability(), drawer_id=drawer_id)
        return self._owner.portable_relations(drawer_id)

    def _portable_lookup(self, identity: str) -> int | None:
        key = self._owner._portable_lookup(identity)
        if key is not None:
            self.authorize(self._portable_capability(), drawer_id=key)
        return key

    def _portable_replace(self, drawer_id: int, identity: str, record: dict[str, Any]) -> None:
        self.authorize("write", drawer_id=drawer_id)
        self._owner._portable_replace(drawer_id, identity, record)

    def _portable_supersedes(self, drawer_id: int, target_id: int) -> None:
        self.authorize("write", drawer_id=drawer_id)
        self.authorize("read", drawer_id=target_id)
        self._owner._portable_supersedes(drawer_id, target_id)

    def context_candidates(
        self, *, wing: str, limit: int | None = None
    ) -> tuple[list[tuple[Drawer, WriteProvenance]], int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = [row for row in self._rows().values() if row["wing"] == wing]
        return [_context_record(row) for row in (rows if limit is None else rows[:limit])], len(
            rows
        )

    def context_relatives(
        self, *, wing: str, drawer_ids: Sequence[int]
    ) -> list[tuple[Drawer, WriteProvenance]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = self._rows()
        if any(key not in rows for key in drawer_ids):
            raise AccessDenied(_DENIED)
        wanted = set(drawer_ids)
        while True:
            connected = {
                key
                for key, row in rows.items()
                if row["wing"] == wing
                and (
                    key in wanted
                    or row["supersedes_id"] in wanted
                    or any(rows[k]["supersedes_id"] == key for k in wanted)
                )
            }
            if connected == wanted:
                return [_context_record(rows[key]) for key in sorted(wanted)]
            wanted = connected

    def context_suppressed_ids(self, drawer_ids: Sequence[int]) -> set[int]:
        """Return visible predecessors displaced by a hidden current successor."""
        visible = self._rows()
        if any(key not in visible for key in drawer_ids):
            raise AccessDenied(_DENIED)
        now = datetime.now(UTC)
        suppressed = set()
        for key in drawer_ids:
            for row in self._owner._conn.execute(
                "SELECT * FROM drawers WHERE supersedes_id=?", (key,)
            ):
                receipt = WriteProvenance.from_json(row["provenance"])
                if (
                    int(row["id"]) not in visible
                    and row["valid_until"] > now.isoformat()
                    and (receipt.valid_from is None or receipt.valid_from <= now)
                ):
                    suppressed.add(key)
        return suppressed

    def context_similarities(self, query: str, drawer_ids: Sequence[int]) -> dict[int, float]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        rows = self._rows()
        if any(key not in rows for key in drawer_ids):
            raise AccessDenied(_DENIED)
        return self._owner.context_similarities(query, drawer_ids)

    def search(
        self,
        query: str,
        *,
        wing: str | None = None,
        room: str | None = None,
        layer: Layer | None = None,
        limit: int = 10,
        rerank_by_belief: bool = True,
        trust: TrustLevel | None = None,
        include_expired: bool = False,
    ) -> list[tuple[Drawer, float]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        drawers = self.list_by(
            wing=wing, room=room, layer=layer, limit=None, include_expired=include_expired
        )
        if trust is not None:
            drawers = [
                drawer
                for drawer in drawers
                if (receipt := self._owner.get_provenance(int(drawer.id or 0))) is not None
                and receipt.trust == trust
            ]
        scores = self.context_similarities(query, [int(drawer.id or 0) for drawer in drawers])
        results = sorted(
            ((drawer, 1.0 - scores[int(drawer.id or 0)]) for drawer in drawers),
            key=lambda item: item[1],
        )[:limit]
        return rerank_results(results) if rerank_by_belief else results

    def update_layer(self, drawer_id: int, layer: Layer) -> None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            self._owner.update_layer(drawer_id, layer)

    def add_anchors(
        self, drawer_id: int, anchors: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.add_anchors(drawer_id, anchors)

    def repair_anchors(self, drawer_id: int) -> list[dict[str, Any]]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read", drawer_id=drawer_id)
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.repair_anchors(drawer_id)

    def reinforce(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.reinforce(drawer_id, amount=amount)

    def weaken(self, drawer_id: int, *, amount: float = 1.0) -> float:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            return self._owner.weaken(drawer_id, amount=amount)

    def stale_ids(
        self, *, older_than: datetime, layer: Layer, wing: str | None = None
    ) -> list[int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return [
            key
            for key, row in self._rows().items()
            if row["layer"] == layer.value
            and (wing is None or row["wing"] == wing)
            and row["last_accessed_at"] is not None
            and row["last_accessed_at"] < older_than.isoformat()
        ]

    def has_content_since(self, *, wing: str, content: str, created_at: datetime) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return any(
            drawer.content == content and drawer.created_at >= created_at
            for drawer in self.list_by(wing=wing, limit=None)
        )

    def wing_exists(self, wing: str, *, include_expired: bool = False) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return bool(self.list_by(wing=wing, limit=1, include_expired=include_expired))

    def content_lengths(
        self, *, wing: str | None = None, include_expired: bool = False
    ) -> list[int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return sorted(
            len(drawer.content)
            for drawer in self.list_by(wing=wing, limit=None, include_expired=include_expired)
        )

    def wing_counts(self, *, include_expired: bool = False) -> dict[str, int]:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return dict(
            Counter(
                drawer.wing for drawer in self.list_by(limit=None, include_expired=include_expired)
            )
        )

    def _workflow_key(self, key: str) -> str:
        return f"grant:{self._token_hash}:{key}"

    def workflow_receipt(self, idempotency_key: str) -> WorkflowReceipt | None:
        """Apply the bound grant to the corresponding drawer-store operation."""
        self.authorize("read")
        return self._owner.workflow_receipt(self._workflow_key(idempotency_key))

    def execute_once(
        self,
        *,
        idempotency_key: str,
        operation: str,
        request: dict[str, Any],
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowExecution:
        """Apply the bound grant to the corresponding drawer-store operation."""
        with self.transaction():
            if operation == "portable.import.v2":
                self._import_depth += 1
            try:
                return self._owner.execute_once(
                    idempotency_key=self._workflow_key(idempotency_key),
                    operation=operation,
                    request=request,
                    action=action,
                )
            finally:
                if operation == "portable.import.v2":
                    self._import_depth -= 1

    def _procedure_record(self, drawer_id: int) -> dict[str, Any] | None:
        self.authorize("read", drawer_id=drawer_id)
        record = self._owner._procedure_record(drawer_id)
        if record is not None and not self._registry_ids(record) <= self._rows().keys():
            raise AccessDenied(_DENIED)
        return record

    @staticmethod
    def _registry_ids(value: dict[str, Any]) -> set[int]:
        names = {
            "drawer_id",
            "root_id",
            "supersedes_id",
            "evaluation_id",
            "procedure_id",
            "current_id",
            "evidence_id",
            "baseline_prediction_id",
            "baseline_observation_id",
            "candidate_prediction_id",
            "candidate_observation_id",
            "evidence_ids",
            "counterexample_ids",
        }
        result: set[int] = set()

        def visit(item: Any, key: str = "") -> None:
            if isinstance(item, dict):
                for name, child in item.items():
                    visit(child, name)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    visit(child, key)
            elif key in names and type(item) is int and item > 0:
                result.add(item)

        visit(value)
        return result

    def _procedure_records(self, wing: str | None = None) -> list[dict[str, Any]]:
        visible = self._rows()
        return [
            record
            for record in self._owner._procedure_records(wing)
            if self._registry_ids(record) <= visible.keys()
        ]

    def is_registered_procedure(self, drawer_id: int) -> bool:
        """Apply the bound grant to the corresponding drawer-store operation."""
        return self._procedure_record(drawer_id) is not None

    def _register_procedure(
        self, drawer_id: int, *, root_id: int, parent_id: int | None, payload: dict[str, Any]
    ) -> None:
        self.authorize("write", drawer_id=drawer_id)
        for key in (root_id, parent_id):
            if key is not None:
                self.authorize("read", drawer_id=key)
        with self.transaction():
            self._owner._register_procedure(
                drawer_id, root_id=root_id, parent_id=parent_id, payload=payload
            )

    def _procedure_evaluation(self, drawer_id: int) -> dict[str, Any] | None:
        self.authorize("read", drawer_id=drawer_id)
        record = self._owner._procedure_evaluation(drawer_id)
        if record is not None and not self._registry_ids(record) <= self._rows().keys():
            raise AccessDenied(_DENIED)
        return record

    def _register_procedure_evaluation(self, drawer_id: int, payload: dict[str, Any]) -> None:
        self.authorize("write", drawer_id=drawer_id)
        with self.transaction():
            self._owner._register_procedure_evaluation(drawer_id, payload)
