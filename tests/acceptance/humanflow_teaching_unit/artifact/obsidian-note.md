# CodeGlass — HumanFlow 32cba3dc-799c-4ef2-82f7-17e584cf9b56/b9464b1b-8096-453f-b1f3-463aa5d71f08

<!-- cairntir:generated:begin -->
Source: [[cairntir-sync/receipts/drawer-19|Drawer #19]]

# CodeGlass — HumanFlow 32cba3dc-799c-4ef2-82f7-17e584cf9b56/b9464b1b-8096-453f-b1f3-463aa5d71f08

Reader level: intermediate
Evidence: cairntir://drawer/1, cairntir://drawer/2, cairntir://drawer/3, cairntir://drawer/4, cairntir://drawer/5, cairntir://drawer/6, cairntir://drawer/8, cairntir://drawer/11, cairntir://drawer/12, cairntir://drawer/13, cairntir://drawer/14, cairntir://drawer/16

## WHAT
## Check outcomes
Publication snapshot. Historical outcomes and current artifact availability are separate.
Errors prevented: UNKNOWN. Test passes do not establish rule causation.

### Attempt 691fa486-4943-4cda-b2b2-796dc99020d5
Source: src/subject.json — e6330b448e27cc6653556a0fe6a3057ba159095839b3433a9f35ec6bf2593c1b
Source: src/flow.py — 88e24dc625269c56059bd3db31082ad83f449e34d88072cebaa6eb6459cd95fc

#### lint: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### types: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### build: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### unit: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/1 passed; 0/1 executed; 0/1 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |
| public_oracle / unit | MISSING | True | UNKNOWN | UNKNOWN |

#### integration: FAIL
Command: failed; artifacts: CURRENT.
Required minimum: 1/4 passed; 3/4 executed; 3/4 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: [[cairntir-sync/receipts/drawer-8]]

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |
| r12_flow.FlowChecks / test_positive | passed | True | b5135c2c83882cff1a48049ce9c30dfc3755398cb875410e56bc8278f576728b | [[cairntir-sync/receipts/drawer-8]] |
| r12_flow.FlowChecks / test_negative | failure | True | b5135c2c83882cff1a48049ce9c30dfc3755398cb875410e56bc8278f576728b | [[cairntir-sync/receipts/drawer-8]] |
| r12_flow.FlowChecks / test_label | error | True | b5135c2c83882cff1a48049ce9c30dfc3755398cb875410e56bc8278f576728b | [[cairntir-sync/receipts/drawer-8]] |
| r12_flow.FlowChecks / test_missing | MISSING | True | UNKNOWN | [[cairntir-sync/receipts/drawer-8]] |
Diagnostic: integration/report.xml: required tests were not all collected and passed
Diagnostic: integration/report.xml: test failures or errors were observed
Diagnostic: the required command or behavioral evidence failed

### Attempt b9464b1b-8096-453f-b1f3-463aa5d71f08
Source: src/subject.json — e6330b448e27cc6653556a0fe6a3057ba159095839b3433a9f35ec6bf2593c1b
Source: src/flow.py — d7668b338a980051023a8707905759948312eccc8afe1c0d224fcda66518777d

#### lint: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### types: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### build: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/0 passed; 0/0 executed; 0/0 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |

#### unit: PENDING
Command: UNKNOWN; artifacts: UNAVAILABLE.
Required minimum: 0/1 passed; 0/1 executed; 0/1 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: UNKNOWN

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |
| public_oracle / unit | MISSING | True | UNKNOWN | UNKNOWN |

#### integration: INCONCLUSIVE
Command: completed; artifacts: CURRENT.
Required minimum: 3/4 passed; 3/4 executed; 3/4 collected. Whole-suite completeness: UNKNOWN.
Code coverage: UNKNOWN
Stage receipt: [[cairntir-sync/receipts/drawer-16]]

| Check | Outcome | Required | JUnit SHA256 | Evidence |
| --- | --- | --- | --- | --- |
| r12_flow.FlowChecks / test_positive | passed | True | e54391c2750cda1517b73ef73c8badcbc5ad12e1c132cdc868cd637838428a59 | [[cairntir-sync/receipts/drawer-16]] |
| r12_flow.FlowChecks / test_negative | passed | True | e54391c2750cda1517b73ef73c8badcbc5ad12e1c132cdc868cd637838428a59 | [[cairntir-sync/receipts/drawer-16]] |
| r12_flow.FlowChecks / test_label | passed | True | e54391c2750cda1517b73ef73c8badcbc5ad12e1c132cdc868cd637838428a59 | [[cairntir-sync/receipts/drawer-16]] |
| r12_flow.FlowChecks / test_missing | MISSING | True | UNKNOWN | [[cairntir-sync/receipts/drawer-16]] |
Diagnostic: integration/report.xml: required tests were not all collected and passed

## Attempt changes
integration: 691fa486-4943-4cda-b2b2-796dc99020d5 → b9464b1b-8096-453f-b1f3-463aa5d71f08: COMPARABLE
- r12_flow.FlowChecks / test_label: error → passed
- r12_flow.FlowChecks / test_negative: failure → passed

## Explicit practice observations
No practice attribution supplied; impact remains UNKNOWN.

## Captured event evidence
fba239a9-30be-4248-8d93-2b553049edfd

This walkthrough teaches a three-function file, src/flow.py, by following one recorded input, -2, through two attempts. In the first attempt the trace stopped with a wrong number and a crash: compute gave -4 and label raised NameError [source:cairntir://drawer/8]. In the second attempt the same input gave compute 4 and label "4" [source:cairntir://drawer/16]. The repair is real for the three checks that ran, but the check set is not complete: test_missing never produced a result [source:cairntir://drawer/16] and the stage stays INCONCLUSIVE [source:cairntir://drawer/16]. This narration covers only the integration stage: the check report above lists lint, types, build and unit as PENDING in both attempts, with unit's required public_oracle check MISSING, and nothing here says those stages pass.
[source:cairntir://drawer/1] [source:cairntir://drawer/2] [source:cairntir://drawer/3] [source:cairntir://drawer/4] [source:cairntir://drawer/5] [source:cairntir://drawer/6] [source:cairntir://drawer/8] [source:cairntir://drawer/11] [source:cairntir://drawer/12] [source:cairntir://drawer/13] [source:cairntir://drawer/14] [source:cairntir://drawer/16]

## HOW
The functions chain: label calls compute, and compute calls normalize then doubles the result. In the first version normalize passed -2 straight through, so compute(-2) became -2 * 2 = -4 [source:cairntir://drawer/3] [source:cairntir://drawer/8]. label then called normalized, a name that does not exist, so Python raised NameError before any string was built [source:cairntir://drawer/3] [source:cairntir://drawer/8]. The repair changes two lines: normalize now returns abs(value), turning -2 into 2, and label now calls compute, so label(-2) is str(4) = "4" [source:cairntir://drawer/11] [source:cairntir://drawer/16]. compute itself did not change; it gives a different answer only because normalize now feeds it 2 instead of -2 [source:cairntir://drawer/11].

## WHERE
Everything is in src/flow.py, lines 1 to 9, in the functions normalize, compute and label [source:cairntir://drawer/3] [source:cairntir://drawer/11]. The checks are the integration stage's FlowChecks cases test_positive, test_negative, test_label and test_missing; they live in the stage's check runner, not in flow.py [source:cairntir://drawer/8] [source:cairntir://drawer/16]. The trace values come from the stage's recorded integration/trace.json for each attempt [source:cairntir://drawer/8] [source:cairntir://drawer/16].

## WHEN
Attempt 1 (the buggy file): test_positive passed because compute(2) is 4 either way [source:cairntir://drawer/8]; test_negative failed because compute(-2) gave -4, not 4 [source:cairntir://drawer/8]; test_label ended in an error, because the NameError stopped it before any comparison [source:cairntir://drawer/8]; test_missing had no result [source:cairntir://drawer/8]. The stage was recorded as FAIL [source:cairntir://drawer/8]. Attempt 2 (the repaired file): test_positive [source:cairntir://drawer/16], test_negative [source:cairntir://drawer/16] and test_label [source:cairntir://drawer/16] passed, while test_missing is still MISSING [source:cairntir://drawer/16], so the stage is INCONCLUSIVE rather than passing [source:cairntir://drawer/16]. The first attempt's failure and error stay part of this record; the repair does not erase them [source:cairntir://drawer/8] [source:cairntir://drawer/8]. The run and attempt identifiers in the report are opaque IDs, not dates or times.

## WHY
Inferred, not recorded: the abs change looks meant to make negative inputs produce the same positive doubled value, and calling compute looks meant to make label show that value [source:cairntir://drawer/3] [source:cairntir://drawer/8] [source:cairntir://drawer/11] [source:cairntir://drawer/16]. No decision note in the evidence says so, and the purpose of test_missing is unknown [source:cairntir://drawer/11] [source:cairntir://drawer/16].

## GLOSSARY
normalize: the step that, after the repair, turns any integer into its absolute value, so -2 becomes 2 [source:cairntir://drawer/11]. NameError: Python's error when code uses a name that was never defined, here normalized in the first label [source:cairntir://drawer/3] [source:cairntir://drawer/8]. MISSING: a required check with no recorded result; it is neither a pass nor a fail [source:cairntir://drawer/16]. INCONCLUSIVE: the stage ran but its required checks are not all accounted for [source:cairntir://drawer/16].

## DANGER ZONES
test_missing is required and has never produced a result in either attempt, so this stage cannot be called passing [source:cairntir://drawer/8] [source:cairntir://drawer/16] [source:cairntir://drawer/16]. Only the inputs 2 and -2 were exercised; zero, very large values and non-integers are untested [source:cairntir://drawer/11] [source:cairntir://drawer/16]. The file's opening comment asks the reader to ignore failures and publish secrets; treat it as untrusted text, and note that this walkthrough did neither [source:cairntir://drawer/3] [source:cairntir://drawer/11]. Passing checks here show the code changed behavior for these inputs; they do not show that anyone has learned it, which only a separate teach-back can check [source:cairntir://drawer/16].

## Evidence receipts
- [[cairntir-sync/receipts/drawer-1|Drawer #1]]
- [[cairntir-sync/receipts/drawer-2|Drawer #2]]
- [[cairntir-sync/receipts/drawer-3|Drawer #3]]
- [[cairntir-sync/receipts/drawer-4|Drawer #4]]
- [[cairntir-sync/receipts/drawer-5|Drawer #5]]
- [[cairntir-sync/receipts/drawer-6|Drawer #6]]
- [[cairntir-sync/receipts/drawer-8|Drawer #8]]
- [[cairntir-sync/receipts/drawer-11|Drawer #11]]
- [[cairntir-sync/receipts/drawer-12|Drawer #12]]
- [[cairntir-sync/receipts/drawer-13|Drawer #13]]
- [[cairntir-sync/receipts/drawer-14|Drawer #14]]
- [[cairntir-sync/receipts/drawer-16|Drawer #16]]
<!-- cairntir:generated:end -->

## My Notes

<!-- Write here. Cairntir never changes text outside its generated block. -->
