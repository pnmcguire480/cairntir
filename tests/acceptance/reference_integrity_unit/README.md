# Reference integrity behavior controls

These synthetic scenarios exercise composed 512-reference boundaries, overflow
rollback, reversible contextual supersession, scoped reference creation, hidden
transitive dependencies, malformed references, SQL lookup budgets and fresh
authority checks. They use temporary SQLite stores and a deterministic integer
evaluator with explicitly synthetic operator approval.

The composed-reference packet retains both owner and scoped authority modes:
seven test functions produce 30 cases, not 15. Scoped creation adds 12 cases
and scoped closure adds 19, for 61 cases across 25 functions. Case counts here
come from unchanged parameter declarations; execution is recorded separately.

Both scoped modules import the same original synthetic snapshot helper through
an ordinary package import. No historical loader, frozen qualification record,
private corpus, platform inventory or model is included. These are portable
behavior controls, not renewed historical acceptance or field qualification.
