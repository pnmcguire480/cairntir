# Landed commitments

These executable assertions preserve shipped regression contracts after closed
plans were removed from the working tree. Run
`python scripts/check_landed_commitments.py`; malformed or unmet assertions
fail CI. Assertion kinds are `file`, `symbol`, `param` (`function:parameter`),
and `test`. Do not remove assertions to make a failing implementation pass.

Historical design narratives remain in Git at
[`ff25ea3`](https://github.com/pnmcguire480/cairntir/tree/ff25ea3/plans).
The old front-door plan's self-existence assertion now names this consolidated
record; its runtime and test assertions are unchanged.

## landed-commitments

```cairntir-commitments
symbol src/cairntir/handoff.py compose
param  src/cairntir/handoff.py compose:budget_chars
test   tests/unit/test_handoff.py test_included_drawers_are_returned_whole
file   docs/release-cadence.md
```

## 2026-08-04-honest-and-whole

```cairntir-commitments
file   scripts/check_store_health.py
file   scripts/repair_leaked_metadata.py
file   scripts/vault_sync.py
symbol src/cairntir/memory/anchors.py recall_for_change
symbol src/cairntir/memory/store.py repair_anchors
file   scripts/backfill_anchors.py
symbol src/cairntir/memory/anchors.py RepoIndex
symbol src/cairntir/memory/anchors.py propose_anchors
test   tests/unit/test_anchors.py test_backfilled_anchors_are_verified_against_disk
test   tests/unit/test_anchors.py test_repo_index_will_not_drop_a_prefix_the_author_asserted
param  src/cairntir/mcp/backend.py remember:model
param  src/cairntir/memory/store.py add:model
test   tests/integration/test_mcp_backend.py test_remember_records_the_authoring_model
test   tests/integration/test_mcp_backend.py test_two_models_in_one_session_are_recorded_separately
param  src/cairntir/mcp/backend.py remember:anchors
param  src/cairntir/mcp/backend.py remember:claim
param  src/cairntir/mcp/backend.py remember:predicted_outcome
symbol src/cairntir/mcp/backend.py settle
param  src/cairntir/mcp/backend.py session_start:budget_chars
test   tests/integration/test_mcp_backend.py test_settle_writes_delta
test   tests/integration/test_mcp_backend.py test_session_start_honours_the_budget
test   tests/unit/test_readme.py test_tool_surface_version_matches_the_server
symbol src/cairntir/cli.py vault_sync_cmd
symbol src/cairntir/vault.py plan_sync
symbol src/cairntir/vault.py apply_sync
param  src/cairntir/cli.py vault_sync_cmd:check
test   tests/unit/test_vault_sync.py test_check_exits_nonzero_when_a_walkthrough_has_no_drawer
test   tests/unit/test_vault_sync.py test_check_writes_nothing_even_when_it_finds_drift
symbol src/cairntir/handoff.py is_open_prediction
symbol src/cairntir/handoff.py open_prediction_count
test   tests/unit/test_handoff.py test_an_unsettled_prediction_gets_its_own_section
test   tests/unit/test_handoff.py test_a_settled_prediction_is_not_open
test   tests/unit/test_handoff.py test_a_wing_with_no_predictions_spends_nothing_on_the_section
test   tests/unit/test_handoff.py test_two_calls_with_open_predictions_are_byte_identical
symbol src/cairntir/provenance.py with_trust
symbol src/cairntir/memory/store.py reattest_legacy_trust
symbol src/cairntir/memory/store.py legacy_migration_drawer_ids
file   scripts/reattest_legacy_trust.py
test   tests/unit/test_reattest_trust.py test_reattest_moves_only_legacy_migration_drawers
test   tests/unit/test_reattest_trust.py test_reattest_keeps_all_three_trust_copies_consistent
symbol src/cairntir/errors.py ContentIntegrityError
test   tests/unit/test_store.py test_add_rejects_tool_call_markup
test   tests/unit/test_store.py test_add_rejects_trailing_envelope_even_with_metadata
test   tests/unit/test_store.py test_add_allows_quoted_markup_when_metadata_present
test   tests/unit/test_store.py test_add_rejects_malformed_anchors
symbol src/cairntir/handoff.py settled_prediction_ids
test   tests/integration/test_seams.py test_settling_a_prediction_closes_it_in_handoff
file   scripts/check_seams.py
test   tests/integration/test_seams.py test_settle_writes_a_delta_a_later_session_can_read
file   src/cairntir/health.py
param  src/cairntir/cli.py doctor:gate
test   tests/unit/test_doctor.py test_gate_fails_on_a_damaged_store
test   tests/unit/test_doctor.py test_gate_skips_loudly_when_there_is_no_store
param  src/cairntir/mcp/backend.py recall:full_content
test   tests/integration/test_mcp_backend.py test_recall_full_content_returns_whole_drawers
test   tests/integration/test_mcp_backend.py test_recall_full_content_names_oversize_hits
symbol src/cairntir/mcp/backend.py _prediction_nudge
test   tests/integration/test_mcp_backend.py test_remember_nudges_when_a_claim_has_no_prediction
test   tests/integration/test_mcp_backend.py test_remember_does_not_nudge_a_claimless_drawer_about_predictions
```

## 2026-08-05-transcript-recovery

```cairntir-commitments
symbol src/cairntir/transcript.py RecoveryReport
symbol src/cairntir/cli.py recover_cmd
param  src/cairntir/mcp/backend.py handoff:recover_transcripts
file   src/cairntir/mcp/server.py
test   tests/unit/test_transcript.py test_kill_after_request_is_named_verbatim_on_first_handoff
test   tests/unit/test_transcript.py test_cursor_returns_an_honest_unsupported_receipt
test   tests/unit/test_transcript.py test_recovery_never_writes_without_explicit_selection
```

## 2026-08-06-hardening-sweep

```cairntir-commitments
file   scripts/check_no_silent_except.py
symbol scripts/check_no_silent_except.py check_file
symbol scripts/check_no_silent_except.py _is_noop
file   tests/unit/test_silent_except.py
test   tests/unit/test_silent_except.py test_the_exact_regression_that_shipped
test   tests/unit/test_silent_except.py test_unparseable_file_is_a_violation_not_a_skip
test   tests/unit/test_silent_except.py test_src_tree_has_no_silent_handlers
symbol src/cairntir/register.py _write_checkpoint
symbol src/cairntir/memory/store.py _parses_as_json
param  src/cairntir/mcp/backend.py recall:budget_chars
test   tests/integration/test_mcp_backend.py test_recall_full_content_budget_is_cumulative
test   tests/integration/test_mcp_backend.py test_recall_budget_exhaustion_is_not_reported_as_oversize
```

## 2026-08-10-the-default-layer-blind-spot

```cairntir-commitments
symbol src/cairntir/handoff.py RECENT_ACTIVITY
symbol src/cairntir/handoff.py _gather
param  src/cairntir/handoff.py _fit:deep_total
test   tests/unit/test_handoff.py test_on_demand_drawers_are_briefed_when_the_budget_has_room
test   tests/unit/test_handoff.py test_on_demand_never_displaces_identity_or_essential
test   tests/unit/test_handoff.py test_the_default_write_layer_is_a_layer_handoff_loads
test   tests/unit/test_handoff.py test_a_wing_of_only_deep_drawers_names_what_it_skipped
file   scripts/check_seams.py
symbol src/cairntir/memory/embeddings.py PRODUCTION_MODEL
symbol src/cairntir/memory/embeddings.py PRODUCTION_TOKEN_WINDOW
symbol src/cairntir/memory/embeddings.py PRODUCTION_DIMENSION
symbol src/cairntir/cost.py EMBEDDER_TOKEN_LIMIT
file   tests/eval/test_embedder_window.py
test   tests/eval/test_embedder_window.py test_declared_embedder_window_matches_the_model
test   tests/eval/test_embedder_window.py test_the_tail_of_a_long_document_changes_its_vector
test   tests/eval/test_longmemeval_subset.py test_longmemeval_subset_recall_at_5_production_embedder
```

## 2026-08-14-new-user-front-door

```cairntir-commitments
symbol src/cairntir/hosts.py CURSOR_USER_RULE_PASTE_HINT
symbol src/cairntir/cli.py _setup_wire_user_hosts
symbol src/cairntir/cli.py _echo_manual_cursor_rule
test   tests/unit/test_cli.py test_setup_succeeds_when_claude_cli_missing
test   tests/unit/test_cli.py test_init_cursor_user_prints_paste_ready_rule
test   tests/unit/test_hosts.py test_repo_policy_blocks_match_memory_policy
test   tests/unit/test_readme.py test_how_to_use_is_not_the_v0_product
file   docs/how-to-use.md
file   docs/landed-commitments.md
file   plans/README.md
symbol src/cairntir/memory/store.py wing_exists
test   tests/unit/test_store.py test_wing_exists_is_sql_exists_not_a_materialised_row
```

## 2026-09-02-bounded-hotfix-ledger

```cairntir-commitments
symbol src/cairntir/hotfix.py HotfixCoordinator
symbol src/cairntir/hotfix.py HotfixCommand
symbol src/cairntir/hotfix.py HotfixReceipt
symbol src/cairntir/mcp/backend.py hotfix
symbol src/cairntir/cli.py hotfix_cmd
file   docs/recipes/bounded-hotfix/recipe.toml
test   tests/unit/test_hotfix.py test_same_failure_produces_one_stable_fingerprint
test   tests/unit/test_hotfix.py test_authority_preflight_attempt_and_independent_verification_complete
test   tests/unit/test_hotfix.py test_unchanged_failed_state_cannot_be_attempted_again
test   tests/integration/test_seams.py test_hotfix_mcp_and_coordinator_enforce_the_same_ordering
```

## 2026-09-03-reason-loop-hardening

```cairntir-commitments
symbol src/cairntir/reason/loop.py ReasonLoop
symbol src/cairntir/reason/model.py Outcome
symbol src/cairntir/learning.py propose_multi_episode_discoveries
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_cross_scope_hypothesis_before_writing
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_outcome_for_a_different_hypothesis
test   tests/unit/test_reason_loop.py test_reason_loop_rejects_outcome_without_an_experiment
test   tests/unit/test_reason_loop.py test_successful_step_preserves_explicit_surprise_delta
test   tests/unit/test_reason_loop.py test_non_durable_memory_rejects_idempotency_key
test   tests/unit/test_learning.py test_multi_episode_reflection_ignores_unbound_outcome_shaped_drawers
test   tests/unit/test_learning.py test_multi_episode_reflection_keeps_rooms_separate
test   tests/unit/test_learning.py test_multi_episode_reflection_counts_each_prediction_once
test   tests/unit/test_cli.py test_replay_extends_supersedes_chain
test   tests/unit/test_cli.py test_recipe_run_preserves_explicit_delta
```

## field-report-2026-08-02

```cairntir-commitments
symbol src/cairntir/cost.py measure
symbol src/cairntir/cost.py corpus_stats
test   tests/unit/test_cost.py test_the_tool_catalog_is_counted_because_it_is_never_free
test   tests/unit/test_determinism.py test_session_start_is_byte_identical_across_calls
symbol src/cairntir/handoff.py compose
param  src/cairntir/handoff.py compose:budget_chars
param  src/cairntir/mcp/backend.py handoff:budget_chars
test   tests/unit/test_handoff.py test_included_drawers_are_returned_whole
test   tests/unit/test_handoff.py test_a_drawer_too_big_for_the_budget_is_omitted_not_truncated
```
