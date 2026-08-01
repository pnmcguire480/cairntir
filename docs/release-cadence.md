# Release Cadence

Cairntir is worked on almost daily. It is not released almost daily.
This document defines the difference, because getting it wrong once
already cost three months of silence.

## Three things that are not the same thing

Most of the confusion here comes from calling all three "uploading."
They have different audiences and different costs.

| Action | Who sees it | Cost of doing it often |
|---|---|---|
| **Commit** | Nobody | None. Do it constantly. |
| **Push / merge to `main`** | Anyone reading the repo | None. **No user receives a new version.** |
| **Push a `vX.Y.Z` tag** | Every `pip install cairntir` | This is the release. |

Only the third one publishes. The release workflow fires on a pushed
`v*.*.*` tag and nothing else.

### The evidence this split is real

Version 1.1.3 was committed, changelogged, reviewed, and sitting on
`main` from 2026-05-03. Not one user received it, because it was never
tagged. The cold-start fix it contained — first run from roughly twelve
minutes down to 1.4 seconds — stayed invisible until 2026-08-01 while
every `pip install cairntir` kept resolving to 1.1.2 and hanging.

The cost was not the bug. The cost was the three months.

`scripts/check_release_tags.py` now fails the build if a released
changelog header has no matching tag, so this specific failure cannot
recur silently. It does not, however, tell you when it is *time* to
release. That judgment is below.

## When to release

**Push daily. Merge whenever a slice is coherent. Release rarely.**

Pushing to `main` costs users nothing and risks nothing, so there is no
reason to hoard work locally. Releasing is the rare act.

A release is warranted when the accumulated `## [Unreleased]` section
would make a user say *"I want that."* Concretely, one of:

- one headline capability, or
- three or four smaller additions that add up to a reason to upgrade.

At a daily working pace that lands somewhere around every two to six
weeks. Releases should be substantial. A changelog full of hotfixes and
small expansions is a signal to keep accumulating, not to publish.

### The one exception that overrides all of the above

**Anything that breaks install or first run for a new user ships
immediately as a patch.** Do not let it wait for a substantial release.

This is the 1.1.3 rule stated as policy. A user who cannot install, or
whose first command hangs, does not experience a project that is
"between releases" — they experience a project that is broken. Cold
starts, import failures, crashes on `--help`, platform-specific
encoding faults, and anything that makes the first five minutes fail
all qualify.

### The staleness check

Because the working cadence is daily and the release cadence is not,
user-facing fixes can accumulate unnoticed on `main`. Before closing
any session, check:

> Does `## [Unreleased]` contain a **Fixed** entry that a current user
> is hitting right now?

If yes, that is a patch release, regardless of how thin the changelog
looks. Thin is fine. Silence is not.

## Choosing the number

Patrick decides *when* a release is worth considering. The agent reads
the accumulated changelog and decides *which number*, based on how deep
the work actually went.

| Segment | When | Example |
|---|---|---|
| **PATCH** `1.2.1` | Fixes only. Nothing new to learn. | Cold-start hang; a Windows encoding crash. |
| **MINOR** `1.3.0` | New capability, additive. Also where deprecated surfaces are removed, after the warning window. | A new MCP tool; a new recipe; a new host adapter. |
| **MAJOR** `2.0.0` | **Reserved.** See below. | Has not happened. May never. |

Tiebreak: if a user would need to read the changelog to know what
changed, it is a MINOR, not a PATCH.

### MINOR is unbounded

There is no ceiling on the minor segment and no pressure to ever reach
`2.0.0`. `1.9.0`, `1.24.0`, and `1.47.0` are all ordinary versions.
Projects sit on a single major for years; that is the normal case, not
a deferred obligation.

This is why Cairntir does not need a fourth version segment. A
four-segment version such as `1.2.0.0` is legal under PEP 440 and PyPI
would accept it, but `scripts/check_release_tags.py` parses changelog
headers as exactly three segments — a `## [1.2.0.0]` header would be
skipped rather than checked, silently re-creating the 1.1.3 failure
inside the tool built to prevent it. Three segments, unbounded middle.

### What `2.0.0` is reserved for

A major version marks a revolutionary change in what Cairntir *is* —
not merely a change that breaks a caller. Removing a deprecated surface
is a MINOR (see [Deprecation Policy](deprecation-policy.md)), so
breaking changes have a home that is not `2.0.0`.

This is a deliberate, documented deviation from strict Semantic
Versioning, and it is safe because the two-minor deprecation window
does the work that a major bump would otherwise do: nothing public
disappears without warning, a named replacement, and at least two
releases of overlap.

## The mechanical sequence

Cadence answers *whether* and *which number*. The actual publish
sequence — verification, tagging, trusted publishing, attestation,
post-publish smoke test — is in
[Publish Checklist](publish-checklist.md). Code completion never
authorizes publication; the tag is an explicit human gate.

## Merging to `main`

`main` is protected. It requires a pull request and two green status
checks (`Build Package`, `LongMemEval R@5 Gate`) and **zero approving
reviews**. For a solo maintainer that is one click, not a review cycle.

Go through the branch, not around it. Pushing directly to `main`
triggers an admin bypass, which defeats the point of running the full
matrix before `main` moves — and `main` is what the release workflow
builds from.
