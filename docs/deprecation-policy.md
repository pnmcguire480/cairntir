# Deprecation Policy

Cairntir's v1.0 contract is a promise: the protocol surface re-exported
from `cairntir.__init__` will not shift underneath you without warning.
This document defines *warning* and *without*.

## What is covered

Everything in `cairntir.__all__` is **public** and covered by this
policy:

- Protocols: `Store`, `EmbeddingProvider`, `HypothesisProposer`,
  `ExperimentRunner`, `BeliefStore`, `MemoryGateway`
- Frozen value types: `Drawer`, `Layer`, `Hypothesis`, `Experiment`,
  `Outcome`, `BeliefUpdate`
- Typed exceptions: every class defined in `cairntir.errors`, plus
  `CairntirDeprecationWarning`
- `__version__`

Anything under `cairntir.impl.*` (`DrawerStore`,
`HashEmbeddingProvider`, `SentenceTransformerProvider`, `Retriever`,
`ReasonLoop`, `SCHEMA_VERSION`) is **not** covered. These concrete
implementations reserve the right to change between minor releases.
If you want stability, depend on the protocol surface.

Anything with a leading underscore — module, attribute, or method —
is **not** covered, full stop.

## What counts as a breaking change

A change to a public name is **breaking** if it would cause any of the
following in a caller that was previously correct:

1. An `ImportError` — the name no longer exists, was renamed, or moved
   to a different module.
2. A `TypeError` at the call site — a method's positional or
   keyword-only signature changed in an incompatible way.
3. A `TypeError` or silent misbehavior at the value boundary — a field
   on a frozen dataclass was removed, renamed, or changed type.
4. An exception that was previously a subclass of `CairntirError` is
   no longer a subclass, or vice versa.
5. A protocol grew a new required method that existing impls do not
   provide.

Adding a new optional parameter with a safe default, adding a new
method to an impl class (not the protocol), adding a new value to an
open enum, or adding a new exception subclass is **not** breaking.

## The warning window

Every breaking change to a public surface must:

1. **Land a deprecation in a minor release.** In that release, the old
   surface still works but emits a `CairntirDeprecationWarning` on use.
   The warning message must name the replacement and link to a
   migration note in `CHANGELOG.md`.
2. **Stay available for at least two minor releases** after the
   deprecation lands. Example: if a method is deprecated in `1.3.0`,
   it cannot be removed before `1.5.0`.
3. **Be removed only in a minor or major release**, never a patch
   release.

Patch releases (`1.4.0 → 1.4.1`) must not introduce, remove, or
retarget any public name. Patches are bugfixes and internal cleanups
only.

## How to filter the warning

The warning is a `DeprecationWarning` subclass, so Python's standard
filtering applies:

```python
import warnings
from cairntir import CairntirDeprecationWarning

# Fail loudly on any Cairntir deprecation — recommended for CI.
warnings.filterwarnings("error", category=CairntirDeprecationWarning)
```

Filtering narrowly on `CairntirDeprecationWarning` (rather than
`DeprecationWarning`) lets you opt in to Cairntir's warnings without
touching the noise from other libraries.

## What the project owes you when deprecating something

When a deprecation lands:

- A `CairntirDeprecationWarning` at every call site of the old
  surface, with `stacklevel=2` so the warning points at your code,
  not ours.
- A `CHANGELOG.md` entry under the deprecating release that names
  the old surface, the replacement, and the earliest release in
  which the old surface may be removed.
- Documentation updates: the new surface documented, the old
  surface marked with a `.. deprecated::` note that repeats the
  migration guidance.
- If the migration is mechanical, a `cairntir` CLI command or a
  `sed` recipe in the CHANGELOG entry.

## What gets deprecated vs. what gets removed silently

| Change                                                | Policy                     |
|-------------------------------------------------------|----------------------------|
| Renaming a public protocol method                     | Two-minor deprecation      |
| Adding a required method to a public protocol        | Two-minor deprecation      |
| Removing a public field from a frozen dataclass      | Two-minor deprecation      |
| Changing the type of a public field                  | Two-minor deprecation      |
| Moving a name out of `cairntir.__all__`              | Two-minor deprecation      |
| Renaming / removing a name under `cairntir.impl.*`    | Allowed in any minor       |
| Changing internal SQL schema layout                   | Allowed in any minor       |
| Changing the `HashEmbeddingProvider` output           | Allowed in any minor       |
| Fixing an incorrect type annotation                   | Patch release              |
| Fixing a docstring                                    | Patch release              |

## Versioning

Cairntir uses three-segment [Semantic Versioning](https://semver.org/)
numbering with one deliberate, documented deviation: **a deprecated
public surface may be removed in a MINOR release** once it has served
the two-minor warning window above. Strict SemVer would require a MAJOR
bump for that removal. Cairntir does not take one.

The deviation is safe because the warning window does the work a major
bump would otherwise do. Nothing public disappears without a
`CairntirDeprecationWarning`, a named replacement, a `CHANGELOG.md`
migration note, and at least two minor releases of overlap. You will
never be surprised; you will be told, in code and in the changelog,
with time to move.

What `1.x.y` therefore guarantees is **not** permanent surface
compatibility with `1.0.0`. It guarantees the *process*: no public name
is removed or retargeted without the full window. Pin a minor version
and read the changelog before upgrading it, exactly as you would for
any dependency.

`2.0.0` is **reserved** for a revolutionary change in what Cairntir is,
not for an accumulation of breaking changes. It may never happen, and
the minor segment is unbounded — `1.24.0` is an ordinary version. See
[Release Cadence](release-cadence.md) for the full versioning rules and
the reasoning behind the reservation.

## Disputes

If you hit a change you think violates this policy, open an issue
with a minimal reproduction. The project treats policy violations as
bugs — the fix is either to restore the old surface and land a proper
deprecation, or (if the policy was genuinely ambiguous) to clarify
this document.
