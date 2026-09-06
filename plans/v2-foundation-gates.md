# Foundation local gate evidence

Coordinator: `/root`. Windows / Python 3.11.9. These supporting checks accompany
the [independent acceptance result](v2-foundation-result.md); they do not replace
its frozen tests. Commands, source/artifact hashes and measurements are in
[the gate record](v2-foundation-gates.json).

| Gate | Result |
| --- | --- |
| Full regression on final runtime | [870 passed](v2-foundation-regression.txt), seven slow cases deselected; 83.56% branch-inclusive coverage. |
| Complete offline model evaluation | [Seven passed](v2-foundation-eval.txt), including production and legacy retrieval models, tokenizer window/tail behavior and frozen model boundaries. |
| Lint, formatting, strict typing | PASS: 133 formatted files, 55 source files checked. |
| Integrity checks | PASS: no silent exceptions, 157 commitments, nine seams, maintained documentation links. |
| Dependency and release checks | PASS: 134 locked registry packages, no advisory findings; released tags verified against PyPI. |
| Build | Locked offline development sync, strict documentation build, wheel and source archive PASS. |
| Built-wheel transport | Real CLI and stdio MCP return identical task JSON; 21 tools, abstention and explicit task/recovery incompatibility verified. |
| Full response ceiling | CLI: 1,553 characters including newline. Serialized MCP `CallToolResult`: 1,851. Requested ceiling: 8,192. |
| Isolated doctor gate | Four drawers/four production-space vectors, dimension 512, SQLite integrity OK, no foreign-key errors. |
| Demo | 7,720 full-history characters → 2,899 selected, a 62.45% synthetic payload reduction. Final HTML matches the visually inspected preview byte for byte. |

The complete regression ran again after the final snapshot error-reporting
correction. Model evaluation used copied local caches with networking disabled.
The corpus-window test measured four synthetic drawers in an isolated home;
it makes no assertion about the user's production corpus. No vault was supplied
to doctor, so vault drift was not evaluated.

The first transport harness incorrectly expected the MCP `isError` flag.
Cairntir's existing transport returns a `[cairntir error]` text receipt. The
harness was corrected to check the exact task/recovery incompatibility receipt;
no runtime or frozen test was changed for that correction.

## Read-only boundary

Cold task CLI opens a private snapshot, with the database and WAL/journal copied
while holding SQLite's database locking region exclusively in a separate
process. It copies through the locked descriptor, then performs recovery only
on the private copy. Busy clients produce a typed retry error, including idle
WAL clients retaining a shared database lock. This follows SQLite's
[WAL locking description](https://sqlite.org/walformat.html) and
[process-scoped POSIX lock warning](https://sqlite.org/howtocorrupt.html).

Already-open MCP task reads preserve persisted evidence, provenance, access
state and diagnostic logs. SQLite may maintain shared-memory read-lock
bookkeeping. The original acceptance contract excludes those existing VFS
sidecars; the cold CLI supplement separately checks source-file and directory
timestamps and hashes. Native Windows execution and independent source review
passed. Linux/macOS execution remains a CI gate before landing.

The demo is a synthetic local backend evaluation. It does not measure commercial
hosts, billed tokens or general task success. No dependency, production
installation, database migration, license, version, tag or publication changes
were made.
