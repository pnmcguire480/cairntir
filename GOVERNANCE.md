# Governance

Cairntir is a **benevolent dictator** project for v1. This is the honest description, not a power claim.

## Current Structure (v1)

- **Project Lead:** Patrick McGuire (@pnmcguire480)
- **Maintainers:** @pnmcguire480 (sole)
- **Decision model:** Lead decides. Community is consulted via GitHub Discussions for anything affecting public API, dependency choices, or project direction.

## Why Benevolent Dictator for v1

A small project with one maintainer does not benefit from committee structures. Voting ceremonies slow decisions without improving them at this scale. When the project has >3 active maintainers, this document will be revised toward a lazy-consensus model.

## Principles

All governance decisions are filtered through four tests:

1. **Does this serve the north star?** (killing cross-chat AI amnesia)
2. **Does this preserve simplicity?** (Cairntir is deliberately minimal)
3. **Does this keep it local-first, free, and open?** (MIT, no SaaS, no gating)
4. **Is this reversible?** (if not, slow down and consult)

If a decision fails any of these tests, it is rejected or deferred regardless of how clever it is.

## Decision Types

### Trivial (no consultation)
- Bug fixes
- Typo corrections
- Dependency patch updates
- Internal refactors with no API change

### Normal (Lead decides, discussion welcome)
- New MCP tools
- CLI flag additions
- Documentation reorganization
- Minor dependency version bumps

### Major (discussion required before decision)
- Breaking changes to public API
- New dependencies
- Adding or removing a skill
- Changes to the taxonomy (wing / room / drawer model)
- Release schedule changes
- License changes (currently impossible — MIT is locked)

### Locked (never changes)
- **MIT license** — Cairntir will never be relicensed.
- **Local-first** — no mandatory cloud component, ever.
- **No telemetry without explicit opt-in** — and opt-in means actually opt-in, not dark patterns.
- **Three skills maximum in the core** — crucible, quality, reason.

## Contributor Ladder

1. **First-time contributor** — submit a PR, be welcomed
2. **Regular contributor** — 3+ merged PRs, invited to review others' PRs
3. **Triager** — demonstrated judgment on issues, granted triage permission
4. **Maintainer** — sustained contribution + alignment with principles, granted write access and CODEOWNERS entry

## Changing This Document

Proposed changes to `GOVERNANCE.md` require a Discussion thread open for at least 7 days before merge, regardless of who proposes them. The lead reserves final say during v1.

## Exit Plan

If the project lead becomes unavailable for 60+ days without notice, the next most-active maintainer assumes stewardship. If no maintainers exist, the most-recent 3 contributors by commit count are invited to take over. This prevents the project from becoming orphaned.

---

*Governance is constraint, not control. These rules exist to make responsibility easier to carry, not to concentrate power.*
