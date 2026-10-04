# Brief-only writes do not change readiness

The frozen core contract says brief records themselves do not invalidate state, and excludes epoch/brief identities from the authoritative state hash. Repair1's prior-unclean-epoch visibility accidentally inserted runtime epoch metadata into that state. An actual two-process race then failed before its dispatch rendezvous when the first process tried to acknowledge its startup brief. The original race failure and surviving driver traceback are retained.

This deterministic supplement starts a second authorized runtime after the first has received its complete brief, without capturing, completing, changing configuration, or dispatching any action. Both runtimes must still be able to acknowledge their own exact complete brief. Prior-unclean-session information remains in the returned brief and its full brief_sha256; its appearance alone is not a task/commitment change. Existing source/checkpoint changes, failed received captures, configuration changes and uncertain actions must continue to invalidate readiness under the original frozen tests.

This is an existing-contract correction, not acceptance relaxation. The original concurrency case remains unchanged and required. No new schema, capability or host guarantee is introduced. The supplement is frozen before repair2.
