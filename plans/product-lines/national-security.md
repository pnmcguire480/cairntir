# National Security Product Roadmap

**Working label:** Cairntir National Security. Do not use “classified,” “CUI
ready,” “FedRAMP,” “CMMC certified,” or an impact-level label in product naming
until the exact deployment and organization have earned the claim.

**Initial target:** Cleared primes, defense-industrial-base suppliers, federal
integrators, laboratories, and public-sector programs that need local or
disconnected AI continuity for **unclassified** work. CUI is the second gate.
Classified information is a later, sponsored path—not a startup feature.

## The honest opening position

Patrick does not need a personal security clearance to write and sell an
unclassified software product. Access to classified information is different.
A company needing classified access must be sponsored into the facility
clearance process by a government activity or cleared contractor; DCSA also
evaluates entity eligibility, facility security, and foreign ownership/control
concerns. Personnel clearances, facility clearance, system authorization, and a
product's technical controls are separate gates.

So the practical route is:

1. build and test an unclassified offline distribution;
2. partner with an experienced defense integrator or cleared prime;
3. support CUI inside a properly scoped contractor environment only after the
   organizational controls and assessment path exist;
4. enter classified work only under sponsorship and the customer's authorized
   architecture.

No roadmap document can pre-authorize classified handling.

## Mission promise

Preserve mission and engineering memory inside the authorized boundary, with no
network dependency, no vendor data path, exact provenance, tamper-evident
evidence, explicit authority, and deterministic recovery after interruption.
Help a mission owner see which program section is improving or degrading, which
decisions and constraints preceded the change, and which bounded intervention
is worth testing—without allowing an AI system to command personnel, move
funds, alter operations, or cross classification boundaries.

## Product principles

- **Disconnected by construction.** Install, operate, update, diagnose, back up,
  and verify without reaching Patrick, GitHub, PyPI, a model vendor, or a time
  service.
- **Customer is the authority.** The customer controls keys, identities,
  configuration, models, evidence, exports, and destruction.
- **Classification is external policy.** Cairntir labels and enforces configured
  domains; it does not determine classification.
- **No silent downgrade.** Missing identity, policy, key, provenance, clock, or
  integrity state blocks the action.
- **No home-grown cryptography.** Use validated modules in their approved
  configurations when FIPS requirements apply.
- **Every byte has a route.** Source, build, dependency, model, configuration,
  update, removable-media transfer, export, and destruction paths are
  documented and tested.
- **Recommendations are evidence, not orders.** Mission feedback runs in shadow
  mode and requires an accountable human decision.

## Reference control paths

The applicable controls depend on customer, contract, data, system boundary,
deployment, and authorizing authority. The product should supply evidence that
helps the customer; it must not market the following as interchangeable badges.

- **NIST SP 800-171 Rev. 3** for protecting CUI in nonfederal systems.
- **CMMC** when a DoD contract includes the required level; the program verifies
  contractor implementation for FCI/CUI, not a standalone software package.
- **NIST SP 800-53 Rev. 5** and agency overlays for federal system controls.
- **FedRAMP** only if Cairntir becomes a cloud service used by federal agencies;
  an on-premises or disconnected package is not made FedRAMP-authorized by a
  document set.
- **FIPS 140-3/CMVP** for validated cryptographic modules where required. A
  product using cryptography is not automatically FIPS validated.
- **NIST SP 800-207** for resource-focused zero-trust architecture.
- **NIST SP 800-218/218A** for secure software and AI development evidence.
- **32 CFR Part 117/NISPOM** for cleared contractor obligations where classified
  work exists.
- Customer/agency rules, contract clauses, data markings, export controls, and
  operational security requirements remain controlling.

## Product shape

### Disconnected data plane

- enclave-local stores separated by classification/sensitivity, mission,
  releasability, compartment, and need-to-know policy supplied by the customer;
- no cross-domain transfer feature in Cairntir; use the customer's approved
  transfer solution and process;
- customer-approved local embedding and model packages with recorded hashes,
  versions, evaluation, and allowed-use policy;
- deterministic bounded recall with authority and policy checks before content
  rendering;
- immutable provenance and validity receipts; recovered/imported evidence starts
  untrusted;
- customer-controlled backup, media handling, retention, and destruction.

### Offline administration and supply chain

- reproducible source-to-artifact build with two-person release review;
- signed manifests, SBOM, vulnerability disposition, provenance attestations,
  and dependency source archive;
- update bundles that declare exact from/to versions, database migrations,
  checks, rollback, and expiration;
- offline license file only if contract administration requires it; no periodic
  activation and no failure that locks the customer out of its memory;
- local health, capacity, integrity, audit, and diagnostics;
- configuration baselines with version, approval, drift detection, and rollback;
- removable-media import/export receipts and quarantine scanning hooks.

### Mission-feedback engine

- read-only, locally deployed connectors to approved mission, logistics,
  readiness, engineering, incident, schedule, and cost sources;
- customer-defined measures, classification markings, caveats, source quality,
  and authority;
- change candidates linked to prior decisions, assumptions, predictions, and
  observed outcomes;
- shadow recommendations with alternatives, uncertainty, guardrails, rollback,
  and settlement;
- no targeting, weapon employment, personnel adjudication, intelligence-source
  evaluation, or autonomous operational control in this product definition;
- no model or rule may move information between security domains.

## Roadmap

### NS0 — Counsel, partner, and scope

**Work**

- engage government-contract and export-control counsel before representing the
  product to defense or intelligence customers;
- identify a defense integrator, cleared prime, or laboratory partner that can
  define a real unclassified use case and later sponsor appropriate work;
- define prohibited data and environments for the first pilot;
- map the product/company/customer responsibility boundary;
- create an IP, dependency, supplier, and foreign-contribution inventory;
- decide whether the commercial entity and development environment can satisfy
  partner supply-chain restrictions.

**Exit gate**

- a partner signs a scoped unclassified evaluation agreement;
- the agreement states allowed data, system, users, models, support, evidence,
  incident, export, and destruction paths;
- nobody expects Patrick to handle classified material;
- counsel identifies the contract/export rules that actually apply.

**Kill signal:** the only interest depends on implying a clearance,
authorization, certification, or classified capability that does not exist.

### NS1 — Unclassified disconnected build

**Work**

- remove or compile-disable update checks and every nonessential network path;
- build from a vendored, hash-pinned dependency archive in a clean offline lab;
- produce signed artifacts, SBOM, source manifest, build recipe, test evidence,
  and vulnerability disposition;
- add offline install, upgrade, rollback, backup, restore, export, and removal;
- support approved local identity and operating-system hardening;
- add tamper-evident audit batches and customer-held verification keys;
- test local models/embeddings without download fallbacks;
- run dependency-confusion, malicious-package, poisoned-memory, malformed-media,
  rollback, corruption, and time-skew tests.

**Exit gate**

- a monitored installation makes zero network requests;
- a second clean room reproduces artifact hashes or records the exact accepted
  nondeterminism;
- a missing dependency/model fails closed without a fetch attempt;
- restore preserves all memory, provenance, policy, and evidence;
- the customer can verify the bundle without trusting Patrick's workstation.

### NS2 — Secure-development evidence

**Work**

- map engineering practices and evidence to NIST SP 800-218 and 800-218A;
- threat model data poisoning, prompt injection, malicious memory, privilege
  escalation, model substitution, insider access, update compromise, and
  cross-domain leakage;
- source review, secret scanning, SAST, dependency analysis, fuzzing, property
  tests, mutation tests, and annual independent penetration assessment;
- vulnerability disclosure, severity, remediation, customer notification, and
  emergency offline patch process;
- supplier review and end-of-support plan for Python, sqlite-vec, FastEmbed,
  model artifacts, operating systems, and build tools;
- archive exact source and build inputs for every supported release.

**Exit gate**

- every security claim has reproducible evidence;
- every critical guard has been watched fail under mutation or adversarial test;
- the offline patch drill reaches an isolated installation within the
  contractual target;
- unsupported dependencies have an explicit replacement or retirement path.

### NS3 — CUI-capable engineering package

**Entry condition:** a real partner has a scoped CUI use case and owns or names
the target system boundary. Do not enter this phase from internal enthusiasm.

**Work**

- map product evidence and shared responsibilities to NIST SP 800-171 Rev. 3;
- use FIPS 140-3 validated cryptographic modules in approved modes where the
  customer's requirements demand them;
- integrate customer identity, device, key, logging, incident, media, backup,
  and configuration services;
- document CUI flow, storage, processing, display, export, backup, support, and
  destruction;
- provide SSP inputs, diagrams, asset/SBOM lists, configuration guide, test
  results, POA&M inputs, and assessment evidence;
- support the customer's CMMC scope without claiming that Cairntir itself is
  “CMMC certified.”

**Exit gate**

- the partner's assessor accepts the product evidence within the stated system
  boundary;
- no CUI path reaches vendor support or an unauthorized model/service;
- required crypto is verified against active CMVP certificates and exact
  operating configurations;
- incident, backup, media, and destruction drills pass in the customer setting.

### NS4 — Mission-feedback shadow evaluation

**Work**

- choose one non-safety-critical mission-support domain with approved data;
- define target measures, sources, classification, owners, freshness,
  reconciliation, known gaps, and prohibited inferences;
- link decisions, assumptions, constraints, and predicted outcomes to later
  readiness/cost/schedule/quality measures;
- run change detection and recommendations beside the existing review process;
- require counterevidence, alternative explanations, uncertainty, and an
  accountable human reviewer;
- settle every recommendation on a pre-registered date;
- conduct adversarial review for manipulated measures and deceptive inputs.

**Exit gate**

- the engine improves detection or prediction on held-out periods;
- it abstains under stale, conflicting, unauthorized, or insufficient data;
- no recommendation escapes its approved mission and data scope;
- a reviewer reconstructs the evidence chain offline;
- the customer—not Cairntir—decides whether a bounded experiment follows.

### NS5 — Authorization support, not self-authorization

**Work**

- adapt evidence to the customer's RMF/ATO process, control baseline, overlays,
  inherited controls, and continuous-monitoring plan;
- support independent assessment and close findings with retest evidence;
- define configuration, vulnerability, incident, update, media, personnel, and
  support responsibilities in contract;
- produce a deployment-specific security guide and evidence archive;
- maintain continuous evidence offline after authorization.

**Exit gate**

- the customer's authorizing authority—not Patrick—accepts the system risk;
- every product claim matches that deployment's authorization boundary;
- changes trigger the agreed impact review instead of silently inheriting the
  old approval.

### NS6 — Classified path only under sponsorship

**Entry condition:** written sponsorship, facility/personnel eligibility,
contract need, authorized facilities/systems, and customer security direction.

**Work**

- follow the sponsor's classification guide, NISPOM responsibilities,
  information-system authorization, need-to-know, releasability, media,
  incident, and configuration rules;
- build and support only inside approved environments;
- separate public, commercial, CUI, and classified development/release chains;
- assume no support access and design customer/self-maintainer procedures;
- treat every transfer across domains as an external approved process.

**Exit gate**

- the sponsor and cognizant security/authorizing authorities approve the people,
  facility, system, process, and exact product configuration;
- marketing says only what those approvals cover;
- Patrick never receives classified data through ordinary support channels.

## Success measures

- zero unexpected network paths in disconnected tests;
- reproducible/verified artifact and SBOM coverage;
- time to verify, install, restore, roll back, and patch offline;
- policy/authority denial accuracy and cross-domain leakage attempts blocked;
- provenance and audit-chain verification;
- mission-change detection time and recommendation calibration;
- percentage of recommendations settled with complete evidence;
- independent findings closed and retested;
- customer-authorized deployments and renewals within exact scope.

## Business route

Sell through a cleared prime/integrator first, or as a subcontracted product
inside an existing authorized program. Price by deployment, assurance burden,
offline release/support obligations, and mission scope—not memory volume.
Expect long cycles and expensive evidence. A national-security contract that
cannot pay for secure maintenance is a liability, not prestige.

## Principal risks

- **Security theater.** Air-gapped is not automatically secure; supply chain,
  removable media, insiders, models, configuration, and support remain attack
  paths.
- **Accidental false claims.** Certification belongs to a scoped organization,
  module, service, or system—not the word Cairntir.
- **Clearance mythology.** Patrick's personal eligibility does not decide
  whether an unclassified product has value. Sponsorship and actual access need
  decide the classified route.
- **Data poisoning becomes mission advice.** Source authority, integrity,
  quality, alternatives, shadow mode, and human settlement are mandatory.
- **Fork drift.** National-security hardening stays in a downstream package;
  core security fixes return to MIT promptly when they do not reveal protected
  customer details.

## Primary sources

- [NIST SP 800-171 Rev. 3 — Protecting CUI](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/800-171r3/NIST.SP.800-171r3.html)
- [CMMC Program final rule](https://www.federalregister.gov/documents/2024/10/15/2024-22905/cybersecurity-maturity-model-certification-cmmc-program)
- [NIST SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [FedRAMP baselines](https://www.fedramp.gov/legacy/)
- [NIST FIPS 140-3](https://csrc.nist.gov/pubs/fips/140-3/final)
- [NIST CMVP validated modules](https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules)
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final)
- [NIST SP 800-218 — Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final)
- [NSA/CISA — AI data security guidance](https://www.cisa.gov/resources-tools/resources/ai-data-security-best-practices-securing-data-used-train-operate-ai-systems)
- [DCSA — Entity vetting, facility clearances, and FOCI](https://www.dcsa.mil/Industrial-Security/Entity-Vetting-Facility-Clearances-FOCI/)
- [DCSA — 32 CFR Part 117/NISPOM](https://www.dcsa.mil/Industrial-Security/National-Industrial-Security-Program-Oversight/32-CFR-Part-117-NISPOM-Rule/)

This roadmap consumes foundation packets F0–F9 from the
[commercial product-family decision](../2026-08-30-commercial-product-family.md).
