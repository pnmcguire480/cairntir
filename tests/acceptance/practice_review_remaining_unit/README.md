# Remaining practice review controls

This package collects exactly the remaining 53 original R18 cases: core23,
additional7, immutable receipt sequence1, completeness16, closure-additional5
and one explicitly selected RecursiveClosure method. The earlier eight edge
cases are excluded, and RecursiveClosure does not recollect its inherited16.

Original classes live in non-test case modules. The sole pytest collector imports
modules and parameterizes the selected unittest cases, preserving their original
bodies, assertions, setup and helpers. Unchanged public edge fixtures provide the
original Hash32 temporary SQLite stores and inert Runner/Harness. No private
packet or sealed execution environment is needed at runtime.

The adapter explicitly adds a finally call to doCleanups after case.debug, so a
failed assertion cannot leak the original socket patch or temporary store. A
False cleanup result raises RuntimeError, retaining any original exception as
context. This is new adapter cleanup protection, not a new product criterion.

Actual local issue_grant/bind_grant cases retain that route. Completeness and
closure cases deliberately inject _grant and qualify scope/closure behavior,
not persisted-token authentication. Original fixture guards apply during setup
and registered cleanup, not protected startup, model or native-host custody.

Only ordinary imports, formatting and narrow lint annotations change original
scenario source. Historical results remain separate. The author ran static
checks only; root independently reviews before one execution. No coverage gain
or roadmap completion is inferred from source restoration.
