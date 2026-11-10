# Practice review edge controls

Only eight original R18 cases are collected: two issued/bound-grant visibility
checks, three review-window/concurrent-append checks and three grant-recheck
checks. The other 53 inventoried cases remain planned; none are inherited or
recollected through completeness test classes.

The original two Harness/Runner versions remain separate. Visibility uses v1;
concurrency and grant rechecks use v2, including its original setledger commit.
Each keeps its temporary Hash32 SQLite store, inert runner, network-connect
guard, setup and registered cleanups. These guards apply during the original
test fixture lifetime, not protected collection/startup or host custody.

The visibility cases use actual local issue_grant/bind_grant calls. The three
recheck cases deliberately inject _grant and qualify lookup freshness and
completeness; they do not qualify persisted-token authentication. Concurrency
uses real local threads and store connections with the original five-second
barrier and 15-second future deadlines. No live model or native observer runs.

Only ordinary relative imports, unused import cleanup, formatting and narrow
lint annotations differ. Original selected test/helper executable bodies and
assertions remain intact. No sealed runner or historical qualification is
transferred. The author ran static checks only; root reviews before execution.
