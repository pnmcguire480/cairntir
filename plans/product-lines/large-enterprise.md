# Large Enterprise Product Roadmap

**Working label:** Cairntir Large Enterprise. Final naming requires trademark
clearance and buyer testing.

**Target:** Multi-business-unit organizations with thousands of users, several
identity and data domains, formal risk/procurement teams, private cloud or
on-premises requirements, and enough operational history that no leadership
team can manually connect every decision to its eventual result.

## Buyer promise

Give the company a governed institutional memory and an evidence-linked
organizational feedback loop. Approved AI hosts can continue work across time,
teams, and models without flattening access boundaries. Leaders can see where
performance changes, what decisions preceded the change, what the system
predicts will help, and whether the proposed correction actually worked.

The product earns the word “enterprise” through isolation, identity, policy,
evidence, lifecycle, availability, and support—not a license key and a bigger
price.

## Product shape

### Memory data plane

- isolated stores by tenant, business unit, sensitivity domain, and residency
  requirement;
- no single shared SQLite file across mutually distrusting users or nodes;
- customer-chosen storage and cryptographic services behind tested contracts;
- immutable provenance, trust, validity, supersession, and decision/outcome
  chains preserved from the core;
- bounded, deterministic retrieval with policy applied before content leaves
  the data plane;
- region and residency placement declared per store.

### Policy and administration plane

- SAML or OIDC federation, SCIM provisioning, MFA, device/session context;
- RBAC plus bounded attributes for sensitivity, project, geography, legal
  matter, and purpose;
- delegated administration with separation of duties and break-glass review;
- policy-as-code with versioned approval, dry-run evaluation, and rollback;
- fleet inventory, supported-version enforcement, capacity, health, and backup
  evidence;
- retention schedules, legal holds, deletion approvals, and export controls;
- SIEM and case-management export without raw memory in routine security logs;
- customer-routed observability; no vendor telemetry by default.

### Organizational-feedback engine

- read-only connectors for approved CRM, ERP, finance, support, incident,
  delivery, code, research, and production systems;
- a customer-owned semantic layer defining measures, owners, units, dimensions,
  time windows, lineage, and known limitations;
- time-linked decision, prediction, intervention, and outcome records;
- change-point, anomaly, lag, and cross-domain pattern candidates;
- explicit distinction among correlation, temporal association, experiment,
  and causal evidence;
- alternative explanations and missing-data warnings;
- shadow recommendations with owner, scope, expected effect, guardrails,
  rollback, and settlement date;
- human approval before experiments and a second approval before any future
  write-back capability;
- portfolio views that show where a strategy worked, failed, or transferred
  poorly across business units.

## Forbidden shortcuts

- Do not convert wing names into an authorization system. Authorization must
  happen before retrieval and be tested independently of taxonomy.
- Do not call a vector database multi-tenant because records have tenant IDs.
- Do not train on customer memory or combine customer evidence.
- Do not infer causation from an attractive chart.
- Do not score individual workers, union activity, health, mood, loyalty, or
  promotion value from activity exhaust.
- Do not claim SOC 2, ISO/IEC 27001, ISO/IEC 42001, HIPAA, GDPR, FedRAMP, or
  another assurance outside the exact audited scope.
- Do not make a cloud control plane mandatory for an on-premises buyer.

## Roadmap

### LE0 — Design partners and control inventory

**Work**

- recruit 3–5 design partners in different operational settings;
- map buyers, system owners, data stewards, works councils/employee
  representatives where applicable, privacy, security, procurement, and daily
  users;
- select one high-cost cross-functional decision loop per partner;
- inventory identity, key management, SIEM, backup, data catalog, legal hold,
  and deployment standards;
- map the product to NIST CSF 2.0, NIST AI RMF, and the customer's own control
  system; evaluate ISO/IEC 42001 only as an organization-wide management goal;
- define the system boundary and shared-responsibility model.

**Exit gate**

- two partners fund a staged pilot;
- one decision loop has authoritative measures, named owners, and a measurable
  cost of current delay or blindness;
- no partner requires the free core to lose a feature;
- the assurance scope is written before any claim.

### LE1 — Storage, identity, and policy contracts

**Work**

- define `MemoryStore`, `IdentityProvider`, `PolicyDecision`, `KeyService`,
  `AuditSink`, and `EvidenceConnector` contracts outside the MIT public API
  until proven;
- implement tenant and sensitivity isolation with per-request policy decisions;
- integrate SAML/OIDC and SCIM; test deprovisioning and group drift;
- add customer KMS/HSM envelope encryption and rotation tests;
- build policy simulation, approval, versioning, rollback, and deny receipts;
- model regional placement and cross-border denial;
- mutation-test every isolation and policy guard.

**Exit gate**

- red-team attempts cannot cross tenant, project, sensitivity, region, backup,
  cache, log, export, or support boundaries;
- a deprovisioned user loses active and cached access within the stated target;
- key rotation and revocation work without losing accepted memory;
- the old or bypassed guard demonstrably fails the test suite.

### LE2 — Availability and lifecycle

**Work**

- define availability and recovery targets per service, not one vague SLA;
- add replication/HA only behind a store contract proven under concurrent
  failure;
- automated backups, point-in-time recovery, restore rehearsals, and regional
  disaster drills;
- online and offline upgrade paths with compatibility checks and rollback;
- capacity tests across realistic drawer size, retrieval mix, and policy load;
- retention, legal hold, defensible deletion, export, and customer exit;
- support access that is disabled by default, time-limited, approved, and
  recorded.

**Exit gate**

- recovery-point and recovery-time objectives pass scheduled destructive
  drills;
- no acknowledged write disappears across the tested failure matrix;
- legal hold blocks deletion and ordinary retention cannot override it;
- a customer can export and leave without Patrick running a private tool.

### LE3 — Audit and assurance

**Work**

- append-only administrative, policy, access, export, backup, and model/host
  events with a documented event schema;
- tamper-evident event batches and customer-held verification material;
- SIEM export, evidence API, control narratives, data-flow diagrams, asset
  inventory, and shared-responsibility matrix;
- NIST SP 800-218 secure-development evidence, SBOMs, signed builds, dependency
  review, vulnerability handling, and annual penetration testing;
- privacy impact assessment, data-processing terms, subprocessor inventory, and
  deletion verification;
- SOC 2 readiness, then Type I/Type II only when customer demand and company
  operations justify the cost;
- ISO/IEC 27001 or 42001 only through an accredited independent certification
  body and only for the stated management-system scope.

**Exit gate**

- an independent assessor can reproduce a sampled claim from evidence without
  private oral explanation;
- severe penetration-test findings are closed and retested;
- audit logs omit raw drawer content by default while retaining useful actor,
  action, target, policy, and result evidence;
- every public assurance statement links to a precise scope.

### LE4 — Organizational model and data quality

**Work**

- connect one decision domain to no more than five authoritative sources;
- define each measure's formula, grain, dimensions, owner, source, freshness,
  exclusions, and revision history;
- profile completeness, timeliness, validity, duplication, and reconciliation;
- record data-quality receipts beside every derived signal;
- link historical decisions and predictions to observed measures without
  rewriting the source records;
- mark policy changes, reorganizations, acquisitions, and metric-definition
  changes so the engine does not treat structural breaks as ordinary trends;
- create read-only organizational maps for processes and dependencies, not
  secret employee dossiers.

**Exit gate**

- finance/operations owners reconcile the chosen measures to their source
  systems;
- stale or conflicting inputs make the engine abstain;
- every derived signal can be reproduced from versioned definitions and source
  references;
- a reorganization does not merge or leak the old and new authority domains.

### LE5 — Shadow recommendation loop

**Work**

- pre-register the target measure, baseline, horizon, constraints, and review
  process;
- run the engine beside the existing executive/operational review for 8–12
  weeks with no actuation rights;
- detect improving and decaying sections, retrieve prior decisions and
  interventions, and generate bounded recommendations;
- require alternative explanations, counterevidence, uncertainty, owner,
  predicted effect, guardrails, and rollback;
- settle every recommendation after its horizon, including ignored proposals;
- compare detection time, precision, calibration, and avoided loss against the
  existing process.

**Exit gate**

- the engine beats the registered baseline in at least one valuable domain;
- false alarms and missed changes stay within the customer's agreed limits;
- reviewers can identify the controlling evidence without asking the model to
  recreate its reasoning;
- no recommendation crosses its authority, data, or business-unit scope;
- the customer elects to proceed to controlled experiments.

**Kill signal:** the engine tells persuasive stories after the fact but cannot
predict changes or improve detection on held-out periods.

### LE6 — Controlled experiments, no autonomous management

**Work**

- convert accepted recommendations into small experiments with an accountable
  human owner;
- cap duration, affected population/system, budget, and reversible actions;
- record safety, legal, customer, workforce, and financial guardrails;
- use stepped or randomized tests where the organization can do so lawfully and
  responsibly; use matched comparisons when it cannot;
- settle outcomes and transfer only strategies that repeat across independent
  cases;
- keep write-back disabled unless a later, separately approved safety case
  proves the exact actuation path.

**Exit gate**

- accepted interventions improve the target without violating guardrails;
- rejected and failed interventions remain visible;
- no strategy promotes itself;
- the organization can turn the engine off and continue operating.

### LE7 — General availability

**Work**

- contractual SLA, support tiers, incident notification, business continuity,
  security addendum, DPA, and end-of-life terms;
- documented deployment profiles with a compatibility matrix;
- reference architecture, capacity model, migration guide, admin/user/auditor
  manuals, and customer exit runbook;
- partner training and certification only after Patrick's team can audit partner
  work;
- annual control, threat, model, and product-family review.

**Exit gate**

- three production customers complete two quarterly settlement cycles;
- upgrades and disaster drills pass without Patrick as sole operator;
- support load, security obligations, and gross margin support the contract;
- renewals cite measured operational value rather than fear of migration.

## Success measures

- cross-session and cross-host continuity success/abstention;
- unauthorized retrieval and policy-bypass rate;
- mean time to detect material operational change;
- recommendation precision, calibration, and time-to-settlement;
- measured effect of accepted interventions and guardrail violations;
- percentage of signals with current, reconciled definitions;
- recovery objectives, patch time, and audit-evidence completion;
- operator/support time per thousand users;
- paid renewal and expansion tied to measured value.

## Business model to test

Annual platform license priced by governed deployment scope—not by tokens or
drawers—with separate implementation, assurance, and premium support. Private
deployment and customer data ownership are base requirements. Charge for the
hard operational work: policy scale, connectors, evidence, HA, lifecycle,
assurance, and support.

## Principal risks

- **Causal theater.** A remembered sequence is not proof of cause. Preserve
  alternative explanations and require prospective settlement.
- **Executive confirmation machine.** Independent data owners and dissenting
  evidence need a first-class path; the sponsor cannot edit away failed calls.
- **Worker surveillance.** Default to process/team measures, minimum necessary
  data, purpose limits, retention limits, and workforce review.
- **Policy/data-plane split fails open.** Deny when identity, policy, key, or
  classification state is unavailable.
- **Enterprise feature gravity damages the core.** Commercial contracts stay at
  the seam; core simplicity remains a protected constraint.

## Sources guiding the assurance path

- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final)
- [NIST SP 800-218 — Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST AI RMF Playbook — Measure](https://airc.nist.gov/airmf-resources/playbook/measure/)
- [ISO/IEC 42001 — AI management systems](https://www.iso.org/standard/42001)
- [CISA — Secure by Design](https://www.cisa.gov/securebydesign)

This roadmap consumes foundation packets F0–F9 from the
[commercial product-family decision](../2026-08-30-commercial-product-family.md).
