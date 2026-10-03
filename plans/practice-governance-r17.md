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

The public byte-preserving `acceptance/practice-governance-r17/controls.zip`
contains the independent contract/assertions/freeze and synthetic baseline,
candidate, mutation and adapted historical receipts. It contains no databases.
`tests/unit/test_practice_governance_independent.py` verifies the preimplementation
assertion/freeze hashes and replays all 21 fresh controls in normal pytest, using
isolated inert fixtures. Original historical controls remain unchanged; their
separate adapter uses current PR125 predecessor pins and does not claim a replay
of the missing historical plan or old runner. The qualified runtime raw-file
SHA256 is `6d0ed499a601857aa41bd3d5fbba93b57cd6f391fa6409853423bc3e46974023`;
platform newline normalization may change raw source bytes without changing Git
blob identity. All frozen archive entries retain their original exact bytes.
The [independent evidence inventory](acceptance/practice-governance-r17/README.md)
also retains a separate finite-scope PASS with 22 adversarial probes and eight
inherited damaged-envelope failures reproduced on exact base. No product repair
round was needed; general registry-corruption handling is not claimed.

At most two product repair rounds follow frozen acceptance. Only light serial
local checks are permitted; the existing full hosted CI runs on the final exact
head. Pass evidence must identify the head/tree, test bytes and run receipts.
Hosted runners cannot qualify private stores or real operator identity.

No merge, release, install or live adoption is authorized by this delivery.
The finite metadata capability can pass while parent integration and merge gates
remain blocked. Preserve independent acceptance and adversarial results separately
from source assertions and qualification claims.
