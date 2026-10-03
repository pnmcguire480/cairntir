# Fixture-only v2 amendment

The initial frozen 35-case baseline completed in 17.39 seconds, with the expected
missing identity/pinning failures and three Windows symlink privilege skips.
Supplementary case 28 also raised Windows file-in-use during temporary-directory
cleanup: its fixture used sqlite3.Connection as a transaction context, which does
not close the connection, and the assertion traceback retained that open handle.

The original freeze, test, runner and baseline evidence remain intact. The v2 test
changes exactly the fixture's import of contextlib.closing and the SQLite context
to `with closing(sqlite3.connect(database)) as conn, conn:`. No assertion, model,
runtime, case count or acceptance semantics changes. CLI diagnostic traces get a
`-v2-cli.json` suffix to keep evidence generations distinct. The v2 runner selects
the versioned supplement and verifies FIXTURE-V2-FREEZE.json. All original 25 cases
and both relative-cache cases remain byte-for-byte unchanged.

The active synthetic command substitutes `run_acceptance_v2.py` for the initial
runner and uses a new report filename. The original baseline remains authoritative
pre-implementation evidence; this fixture repair does not consume a product
repair round or the independent adversarial review reserve.
