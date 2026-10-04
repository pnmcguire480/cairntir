# Frozen managed evidence transport

PR131's first hosted run reported fourteen CodeQL findings in eight historical
acceptance/evidence resources. Two identify setup calls inside assertions; six
concern deliberately raised rollback exceptions; six concern test diagnostics,
cleanup style and an unused historical global. No production vulnerability is
established by those annotations. The initial failed head is
`22a291cd3868b568af1c5013519f14af53aff24f`.

`resources.zip` preserves exactly those eight resources, with original logical
paths and bytes. `MAP.json` records their hashes and sizes. All prior manifests,
seals and historical results remain unchanged. The restorer independently pins
the transport hash, member set, individual hashes, sizes and regular-file
metadata. It rejects altered, extra, duplicated or missing resources before
writing anything. It never overwrites an existing destination.

Normal test adapters reconstruct the four original capsules in disposable
directories, then run their unchanged integrity checks, loaders and assertions.
Installed verification copies the same pinned originals from a reconstructed
capsule. The source checkout is never restored into or modified by this process.
Corrected active controls remain normal Python sources for analysis and execution;
their amendments retain the original behavioral expectations.

This is a resource representation change, not an alert dismissal, query exclusion
or passing CodeQL result. Both CI and CodeQL workflows, coverage settings, root
fixtures and the generic preservation gate are unchanged. Fresh exact-head hosted
qualification and independent review remain required. Evidence preservation is
not independent evaluator custody or real-host/operator acceptance.
