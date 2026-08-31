# Cairntir Commercial Product Family

**Status:** Product-family direction authorized by Patrick McGuire on
2026-08-30. This document authorizes planning, IP-boundary work, and customer
discovery. It does not authorize claims of certification, handling classified
information, publishing a release, or changing the MIT core.

**Baseline:** `pnmcguire480/cairntir` `main` at `ee9bc52` (v1.8.0 release
candidate). PR #76, the phone-to-PC continuity proposal, is related but remains
unmerged and is not part of this baseline.

## Decision

Cairntir will have three commercial product lines:

1. **Medium Business** — a low-administration, customer-hosted memory appliance
   for teams that cannot afford an AI platform staff.
2. **Large Enterprise** — governed private deployment for many teams, identity
   domains, retention policies, audit systems, and procurement controls.
3. **National Security** — an offline-first, evidence-heavy distribution for
   unclassified and CUI work first; classified use is forbidden until a customer
   sponsor, cleared organization, authorized system, and applicable approvals
   exist.

These are three products, not three permanent copies of the same Python tree.
Literal long-lived forks would multiply every migration, retrieval correction,
host adapter, security fix, and evaluation by three. The cleaner structure is:

```text
MIT Cairntir core
  ├── Medium Business product package
  ├── Large Enterprise product package
  └── National Security product package
```

Each commercial package pins an attested core version and adds separately
owned deployment, policy, administration, support, and compliance material.
Code that is intentionally donated to the core is released under MIT through a
normal core pull request. Commercial code never drifts into the public tree by
accident.

## The non-negotiable license boundary

The existing core cannot be pulled back from MIT. The license already grants
recipients the rights to use, copy, modify, distribute, sublicense, and sell the
released code. Cairntir's `GOVERNANCE.md` also locks the core to MIT.

That does **not** prevent Patrick from selling Cairntir, selling support, or
building new proprietary software around it. It means the protected value must
be new work and real service, not an attempt to revoke rights already granted.

| Asset | Default treatment |
|---|---|
| Existing and future public core | MIT; forever free, local-first, no gated core features |
| Public documentation and tests | Same repository terms unless separately marked |
| Commercial control plane, installers, policy engine, fleet tools, connectors, evidence packs | Private repository; commercial license; all rights reserved until counsel supplies final terms |
| Customer configuration and memory | Customer-owned; never treated as Cairntir IP |
| Brand names and marks | Trademark clearance, then registration if commercially justified |
| Non-public operating methods, pricing, customer mappings, deployment know-how | Trade-secret controls where secrecy is real and maintained |
| Patent candidates | Evaluate before public disclosure; file only for a specific, valuable, defensible invention |

The repository history currently attributes human commits to Patrick McGuire;
Dependabot is the only other recorded committer. Before outside code enters a
commercial repository, contributors or contractors need written invention and
copyright assignment terms. Public-core contributions remain MIT; add a DCO or
CLA only after counsel chooses the inbound policy.

### IP work that comes before sales

1. Preserve the baseline commit, release artifacts, SBOM, authorship history,
   and build attestations.
2. Form the entity that will sign contracts and own the commercial IP, then
   execute a written assignment from Patrick to that entity if that is the
   chosen structure.
3. Run trademark clearance for `Cairntir` before promising exclusive brand
   rights.
4. Register important human-authored source releases and documentation with the
   U.S. Copyright Office when counsel says the cost is justified.
5. Put invention-assignment, confidentiality, and work-made-for-hire language in
   every employee and contractor agreement before work begins.
6. Keep commercial repositories private, permissioned, logged, and backed up.
7. Maintain a dependency and license inventory for every shipped artifact.
8. Do not call AI-generated material protectable IP merely because it is in the
   repository; record meaningful human selection, revision, and authorship.

This is an engineering boundary, not legal advice. Final licenses, assignments,
trademark filings, patent decisions, and government contract terms require a
qualified attorney.

## What the market already makes ordinary

Local storage and self-hosting matter, but they are not rare. Mem0 documents a
self-hosted server with a dashboard and audit log; Letta keeps local agent state
on-device without an account; LangGraph supports long-term memory stores; Zep
positions Graphiti as its local open-source graph engine and its proprietary
service as the governed enterprise layer.

That means Cairntir cannot win by saying only: “your memory stays local.” It can
win by proving that the memory is **trustworthy enough to drive work**—and, at
the commercial layer, trustworthy enough to help an organization see itself.

## The moat

### 1. Receipted institutional memory

Cairntir preserves exact evidence, immutable write provenance, trust,
sensitivity, validity, supersession, and durable workflow receipts. A buyer can
trace an answer or action to the drawer, source, host, model, session, and
decision chain that produced it. Most memory products optimize for a useful
answer. Cairntir should own the harder question: *why was this context allowed
to influence the answer?*

### 2. Authority-aware continuity

User statements, verified sources, assistant synthesis, imported memory, and
recovered transcripts do not receive equal authority. Untrusted text is quoted
as evidence with `instruction_authority=none`; it cannot silently become
policy. This is more valuable in a company than another similarity score.

### 3. Deterministic, bounded context

Whole drawers, explicit omission, hard budgets, and prompt-cache-friendly
determinism make token cost and context behavior measurable. “Returned useful
context” is not enough. The product must show what was loaded, what was omitted,
why, and how much it cost.

### 4. Closed learning loops without hidden training

Prediction-bound drawers, observed outcomes, surprise, calibration, and the
Discovery Ledger let the system improve through visible evidence without
fine-tuning on customer data or silently rewriting prompts. Karpathy's useful
essence belongs here: small tests, explicit predictions, measured deltas,
keep/reject decisions, and no architectural victory speech before the result.

### 5. Structural memory tied to work

File anchors and `recall_for_change` connect remembered decisions to the code
or research artifact being changed. The long-term target is a verified chain
from request → evidence → decision → file diff → test → outcome, without hiding
the record in source comments.

### 6. Portability without hostage-taking

The MIT core, local store, portable envelopes, and explicit export path reduce
customer fear. The commercial moat is superior operation and evidence, not
preventing departure. That looks weaker on a spreadsheet and stronger during a
security review.

### 7. The organization can remember cause and effect

The largest commercial idea is not employee memory. A company pours decisions,
forecasts, incidents, launches, customer signals, financial results, staffing
changes, production measures, and corrective actions into disconnected systems.
Humans see their own slices. Cairntir can preserve the time-linked chain:

```text
signal → interpretation → decision → predicted result → action → observed result → correction
```

A separate commercial **organizational-feedback engine** may read approved
signals from CRM, ERP, finance, support, delivery, code, incident, and research
systems. It can identify a section improving or decaying, retrieve the decisions
and conditions that preceded the change, and propose a small intervention with
an expected measurable effect.

This engine is not part of the MIT memory core. It never changes a business
system, reallocates money, scores an employee, or promotes its own strategy.
Every recommendation must carry:

- the metric and scope that triggered it;
- the source systems, freshness, quality limits, and missing data;
- the remembered decisions and outcomes that support it;
- at least one plausible alternative explanation;
- the proposed action, owner, duration, guardrails, and rollback;
- a falsifiable predicted effect and a settlement date; and
- the human decision plus the observed result.

New recommendations run in shadow mode first. The system proves that it can
detect a problem and predict an outcome before it receives any actuation path.
This is the Karpathy loop applied to company operations: one bounded hypothesis,
one measurable change, keep or reject from evidence. It is also where Cairntir's
provenance matters more than generic analytics. A direction without its chain of
evidence is another dashboard opinion.

Employee surveillance is outside the default product. Analyze work systems and
team-level outcomes; do not infer individual loyalty, mood, health, productivity,
or promotion value from memory exhaust. A customer seeking individual scoring
requires a separate legal, labor, bias, and governance review and is not covered
by these roadmaps.

## Shared foundation before edition work

Every product line depends on the same ten foundation packets. Build each once
and test each edition against it.

| Packet | Required result |
|---|---|
| F0 — ownership | Authorship ledger, dependency licenses, commercial contribution policy, entity/IP assignment decision |
| F1 — threat model | Assets, actors, trust boundaries, abuse cases, data flows, and forbidden claims |
| F2 — cryptography seam | Encryption interfaces that can use customer-approved or FIPS-validated modules without home-grown cryptography |
| F3 — identity/policy seam | External identity, least privilege, role and attribute checks, separate administrative duties |
| F4 — audit evidence | Append-only, tamper-evident administrative and data-access events with redaction rules and export |
| F5 — deployment | Signed, reproducible, offline-capable artifacts; deterministic configuration; rollback; SBOM |
| F6 — lifecycle | Backup, restore, retention, legal deletion, migration, disaster recovery, and end-of-support policy |
| F7 — evaluation | Pre-registered continuity, retrieval, authority, isolation, cost, latency, and failure tests |
| F8 — support | Severity definitions, response targets, disclosure process, customer runbooks, and escalation ownership |
| F9 — organizational feedback | Approved connectors, semantic metric definitions, data-quality receipts, decision/outcome links, shadow recommendations, experiments, and settlement |

No edition may claim a packet because a document exists. Its gate must be
watched fail, then pass—the same lesson Cairntir learned from guards that
reported success without doing their job.

## Edition boundaries

| Question | Medium Business | Large Enterprise | National Security |
|---|---|---|---|
| Primary buyer | Owner, CTO, IT generalist | CIO/CISO, platform engineering, procurement | Program office, cleared prime, mission owner, authorizing official |
| Typical deployment | One customer-managed node or small cluster | Private cloud/on-prem, multi-region optional | Disconnected or tightly controlled enclave; no network dependency |
| Identity | Local accounts or OIDC; MFA | SAML/OIDC, SCIM, RBAC/ABAC, break-glass | Approved enterprise identity, device identity, separation of duties |
| Storage | Encrypted local stores with managed backup | Tenant-isolated stores, KMS/HSM, retention and legal hold | Enclave-local stores, approved crypto, media and transfer controls |
| Administration | Simple policy presets | Central policy, delegated admin, fleet inventory | Configuration baseline, two-person changes where required, offline evidence |
| Evidence | Audit export and recovery receipts | SIEM export, evidence API, control mappings | Signed evidence bundles, chain of custody, authorization package inputs |
| Availability | Clear backup/restore target | HA, DR, capacity and SLOs | Mission-specific continuity; degraded/offline operation is tested |
| Telemetry | Off by default; explicit preview and consent | Customer-routed observability; no vendor data by default | None; locally retained diagnostics only |
| Claim ceiling | “Private team memory” after tests | “Enterprise governed” after audits | “CUI-ready” or “classified-ready” only after the applicable assessment/authorization |

## Build order

1. **Protect and measure the core.** Finish ownership, threat, dependency, and
   baseline evidence. Merge no edition code into core merely to save time.
2. **Build feedback in shadow mode.** Connect one decision domain to two or
   three authoritative systems, define its measures, and test whether the engine
   predicts changes better than the existing review process. No write-back.
3. **Medium Business first.** It forces packaging, administration, backup,
   identity, support, and real paid use without pretending to be an enterprise
   platform.
4. **Large Enterprise second.** Add policy scale, isolation, SIEM, HA, legal
   controls, and formal assurance only after the smaller product survives use.
5. **National Security in parallel as documentation and lab hardening only.**
   Begin CUI mappings, offline builds, crypto seams, supply-chain evidence, and
   partner discovery. Do not build classified features from imagination.
6. **Classified work only after sponsorship.** A government agency or cleared
   contractor must sponsor the facility-clearance process; system authorization
   and personnel access are separate gates.

The three detailed roadmaps are:

- [Medium Business](product-lines/medium-business.md)
- [Large Enterprise](product-lines/large-enterprise.md)
- [National Security](product-lines/national-security.md)

## Product-family acceptance bar

The family structure survives only if all of these remain true:

- one core fix can reach all editions without hand-merging three code copies;
- the free core loses no existing feature to manufacture a paid tier;
- commercial modules have a clean ownership and dependency record;
- a customer can export its data and operate the core without the commercial
  service;
- no edition silently sends memory or diagnostics to Patrick;
- every compliance statement names the exact scope and evidence behind it;
- each edition has a different buyer, deployment, gate, and reason to exist;
- paid pilots show less re-briefing or lower failure cost, not merely more
  stored drawers;
- an operational recommendation can be traced from source signal through human
  decision to settled outcome;
- shadow recommendations outperform the customer's existing review baseline
  before any write-back is considered; and
- the engine abstains when source data is stale, contradictory, or too weak to
  support causal language.

If those conditions fail, stop calling the result a product family. It is three
branches and a sales page.

## Source register

- [Open Source Initiative — MIT License](https://opensource.org/license/mit)
- [U.S. Copyright Office — copyright basics and registration](https://www.copyright.gov/circs/)
- [USPTO — IP toolkits](https://www.uspto.gov/learning-and-resources/inventors-and-entrepreneurs/ip-basic-toolkits)
- [Mem0 — platform versus open source](https://docs.mem0.ai/platform/platform-vs-oss)
- [Letta — self-hosting](https://docs.letta.com/self-hosting/)
- [Zep — Zep versus Graphiti](https://help.getzep.com/zep-vs-graphiti)
- [LangGraph — long-term memory](https://docs.langchain.com/oss/python/concepts/memory)
- [NIST SP 800-218 — Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final)
- [CISA — Software Bill of Materials](https://www.cisa.gov/topics/information-communications-technology-supply-chain-security/sbom)
- [NIST — AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST AI RMF Playbook — Measure](https://airc.nist.gov/airmf-resources/playbook/measure/)
- [ISO/IEC 42001 — AI management systems](https://www.iso.org/standard/42001)

There are no `cairntir-commitments` in this decision package. Product code
requires a separate implementation plan with pre-registered tests and explicit
edition scope.
