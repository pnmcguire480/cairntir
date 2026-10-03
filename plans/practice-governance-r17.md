# R17 opt-in practice metadata increment

This lane implements the approved finite attributed owner/version/rationale/review
date storage capability on reviewed PR125 head
`37ab0b1bb7e641adec8d2305b1546d1a35b1cd7e`, tree
`cb98d9d555dfbb9db466c15026b06f723369777b`. Full connected R17 remains partial;
R18 review scheduling, R19 guidance conflict resolution and R20 expanded lifecycle
policy remain separate roadmap work. No roadmap commitment is removed.

The [operator/API contract](../docs/procedure-governance.md) describes explicit
opt-in, exact legacy compatibility, immutable family histories, complete metadata
validation and family-specific unused version labels. Owner labels record
attribution and provide no authenticated identity or approval authority.

Runtime changes are limited to `src/cairntir/procedures.py`. The port introduces
no Obsidian import or correction-loop call, no schema/dependency/MCP surface,
credential, grant or installed-host change. It is independent of the correction
lane at runtime. Parent coordination retains shared source-version, changelog,
navigation and workflow-filter ownership; combined integration is still required.
This branch retains the base's unpublished source version and does not reserve a
new release number or imply that the correction feature is included.

Acceptance checks the actual user outcomes with temporary SQLite stores and
deterministic hash embeddings. The new dedicated unit regressions cover legacy
wire bytes/content/hash, explicit opt-in, append history, each metadata field,
invalid dates and Unicode, malformed stored governance, stripping and reused
versions. Existing procedure evaluation/operator controls run unchanged. Fresh
tester-authored controls are frozen before implementation and replayed unchanged;
a deliberately stripping source copy must fail direct assertions. A separate
whole-branch reviewer probes uncovered input classes and transaction behavior.

At most two product repair rounds follow frozen acceptance. Only light serial
local checks are permitted; the existing full hosted CI runs on the final exact
head. Pass evidence must identify the head/tree, test bytes and run receipts.
Hosted runners cannot qualify private stores or real operator identity.

No merge, release, install or live adoption is authorized by this delivery.
The finite metadata capability can pass while parent integration and merge gates
remain blocked. Preserve independent acceptance and adversarial results separately
from source assertions and qualification claims.
