# Integration Guide — How to put Cairntir behind your own tool

This guide is for developers embedding Cairntir as a library inside
another application. If you are using Cairntir as a Claude Code
plugin, you want [how-to-use.md](how-to-use.md) instead.

## The 30-second version

```python
from cairntir import Drawer, Layer, Store
from cairntir.impl import DrawerStore, HashEmbeddingProvider

# Open a store. Any path; any embedder that satisfies EmbeddingProvider.
store: Store = DrawerStore(
    "/path/to/cairntir.db",
    HashEmbeddingProvider(dimension=384),
)

# Write a verbatim drawer.
saved = store.add(Drawer(
    wing="my-app",
    room="decisions",
    content="we picked postgres over sqlite for the live tier",
    layer=Layer.ESSENTIAL,
    claim="postgres scales past 10M rows for our workload",
    predicted_outcome="p99 read latency stays under 50ms at target volume",
))

# Search.
hits = store.search("which database did we pick", wing="my-app", limit=5)
for drawer, distance in hits:
    print(f"{distance:.3f}  {drawer.content}")

store.close()
```

That's it. Everything else is variations on this theme.

## The three surfaces you'll touch

### 1. The protocol surface (`cairntir.*`)

The stable seam. Import from `cairntir` itself — never from submodules
— if you want your code to survive future releases without refactors.
Every name in `cairntir.__all__` is covered by the
[deprecation policy](deprecation-policy.md).

The core protocols you'll reference:

- **`Store`** — the memory backend. Implement this to plug a custom
  backend (Redis, Postgres, a cloud-hosted vector DB) into the rest
  of Cairntir.
- **`EmbeddingProvider`** — vector embeddings. Implement this to swap
  the default sentence-transformers model for whatever you already
  have running.
- **Reason-loop ports** (`HypothesisProposer`, `ExperimentRunner`,
  `BeliefStore`, `MemoryGateway`) — the four seams of the library
  Reason loop. Implement these for tool-driven reasoning without
  touching the default memory layer.

### 2. The concrete namespace (`cairntir.impl.*`)

The default implementations. These are supported but **not** covered
by the deprecation policy — Cairntir reserves the right to rename
`DrawerStore` to `SQLiteVecDrawerStore` in a minor release if that
makes the library better. If you import from `cairntir.impl.*`, you
are opting into upgrade friction in exchange for convenience.

Rule of thumb: use `cairntir.impl.*` to *construct* things, use
`cairntir.*` to *type-annotate* things.

```python
from cairntir import Store
from cairntir.impl import DrawerStore, HashEmbeddingProvider

def build_store(path: str) -> Store:  # Store is the protocol
    return DrawerStore(path, HashEmbeddingProvider())  # impl is concrete
```

### 3. The portable format (`cairntir.portable`)

For moving drawers between stores (or between machines, or offline,
or through gossip). Covered by the policy at the envelope-format
level: the JSON shape of an envelope is stable within a major
version. See [how-to-use.md](how-to-use.md) for CLI use.

## Implementing a custom `Store`

`Store` is a `runtime_checkable` `Protocol`. No inheritance required
— any object that provides the methods will pass `isinstance(x,
Store)`.

```python
from datetime import datetime
from cairntir import Drawer, Layer, Store, MemoryStoreError

class MyRedisStore:
    """Toy example. Not production-ready."""

    def __init__(self, redis_client: object) -> None:
        self._r = redis_client
        self._next_id = 1

    def add(self, drawer: Drawer) -> Drawer:
        drawer_id = self._next_id
        self._next_id += 1
        # ... persist drawer.model_dump() under drawer_id ...
        return drawer.model_copy(update={"id": drawer_id})

    def get(self, drawer_id: int) -> Drawer | None:
        # ... fetch by id, return None if missing ...
        ...

    def list_by(self, *, wing=None, room=None, layer=None, limit=100):
        ...

    def search(self, query, *, wing=None, room=None, limit=10, rerank_by_belief=True):
        ...

    def update_layer(self, drawer_id: int, layer: Layer) -> None:
        ...

    def reinforce(self, drawer_id: int, *, amount: float = 1.0) -> float:
        ...

    def weaken(self, drawer_id: int, *, amount: float = 1.0) -> float:
        ...

    def stale_ids(self, *, older_than: datetime, layer: Layer, wing=None):
        ...

    def close(self) -> None:
        ...
```

### Run the contract test suite against your impl

The v1.0 promise is that every `Store` impl passes
`tests/contract/test_store_contract.py`. To run the suite against
your backend, add a factory to the parametrized list:

```python
# In your own test file:
from cairntir import Store
from my_package import MyRedisStore

def _my_store_factory(tmp_path):
    return MyRedisStore(redis_client=start_ephemeral_redis(tmp_path))

# Then parametrize the same fixture shape the suite uses.
```

Every failing invariant is a bug in your backend, not a bug in the
suite. The invariants are the minimum the library assumes; breaking
them will cause higher-level code (`consolidate_room`, `ReasonLoop`,
the reranker) to misbehave in subtle ways.

## Implementing a custom `EmbeddingProvider`

```python
from collections.abc import Sequence
from cairntir import EmbeddingProvider

class MyOpenAIEmbeddings:
    @property
    def dimension(self) -> int:
        return 1536  # text-embedding-3-small

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # ... call OpenAI, return one vector per input ...
        ...
```

Pass an instance to `DrawerStore`:

```python
store = DrawerStore("/path/to/db", MyOpenAIEmbeddings())
```

All the existing contract and property tests will run against your
embedder through the store.

## Wiring the Reason loop

`ReasonLoop` is under `cairntir.impl` because it's a concrete
orchestration. The four ports it takes (`HypothesisProposer`,
`ExperimentRunner`, `BeliefStore`, `MemoryGateway`) are protocols in
`cairntir.*`.

```python
from cairntir import (
    BeliefStore,
    ExperimentRunner,
    Hypothesis,
    HypothesisProposer,
    MemoryGateway,
    Outcome,
)
from cairntir.impl import ReasonLoop

class ClaudeProposer:
    """Hypothesis proposer backed by the Claude API."""
    def propose(self, *, question: str, wing: str, room: str) -> Hypothesis:
        # ... call Claude, return a Hypothesis ...
        ...

class ShellRunner:
    """Experiment runner that executes a bash command."""
    def run(self, hypothesis: Hypothesis) -> Outcome:
        # ... run the command, decide success ...
        ...

class StoreBackedBeliefs:
    """BeliefStore wrapper around a cairntir.Store."""
    def __init__(self, store: Store) -> None:
        self._store = store

    def reinforce(self, drawer_id: int, *, amount: float) -> float:
        return self._store.reinforce(drawer_id, amount=amount)

    def weaken(self, drawer_id: int, *, amount: float) -> float:
        return self._store.weaken(drawer_id, amount=amount)

class StoreBackedMemory:
    """MemoryGateway wrapper around a cairntir.Store."""
    def __init__(self, store: Store) -> None:
        self._store = store

    def remember(self, drawer: Drawer) -> int:
        saved = self._store.add(drawer)
        assert saved.id is not None
        return saved.id

    def recall(self, query: str, *, wing: str, room: str | None = None, limit: int = 5):
        return [d for d, _ in self._store.search(query, wing=wing, room=room, limit=limit)]

loop = ReasonLoop(
    proposer=ClaudeProposer(),
    runner=ShellRunner(),
    beliefs=StoreBackedBeliefs(store),
    memory=StoreBackedMemory(store),
)
update = loop.step(question="should we rate-limit this endpoint?", wing="my-app", room="decisions")
print(update.mass_change, update.delta)
```

The loop writes two drawers per `step()`: a prediction drawer up
front and an observation drawer that `supersedes_id`s it after the
runner reports back. Everything is verbatim, nothing is summarized.

## Migrations

When a new Cairntir minor release bumps the on-disk schema, the
migration runs automatically the first time you open the store:

```python
store = DrawerStore("/path/to/existing.db", HashEmbeddingProvider())
# Migration ran here. PRAGMA user_version is now the current SCHEMA_VERSION.
```

To apply migrations deliberately (e.g. in a deploy script) without
going through `DrawerStore`, use the CLI:

```bash
cairntir migrate /path/to/existing.db
cairntir migrate --check /path/to/existing.db  # dry run, reports version only
```

Migrations are always forward-only. Downgrading to an older library
version against an already-migrated database is **not** supported —
the contract is that every minor release reads every prior schema,
not that every schema reads every library version.

## What you should not do

- **Do not reach into `cairntir.memory.*` directly.** It is still the
  canonical source for the concrete impls, but the stable import
  paths are `cairntir.*` (protocols) and `cairntir.impl.*` (concrete).
- **Do not catch `Exception`** around Cairntir calls. Every error
  Cairntir raises is a subclass of `CairntirError`. Catch that (or a
  more specific subclass) and let everything else propagate.
- **Do not mutate `Drawer` instances.** They are frozen pydantic
  models. Use `drawer.model_copy(update={...})` if you need a
  modified copy.
- **Do not rely on `id` values across stores.** A drawer's id is
  local to the store that assigned it. If you export and re-import,
  the new store will assign fresh ids. Use `content_hash` from the
  portable format for cross-store identity.

## Where to go from here

- [manifesto.md](manifesto.md) — why Cairntir exists
- [concept.md](concept.md) — the three ingredients
- [deprecation-policy.md](deprecation-policy.md) — what "stable"
  actually means
- [how-to-use.md](how-to-use.md) — the Claude Code plugin path
- `tests/contract/test_store_contract.py` — the invariants your
  custom `Store` must satisfy
