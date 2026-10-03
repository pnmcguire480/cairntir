# E22 independent scoped architecture/security review: PASS

The final repair2 runtime closes the reproduced acquisition-policy defect and the parent's final requested typed-cache-error case. This is a PASS for this bounded review, not approval to merge, publish, migrate or install. PR124 was treated as accepted and was not reopened.

## Verified result

The public pytest integration ran all twelve unchanged frozen controls in process: original eight, three Hub-layout/ref controls, and one offline cache-stat permission control. All passed. The deliberate in-memory bypass of pre-load verification was detected by the unchanged mutation assertion. Three pytest parameters passed in 0.81 seconds; underlying controls reported zero failures and zero errors.

The controls establish that the reproduced invalid assets/runtime cases refuse before acquisition; genuine missing-only bootstrap still acquires then constructs a distinct pinned/local-only model; changed pinned bytes refuse before construction; permission and path-loop failures in the tested seams are typed; the selected incomplete Hub snapshot is validated; malformed selected refs refuse; and an offline cache-stat denial raises EmbeddingError.

Runtime SHA256 values recorded by the final execution:

| File | SHA256 |
| --- | --- |
| artifacts.py | `549095cd71e8c208d5ca4d0f930af98ef0ec178bac1a4ca8d900dde53d4f4a5f` |
| embeddings.py | `fcbc6a5f8fa7de6a436e71e3e4f42ef4ea46a84ab214c2db53666a2df8f41cdc` |
| store.py | `900dc793536d64e89794e821cccabefdf1ec63fab99dd246224b546f6d285002` |

Final console receipt: `pytest-repair2-final.log`. Final detailed receipts:

- `pytest-repair2-final/test_frozen_e22_review_run_rev0/run_review_portable.json`
- `pytest-repair2-final/test_frozen_e22_review_hub_lay0/hub_layout_control_v2.json`
- `pytest-repair2-final/test_frozen_e22_review_cache_p0/cache_permission_control.json`

## Findings and repair custody

The initial candidate improperly treated invalid or incompletely checked evidence as missing-only acquisition authority. Initial eight controls produced five passes and three failures. Repair1 passed those eight but left the same pattern in incomplete Hub snapshots; the frozen layout extension reproduced it. The final selected-snapshot resolver passes those controls. Before final repair2 acceptance, the parent identified and requested reproduction of a cache-stat PermissionError escaping offline inspection; its frozen control reproduced the untyped error, and the final boundary translation passes it. The final acceptance occurred only after that closure change.

All initial failures, original tests, freezes, repair1 results, and preliminary repair2 receipts are preserved separately. No original assertion was relaxed. This reviewer made no runtime edits. Two product repair rounds were used by the parent; no further review expansion is requested.

## Portable deliverable and limits

Copy this complete review packet unchanged beneath `plans/acceptance/embedding-artifacts-1.14/review`. `test_e22_review.py`, governed by `PYTEST-FREEZE.json` and `PYTEST-CONTRACT.md`, runs the same frozen checks from pytest and verifies source import locations. The preserved historical absolute source path cannot override the target source already loaded by the portable adapters.

No remaining blocker was found within this scoped review. Independent acceptance, hosted platform checks, exact-tree reconstruction and external parent review remain separate gates. Windows real-symlink privilege skips are not passes; these synthetic fault checks do not substitute for capable-platform containment evidence. No real model, network acquisition, credentials, production store, install or API spend was used. Public shared-workspace evidence does not establish private custody or live-host qualification. Requested routing was gpt-6-astra/high; actual serving variant, effort and cost are not exposed.
