# Installed question diagnostic amendment

The Windows installed proof at PR129 `db3d431` completed its semantic checks
but failed its final post-shutdown SQLite count with `disk I/O error`. The failed
database was removed by the verifier, so its extended error and recovery state
are unknown. A local source-only owned-process probe passed all original helper
assertions after two abrupt terminations; the exact installed Windows launcher
tree was not reproduced because local `taskkill` was denied.

Version 2 retains the complete original helper as an identical byte prefix and
adds observations around its existing process and assertion execution. It does
not retry, delay, substitute a reader, relocate the final count, or change process
termination. The original exception is rethrown with a diagnostic note. Only
synthetic database file sizes and owned process state are recorded; no environment
or credentials are captured. Diagnostic database copies are not consistent backups.

Four independent controls verify exact original function/assertion preservation,
unchanged successful return and shutdown, and identical SQLite/assertion exception
propagation with no retry or false success. A normal pytest router executes them.
A future hosted pass alone will not establish the original failure's cause.
