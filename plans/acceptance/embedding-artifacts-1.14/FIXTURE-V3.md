# Explicit v3 workflow and normal-diagnostics correction

The first candidate run preserved in candidate-first.json/log passed every
original artifact/relative-cache case. Its supplementary workflow exposed that
CliRunner keeps owner CLI backends alive in one Python process; the get/failed
recall command therefore left SQLite WAL handles held when that same process
invoked reindex. Normal user CLI invocations exit between commands and release
those OS handles. This is a test lifecycle mismatch, not evidence of a user CLI
failure. The v3 CLI helper now runs the actual Typer app in a fresh child Python
process for every command, with only synthetic FastEmbed/Hub loader APIs. It
receives constructor paths/local-only flags and fault counts in explicit synthetic
JSON receipts. Actual doctor, raw get, denied recall, backed-up rebuild, final
doctor and successful recall all execute the product app/store/backend. No runtime
methods or outcomes are replaced. All original workflow assertions stay intact.

Case 31's normal embed failure created the existing mcp.log diagnostic. The
governing ORIGINAL-CONTRACT.md forbids bootstrap after pinned-asset loss and
requires changed/missing bytes rejection before loading; its no-write constraint
applies to offline identity/inspection and readonly embedding. It does not prohibit
normal embed's existing error log. The v1/v2 whole-root equality for normal embed
was an overconstraint. This explicit versioned acceptance correction compares
the complete synthetic cache for normal embed, retains whole-root equality for
readonly embedding, and keeps identity, typed error and zero acquisition/model
construction assertions. No runtime repair is justified by that diagnostic log.

The original freeze, v2 fixture, initial candidate failures and original 25+2
tests remain unchanged. The v3 manifest hashes this amendment, subprocess driver,
v3 supplement and runner. Total case count remains 35. No heavy tests/model/network
are authorized. CLI subprocesses have 15-second individual timeouts; all fixture
input/receipts/caches are beneath packet/runs, with synthetic user home/cwd and
blocked socket/Hub acquisition. Independent review reserve remains untouched.
