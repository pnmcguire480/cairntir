# Backup probe amendment results

The legacy CLI case failed locally in 2.453 seconds and in hosted qualification
because status no longer opens a writable store. The explicit independent
amendment preserves the frozen original and every backup assertion, using actual
owner get startup only for that exact case. No runtime source changes.

Initial amended run: two passed, one failed in 7.063 seconds. The added owner-get
control incorrectly required source equality despite documented access metadata
updates. Independently frozen v2 removes only that invalid new assertion.

Corrected bounded run: three passed in 7.969 seconds, including real due-backup
status purity, real owner startup, complete standalone snapshot fidelity and
repeat-get cadence. Existing pytest plugin autoload is disabled; the unused
asyncio_mode option emits one warning. No inference, installation or private data.

Canonical Ruff lint/format pass for 197 maintained files. The unchanged
preservation gate passes 24 baseline manifests, 115 artifacts and four council
manifests. Release lint scope now matches CI; no global exclusions, coverage
changes, behavioral skips or preservation gate modifications.

Full fresh hosted CI, installed-package/evaluation checks and release remain
pending. These bounded local checks do not substitute for that qualification.
Reviewer: gpt-6-astra/high as recorded by task metadata. Root routing/effort and
token/cost telemetry are unavailable; no savings are claimed.
