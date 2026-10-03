# Independent grant-fixture correction and negative-control strengthening

Version 2 source/freeze remain under history/v2. Its exact baseline and candidate
round-0 logs/XML remain unchanged. Candidate result: 4 failed, 38 passed, 1
Windows symlink privilege skip, and 21 subtests passed. Two product failures
reproduce false durable acknowledgements inside enclosing transactions.

The other two failures happened before the intended scoped operations: the
fixture supplied `room`, while the public grant contract accepts `rooms` as a
list. Version 3 fixes only this independently owned input to `rooms:["notes"]`;
scope and assertions are unchanged. Version 2 baseline's three negative embedding
cases also passed absence of obsidian-sync because any nonzero exit was accepted.
Version 3 strengthens them to require an embedding-specific error from the CLI.
This preserves all assertions and prevents the absent-command false positive.

No original bytes or candidate product assertions change. Version 3 keeps 43
pytest cases, including mandatory original Node v3 and actual plugin routing.
This amendment is frozen separately before the product repair verification.
