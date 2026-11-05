# Actual resource controls

These 53 existing Q05 cases execute real SQLite workloads, cProfile/tracemalloc,
offline wheel builds and Ruff security scans. They retain the original limits,
deliberately incorrect controls and byte-bound producer, subject and policy.

Run `python -B scripts/provision_q05.py --output NEW_DIRECTORY` first, then set
`CAIRNTIR_Q05_PLATFORM` to its `platform.json`. Preparation uses the current
Python, installed Ruff and available uv, six exact public build-wheel inputs,
and an owned toolchain. Missing or changed preparation fails before dispatch.
Use `PYTHONDONTWRITEBYTECODE=1` and a fresh `-X pycache_prefix=NEW_CACHE` for
preparation and tests so the selected shared runtime/cache stays unchanged.

The local source run passed all 53 cases; 17 independent preparation controls
also passed. Hosted cross-platform results remain separate. The selected base
runtime is shared and read-only; no whole-machine or protected-custody claim
is made. Historical reconstructed wheel hashes and qualification are not reused.
