# Practice governance controls

These 21 original R17 unittest cases retain their complete scenario bodies and
independent wire/hash oracles. They cover verbatim governance metadata, invalid
input atomicity, immutable revision history, lifecycle/evaluation boundaries,
holdout separation, corrupted stored metadata and approval reentrancy.

The original finite-list runner and Hash32 SQLite stores remain inert. Ordinary
imports bind the original API globals; a package fixture supplies fresh temporary
roots and offline, network/process and model-import restrictions during test
execution. Product imports occur at pytest collection before that fixture runs;
the original guarded collection/startup boundary is not transferred. No real
evaluator, model, native host or protected custody is qualified here.

The old sealed serial runner, artifact/predecessor checks and watchdog are not
replayed. Current source identity is checked against this checkout, and historical
results remain separate. Only imports, formatting and narrow lint annotations
change; original test/helper/class executable bodies remain intact. The author
ran static checks only. Root reviews the source before first execution.
