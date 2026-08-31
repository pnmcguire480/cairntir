# Medium Business Product Roadmap

**Working label:** Cairntir Medium Business. Final naming requires trademark
clearance and customer testing.

**Target:** Organizations roughly 25–500 people with several AI-assisted teams,
one IT generalist or a small IT staff, private source or research material, and
no desire to operate an AI memory platform.

## Buyer promise

Install Cairntir inside the customer's environment in one working session.
Connect approved AI hosts. Keep the customer’s memory under customer control.
Give an administrator enough policy, backup, and evidence to trust it without
turning the product into another full-time system.

The product is not “shared ChatGPT history.” It is a private continuity layer
that can show where remembered context came from and whether it was allowed to
influence the session.

## What ships

- signed Windows and Linux packages plus a documented container option;
- one-node production deployment, with an optional warm standby only after
  restore testing proves it useful;
- encrypted storage using operating-system or customer-approved cryptographic
  services rather than Cairntir-authored cryptography;
- team and project boundaries mapped onto the existing wing/room/drawer model;
- local accounts for the smallest customer and OIDC for managed identity;
- administrator, workspace-owner, contributor, reader, and auditor roles;
- MFA through the identity provider or a documented local fallback;
- explicit allowlists for hosts, models, projects, and export destinations;
- scheduled backup, tested restore, retention, export, and deletion;
- a human-readable audit log and CSV/JSON export;
- diagnostics disabled by default, locally previewable, and sent only after
  explicit approval;
- upgrade preview, rollback, and a supported-version policy;
- paid onboarding and support.
- a bounded organizational-health pack for one business domain: 2–3 approved
  source systems, shared metric definitions, weekly change detection, and
  evidence-linked recommendations in shadow mode.

## What does not ship

- mandatory vendor cloud;
- hidden telemetry or customer-memory access;
- fleet management across hundreds of sites;
- a promise of high availability before a measured customer need;
- SOC 2, CMMC, FedRAMP, HIPAA, or “military grade” marketing without the exact
  scoped evidence;
- a second agent runtime, model router, project manager, or chat interface;
- silent cross-team search.
- automatic write-back to CRM, finance, staffing, ticketing, or production
  systems.

## Architecture boundary

The MIT core remains the memory engine on each customer-controlled node. The
commercial package owns installation, identity, policy, backup, audit, upgrades,
and support. It calls the core through documented interfaces and pins an exact
attested core build.

Start with one store per workspace or team rather than putting many mutually
distrusting teams into one SQLite file. A small registry may locate stores, but
it must not become a second truth source for drawer content. Cross-workspace
recall is denied by default and requires an explicit policy plus an audit event.

## Roadmap

### MB0 — Problem proof and ownership

**Work**

- interview 10–15 organizations that already use two or more AI coding or
  research hosts;
- record the cost of re-briefing, lost decisions, and unsupported AI claims;
- identify the buyer, operator, data owner, and daily user separately;
- freeze the MIT-core baseline and produce its authorship/dependency ledger;
- draft commercial contribution and contractor rules;
- select three paid-design-partner candidates.

**Exit gate**

- at least five interviews describe the same expensive continuity failure;
- at least two organizations will pay for a bounded pilot;
- the commercial value is administration/evidence/support, not a feature
  removed from the free core.

**Kill signal:** buyers like “local AI” but cannot name a repeated continuity
failure or a budget owner.

### MB1 — Threat model and deployment spike

**Work**

- map data flows, trust boundaries, local administrators, compromised agents,
  malicious drawers, stolen backups, and accidental exports;
- build a signed installer around an unchanged pinned core;
- add first-run environment checks, least-privilege service identity, and
  deterministic configuration;
- implement encryption and key-rotation seams using customer/OS services;
- build backup and restore with corruption and interrupted-write tests;
- generate SPDX or CycloneDX SBOMs and sign release artifacts;
- prove offline installation and updates from a local bundle.

**Exit gate**

- a clean machine installs in under 60 minutes from the customer artifact;
- a deliberately damaged or incomplete install fails loudly;
- restore recovers every drawer, provenance receipt, index state, and policy;
- an offline installation performs no network call;
- the SBOM and artifact signature match the installed bytes.

### MB2 — Identity, isolation, and administration

**Work**

- OIDC login, local break-glass procedure, role checks, and session expiry;
- workspace-scoped stores and deny-by-default cross-workspace access;
- project/host/model allowlists;
- admin console for health, capacity, backup status, versions, and policy;
- append-only security events with actor, action, target, result, and time;
- export/delete workflows with a preview and dual confirmation for destructive
  operations;
- migration rehearsal against a copy before touching the live store.

**Exit gate**

- red-team tests cannot read another workspace through recall, export, backup,
  logs, or error messages;
- every administrative mutation has a durable receipt;
- a break-glass session is time-limited, visible, and reviewable;
- a policy denial explains the boundary without leaking protected content.

### MB3 — Continuity and evidence pilot

**Work**

- run 30-day pilots with 3–5 teams;
- pre-register recurring tasks and continuity questions before pilot use;
- measure successful handoffs, wrong-authority retrievals, re-brief time,
  omissions, token output, restore success, and operator time;
- require users to mark accepted, wrong, stale, or unsafe recalled context;
- test phone-to-PC intake only after PR #76's proposal is accepted and its
  transport is implemented independently;
- publish a pilot evidence report without customer memory.
- choose one operational question, such as delivery delays, support escalation,
  or sales handoff loss; link its source measures to the decisions and predicted
  outcomes stored in Cairntir;
- run weekly shadow recommendations beside the customer's normal review and
  settle each prediction after the agreed window;
- record source freshness, missing fields, metric-definition changes, and
  alternative explanations before calling a pattern actionable.

**Exit gate**

- 95% of tested session resumes recover the controlling decision or abstain;
- zero cross-workspace disclosures;
- median weekly operator time stays below 30 minutes after onboarding;
- restore succeeds in every scheduled drill;
- two customers convert to paid annual use.
- the feedback engine either beats the customer's existing review baseline on
  pre-registered detection/prediction measures or the feature is rejected.

The 95% target is a product gate, not a claim about current Cairntir.

### MB4 — Sellable release

**Work**

- standard order form, commercial license, DPA, support policy, and security
  questionnaire answers reviewed by counsel;
- two supported deployment profiles and no undocumented permutations;
- vulnerability intake, patch cadence, end-of-support policy, and customer
  notification procedure;
- onboarding checklist, admin manual, incident runbook, and recovery drill;
- pricing tested against customer savings and support burden.

**Exit gate**

- a customer not involved in development installs from the release package;
- a second person follows the runbooks without Patrick translating them;
- the complete release is reproducible from a clean checkout;
- support cost and gross margin remain viable at the chosen price.

## Business model to test

Prefer an annual site license with a clear seat or active-workspace band,
onboarding, and support. Do not charge per drawer, token, or recalled sentence;
those meters punish the behavior the product is meant to improve. Keep a
customer-operated base tier and price higher for OIDC, managed upgrades,
extended retention, and priority support only when those features create real
service cost.

Pricing is not set by this roadmap. Three paid pilots come before a polished
pricing page.

## Success measures

- minutes of re-briefing avoided per person per week;
- percentage of resumes that recover the controlling decision or abstain;
- wrong-authority retrieval rate;
- operator minutes per week;
- backup and restore success;
- time to patch a severe issue;
- paid pilot conversion and renewal;
- support hours per customer.
- percentage of shadow recommendations settled on time;
- precision of detected operational changes and calibration of predicted
  effects;
- accepted interventions that improve the target measure without breaking a
  guardrail.

Drawer count, embedding count, and dashboard visits are not success measures.

## Principal risks

- **SQLite is mistaken for a team database.** Use isolated stores and an
  external policy/registry seam; do not fake concurrent tenancy inside one file.
- **Administration overwhelms simplicity.** Ship presets and two deployment
  profiles, not a configuration maze.
- **The product becomes paid packaging with no value.** Paid pilots must buy
  isolation, evidence, recovery, and support—not an installer alone.
- **Diagnostics repeat the telemetry mistake.** Keep them local until the
  customer previews and sends a specific bundle.

## Dependency on the product family

This roadmap consumes foundation packets F0–F9 from the
[commercial product-family decision](../2026-08-30-commercial-product-family.md).
It may start first, but it cannot redefine the MIT core or pre-commit enterprise
and national-security claims.
