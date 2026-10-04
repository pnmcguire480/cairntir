# Final readiness-state correction

The original package and its first-repair PASS receipts remain unchanged. A later
focused active-checkout run exposed an intermittent startup race: one worker's
new brief inserted an unclosed epoch into another worker's readiness hash. The
first worker then rejected its otherwise unchanged complete brief before the
dispatch rendezvous. The first failed wrapper log, secondary cleanup error and
surviving driver traceback are retained here.

The separately frozen STATE contract makes the original requirement
deterministic: two runtimes can acknowledge their own unchanged task briefs even
when the second starts after the first received its brief. No capture, outcome,
configuration or task change occurs in that test. It reproduced the stale-brief
error on repair1 before repair2.

The final permitted product repair removes unclosed-session telemetry from the
authoritative readiness state. The whole returned brief and its brief hash still
contain that information. Captures, failed claimed events, task state,
configuration and uncertain actions continue to affect readiness. The original
concurrency assertions remain unchanged.

The complete original 27 cases plus the new deterministic case pass. The maintained
wrapper now runs 28 cases: 26 without a model cache and two explicit real-model CLI
gates. A deliberate replay-guard removal still creates two actual child markers
and fails the unchanged crash assertion. This uses both allowed managed-runtime
repair rounds; additional product repair requires an explicit plan amendment.

These results qualify only the managed local workflow boundary. Full-source,
repository and installed-wheel gates remain separately recorded. Native coding-
host delivery, private evaluator custody and R10 projection remain outside this
packet's claims.
