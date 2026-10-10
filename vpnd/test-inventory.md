# Baseline test transfer inventory

Baseline: `5365cbd4b33dff5b3d0be0e1f8c5cb2c9d17ac50`. This is a source inventory, not an executed-test result.

Enumerated 206 Rust test functions across 40 files, including proptest functions and inline tests. Each row requires an assertion-preserving destination in the implementation transfer manifest. Runtime parameter cases, helpers, generated property inputs and snapshot dependencies must also be retained; this count is not a collected-case count.

## Rust cases

| Baseline path | Attribute line | Test function |
|---|---|---|
| `vpnd/src/cli.rs` | 279 | `clip_without_ai_is_a_parse_time_error` |
| `vpnd/src/cli.rs` | 289 | `clip_with_ai_parses_and_carries_both_flags` |
| `vpnd/src/cli.rs` | 301 | `json_flag_is_rejected_for_unsupported_subcommands` |
| `vpnd/src/commands/deploy.rs` | 153 | `pipeline_matches_makefile_order_before_unconditional_cleanup` |
| `vpnd/src/commands/deploy.rs` | 183 | `skip_precheck_and_tag_on_success_flow_into_their_targets` |
| `vpnd/src/commands/deploy.rs` | 205 | `plan_summary_renders_placeholders_not_paths` |
| `vpnd/src/commands/doctor.rs` | 320 | `healthy_section_renders_invocation_and_stdout` |
| `vpnd/src/commands/doctor.rs` | 332 | `failed_section_marks_failure_and_keeps_both_streams` |
| `vpnd/src/commands/doctor.rs` | 352 | `capture_failure_section_records_the_error_without_streams` |
| `vpnd/src/commands/fleet.rs` | 75 | `rotate_flags_map_to_make_kvs` |
| `vpnd/src/commands/mod.rs` | 88 | `cleanup_runs_after_failure_and_original_error_wins` |
| `vpnd/src/commands/mod.rs` | 128 | `successful_pipeline_requires_successful_cleanup` |
| `vpnd/src/commands/mod.rs` | 139 | `ensure_host_rejects_unknown_alias_and_accepts_match` |
| `vpnd/src/commands/preflight.rs` | 55 | `guards_run_in_order_and_include_certs_by_default` |
| `vpnd/src/commands/preflight.rs` | 75 | `skip_certs_drops_only_the_cert_check` |
| `vpnd/src/commands/probe_matrix.rs` | 1238 | `json_summary_reports_path_and_counts` |
| `vpnd/src/commands/probe_matrix.rs` | 1292 | `fingerprint_ignores_only_identity_and_credentials` |
| `vpnd/src/commands/probe_matrix.rs` | 1305 | `durations_parse_valid_units` |
| `vpnd/src/commands/probe_matrix.rs` | 1318 | `durations_reject_malformed_units` |
| `vpnd/src/commands/probe_matrix.rs` | 1325 | `durations_reject_zero_and_multiplication_overflow` |
| `vpnd/src/commands/probe_matrix.rs` | 1332 | `windows_exclude_local_failures_and_do_not_bridge_indeterminate_gaps` |
| `vpnd/src/commands/probe_matrix.rs` | 1363 | `windows_record_blocked_onset_and_ok_recovery` |
| `vpnd/src/commands/probe_matrix.rs` | 1383 | `paired_targets_are_required` |
| `vpnd/src/commands/probe_matrix.rs` | 1407 | `paired_profiles_require_matching_transport_parameters` |
| `vpnd/src/commands/probe_matrix.rs` | 1453 | `concurrent_collection_is_ordered_and_isolates_timeout` |
| `vpnd/src/commands/probe_matrix.rs` | 1484 | `fixed_rate_schedule_does_not_accumulate_sweep_time` |
| `vpnd/src/commands/probe_matrix.rs` | 1498 | `synthetic_report_detects_dual_role_candidate` |
| `vpnd/src/commands/probe_matrix.rs` | 1508 | `analyzer_detects_protocol_specific_in_two_of_three_classes` |
| `vpnd/src/commands/probe_matrix.rs` | 1523 | `analyzer_detects_destination_class_collateral` |
| `vpnd/src/commands/probe_matrix.rs` | 1537 | `unknown_evidence_is_indeterminate_and_suppresses_positive_results` |
| `vpnd/src/commands/share.rs` | 287 | `token_file_gate_rejects_symlink` |
| `vpnd/src/commands/share.rs` | 298 | `token_file_gate_rejects_loose_mode` |
| `vpnd/src/commands/share.rs` | 307 | `token_file_gate_accepts_0600_raw` |
| `vpnd/src/commands/update.rs` | 173 | `refresh_writes_real_cache_and_fresh_hits_skip_fetch` |
| `vpnd/src/commands/update.rs` | 212 | `release_fetch_uses_real_http_json_and_rejects_http_or_schema_errors` |
| `vpnd/src/commands/update.rs` | 250 | `production_cache_load_enforces_ttl_and_rejects_corrupt_or_future_data` |
| `vpnd/src/commands/update.rs` | 287 | `normalize_tag_accepts_both_release_train_schemes` |
| `vpnd/src/commands/update.rs` | 296 | `notice_requires_a_strictly_newer_parseable_release` |
| `vpnd/src/commands/update.rs` | 322 | `stalled_connection_fails_within_the_explicit_timeout` |
| `vpnd/src/config.rs` | 129 | `runtime_dir_resolution_matrix_xdg_set_and_unset` |
| `vpnd/src/config.rs` | 154 | `secure_secrets_file_propagates_chmod_failure` |
| `vpnd/src/docs_bundle.rs` | 51 | `empty_report_produces_empty_excerpts` |
| `vpnd/src/docs_bundle.rs` | 60 | `report_with_no_keywords_produces_empty_excerpts` |
| `vpnd/src/docs_bundle.rs` | 69 | `fleet_status_keyword_triggers_excerpt` |
| `vpnd/src/docs_bundle.rs` | 86 | `asn_drift_keyword_triggers_incident_runbook` |
| `vpnd/src/docs_bundle.rs` | 97 | `burn_check_keyword_triggers_multiple_runbooks` |
| `vpnd/src/docs_bundle.rs` | 114 | `duplicate_runbook_suppressed_for_two_matching_keywords` |
| `vpnd/src/docs_bundle.rs` | 125 | `missing_runbook_file_silently_skipped` |
| `vpnd/src/protected_file.rs` | 101 | `private_write_preserves_an_unrelated_temp_file` |
| `vpnd/src/protected_file.rs` | 113 | `parallel_private_writes_with_shared_stems_do_not_collide` |
| `vpnd/src/protected_file.rs` | 130 | `metadata_gate_rejects_a_foreign_uid_even_for_a_private_regular_file` |
| `vpnd/src/runner/ansible.rs` | 219 | `inventory_scope_uses_public_address_and_exact_host_key` |
| `vpnd/src/runner/ansible.rs` | 235 | `inventory_scope_rejects_ambiguous_addresses_and_group_collisions` |
| `vpnd/src/runner/ansible.rs` | 258 | `inventory_scope_rejects_pattern_names_and_missing_scope_metadata` |
| `vpnd/src/runner/ansible.rs` | 282 | `playbook_program_is_ansible_playbook` |
| `vpnd/src/runner/ansible.rs` | 292 | `playbook_path_contains_playbook_name` |
| `vpnd/src/runner/ansible.rs` | 302 | `playbook_sets_ansible_config_env` |
| `vpnd/src/runner/ansible.rs` | 316 | `playbook_sets_vpn_secrets_file_env` |
| `vpnd/src/runner/ansible.rs` | 330 | `dry_run_appends_check_and_diff` |
| `vpnd/src/runner/ansible.rs` | 344 | `site_uses_site_playbook` |
| `vpnd/src/runner/ansible.rs` | 351 | `rotate_uses_rotate_credentials_playbook` |
| `vpnd/src/runner/make.rs` | 197 | `target_pushes_env_then_provider_after_name` |
| `vpnd/src/runner/make.rs` | 208 | `target_carries_resolved_secrets_file_after_provider` |
| `vpnd/src/runner/make.rs` | 224 | `target_program_is_make` |
| `vpnd/src/runner/make.rs` | 232 | `target_cwd_is_repo_root` |
| `vpnd/src/runner/make.rs` | 239 | `target_with_appends_kvs_after_provider` |
| `vpnd/src/runner/make.rs` | 255 | `target_with_no_extra_kvs_matches_target` |
| `vpnd/src/runner/make.rs` | 267 | `per_key_acceptance_table_passes_legitimate_values` |
| `vpnd/src/runner/make.rs` | 306 | `per_key_rejection_table_aborts_naming_key_and_rule` |
| `vpnd/src/runner/make.rs` | 346 | `unknown_keys_fail_closed_to_identifier_charset` |
| `vpnd/src/runner/make.rs` | 355 | `target_gates_context_values_before_building_invocation` |
| `vpnd/src/runner/make.rs` | 373 | `secrets_file_rejection_redacts_the_value` |
| `vpnd/src/runner/make.rs` | 390 | `target_with_first_failing_key_aborts_and_nothing_spawns` |
| `vpnd/src/runner/process.rs` | 353 | `sensitive_paths_are_masked_before_shell_quoting_without_changing_argv` |
| `vpnd/src/runner/process.rs` | 366 | `explain_plain_program_no_env_no_cwd` |
| `vpnd/src/runner/process.rs` | 372 | `explain_arg_with_spaces_is_quoted` |
| `vpnd/src/runner/process.rs` | 382 | `explain_arg_with_single_quote` |
| `vpnd/src/runner/process.rs` | 397 | `explain_arg_with_double_quote` |
| `vpnd/src/runner/process.rs` | 415 | `explain_arg_with_dollar_var` |
| `vpnd/src/runner/process.rs` | 426 | `explain_arg_with_newline` |
| `vpnd/src/runner/process.rs` | 437 | `explain_env_vars_appear_before_program` |
| `vpnd/src/runner/process.rs` | 453 | `explain_env_value_with_spaces_is_quoted` |
| `vpnd/src/runner/process.rs` | 463 | `explain_cwd_wraps_with_cd_and_ampersand` |
| `vpnd/src/runner/process.rs` | 472 | `explain_cwd_with_spaces_is_quoted` |
| `vpnd/src/runner/process.rs` | 482 | `explain_env_ordering_is_stable` |
| `vpnd/src/runner/sops.rs` | 40 | `decrypt_program_is_sops` |
| `vpnd/src/runner/sops.rs` | 50 | `decrypt_contains_decrypt_flag` |
| `vpnd/src/runner/sops.rs` | 57 | `decrypt_contains_output_flag_and_secrets_file` |
| `vpnd/src/runner/sops.rs` | 68 | `decrypt_contains_sops_source_file` |
| `vpnd/src/runner/terraform.rs` | 86 | `init_uses_environment_wrapper` |
| `vpnd/src/runner/terraform.rs` | 101 | `init_contains_init_subcommand` |
| `vpnd/src/runner/terraform.rs` | 108 | `plan_contains_var_file_for_env` |
| `vpnd/src/runner/terraform.rs` | 118 | `plan_contains_out_flag` |
| `vpnd/src/runner/terraform.rs` | 128 | `apply_references_tfplan` |
| `vpnd/src/runner/terraform.rs` | 138 | `output_contains_json_flag` |
| `vpnd/src/runner/terraform.rs` | 148 | `all_cmds_use_environment_wrapper` |
| `vpnd/src/state/registry.rs` | 169 | `resolve_for_rejects_unknown_alias` |
| `vpnd/src/state/registry.rs` | 179 | `resolve_for_rejects_env_or_provider_mismatch` |
| `vpnd/src/state/registry.rs` | 189 | `ipv4_limit_rejection_table` |
| `vpnd/src/state/registry.rs` | 207 | `ipv4_limit_rejects_zero_padded_octets` |
| `vpnd/src/state/registry.rs` | 215 | `ipv4_limit_accepts_literal` |
| `vpnd/src/state/registry.rs` | 221 | `ipv4_limit_requires_an_address` |
| `vpnd/src/state/version.rs` | 46 | `warn_on_skew_is_silent_when_versions_match` |
| `vpnd/src/state/version.rs` | 56 | `warn_on_skew_does_not_panic_on_mismatch` |
| `vpnd/src/state/version.rs` | 62 | `warn_on_skew_is_silent_when_deployed_with_absent` |
| `vpnd/tests/ai_docs_emit.rs` | 31 | `emits_llms_txt_index` |
| `vpnd/tests/ai_docs_emit.rs` | 58 | `emits_llms_full_txt_concatenation` |
| `vpnd/tests/ai_docs_emit.rs` | 84 | `emits_per_doc_copies_in_md_subdir` |
| `vpnd/tests/ai_docs_emit.rs` | 110 | `index_sorted_by_path` |
| `vpnd/tests/ai_docs_emit.rs` | 136 | `explain_mode_does_not_write_files` |
| `vpnd/tests/completions_snapshot.rs` | 23 | `bash_completion_snapshot` |
| `vpnd/tests/completions_snapshot.rs` | 29 | `zsh_completion_snapshot` |
| `vpnd/tests/completions_snapshot.rs` | 35 | `fish_completion_snapshot` |
| `vpnd/tests/completions_snapshot.rs` | 43 | `bash_completion_contains_vpnd_subcommands` |
| `vpnd/tests/completions_snapshot.rs` | 68 | `zsh_completion_contains_vpnd_subcommands` |
| `vpnd/tests/completions_snapshot.rs` | 92 | `fish_completion_contains_vpnd_subcommands` |
| `vpnd/tests/completions_snapshot.rs` | 116 | `share_completions_offer_only_token_input_flags` |
| `vpnd/tests/completions_snapshot.rs` | 141 | `bash_completion_mentions_global_flags` |
| `vpnd/tests/config_discover.rs` | 32 | `root_override_wins_over_ancestor_walk` |
| `vpnd/tests/config_discover.rs` | 41 | `missing_ansible_dir_returns_error` |
| `vpnd/tests/config_discover.rs` | 56 | `unknown_provider_returns_error` |
| `vpnd/tests/config_discover.rs` | 70 | `missing_root_dir_returns_error` |
| `vpnd/tests/config_discover.rs` | 87 | `context_env_and_provider_propagated` |
| `vpnd/tests/deploy_lifecycle.rs` | 133 | `reconverge_dry_run_cleans_plaintext_and_uses_scoped_inventory_name` |
| `vpnd/tests/deploy_lifecycle.rs` | 149 | `deploy_and_reconverge_preserve_primary_failures_and_still_clean` |
| `vpnd/tests/deploy_lifecycle.rs` | 168 | `registered_probe_uses_address_and_invalid_aliases_fail_before_work` |
| `vpnd/tests/deploy_lifecycle.rs` | 191 | `reconverge_explain_does_not_execute_or_harden_an_existing_file` |
| `vpnd/tests/deploy_lifecycle.rs` | 214 | `doctor_redacts_both_ai_and_every_bundle_entry` |
| `vpnd/tests/deploy_lifecycle.rs` | 245 | `share_without_xdg_decrypts_once_through_the_canonical_script` |
| `vpnd/tests/deploy_lifecycle.rs` | 281 | `every_decrypting_caller_stops_at_an_unsafe_or_missing_plaintext_file` |
| `vpnd/tests/deploy_lifecycle.rs` | 315 | `every_decrypting_caller_propagates_a_real_fd_chmod_failure` |
| `vpnd/tests/doctor_bundle.rs` | 11 | `redact_masks_historical_default_tmp_path` |
| `vpnd/tests/doctor_bundle.rs` | 22 | `redact_masks_resolved_path_outside_tmp` |
| `vpnd/tests/doctor_bundle.rs` | 36 | `redact_leaves_innocent_lines_unchanged` |
| `vpnd/tests/doctor_resilience.rs` | 103 | `all_steps_run_and_report_after_a_mid_run_failure` |
| `vpnd/tests/doctor_resilience.rs` | 145 | `healthy_run_exits_zero_without_failed_marks` |
| `vpnd/tests/doctor_resilience.rs` | 159 | `bundle_preserves_the_failed_step_evidence` |
| `vpnd/tests/doctor_resilience.rs` | 201 | `explain_mode_lists_the_steps_without_running_them` |
| `vpnd/tests/host_crud.rs` | 3 | `host_cli_persists_add_show_overwrite_and_remove` |
| `vpnd/tests/host_crud.rs` | 68 | `json_flag_emits_machine_readable_list_and_show` |
| `vpnd/tests/man_page.rs` | 58 | `man_pages_cover_every_subcommand_and_visible_flag` |
| `vpnd/tests/man_page.rs` | 142 | `man_pages_render_the_real_flag_values_the_replica_drifted_on` |
| `vpnd/tests/man_page.rs` | 178 | `man_pages_are_written_to_target_man_for_install` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 119 | `normal_run_checkpoints_private_report_and_jsonl_journal` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 158 | `signal_during_scheduled_wait_flushes_prior_ticks_without_synthetic_cells` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 194 | `signals_during_cells_flush_partial_evidence_and_reclaim_descendants` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 273 | `same_output_sessions_are_exclusive_and_lock_survives_reuse` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 307 | `output_names_with_shared_stems_keep_distinct_companions` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 332 | `unsafe_output_locks_and_reserved_suffixes_fail_before_make` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 374 | `failed_interrupted_checkpoint_preserves_last_valid_report_and_exits_one` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 499 | `share_stdin_and_reconverge_prompt_preserve_signal_termination` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 512 | `hanging_control_records_unknown_and_continues_real_make_cells` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 544 | `invalid_durations_fail_before_probes_without_panicking` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 575 | `unrepresentable_next_poll_finishes_with_observed_results` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 638 | `direct_and_foreground_signals_reclaim_probe_jobs_and_doctor_captures` |
| `vpnd/tests/probe_matrix_lifecycle.rs` | 779 | `invalid_config_and_profile_inputs_fail_before_probe_execution` |
| `vpnd/tests/probe_matrix_snapshot.rs` | 10 | `probe_matrix_report_snapshot` |
| `vpnd/tests/probe_matrix_snapshot.rs` | 17 | `probe_matrix_report_carries_required_top_level_fields` |
| `vpnd/tests/probe_matrix_snapshot.rs` | 39 | `probe_matrix_destination_classes_are_technical_signatures` |
| `vpnd/tests/proptest_redact.rs` | 42 | `redact_masks_any_historical_default_path` |
| `vpnd/tests/proptest_redact.rs` | 59 | `redact_masks_resolved_non_tmp_paths` |
| `vpnd/tests/proptest_redact.rs` | 76 | `redact_preserves_non_secret_lines` |
| `vpnd/tests/proptest_urlencode.rs` | 13 | `urlencode_no_whitespace_survives` |
| `vpnd/tests/proptest_urlencode.rs` | 24 | `urlencode_roundtrip_via_url_decode` |
| `vpnd/tests/qr_encode.rs` | 9 | `write_svg_produces_file` |
| `vpnd/tests/qr_encode.rs` | 21 | `write_svg_output_is_valid_xml_with_svg_root` |
| `vpnd/tests/qr_encode.rs` | 34 | `write_svg_contains_rect_or_path_elements` |
| `vpnd/tests/qr_encode.rs` | 48 | `write_svg_min_dimensions_at_least_256` |
| `vpnd/tests/recipient_render.rs` | 9 | `recipient_page_renders_with_expected_sections` |
| `vpnd/tests/recipient_render.rs` | 60 | `recipient_page_escapes_hostile_input` |
| `vpnd/tests/registry_roundtrip.rs` | 7 | `production_registry_io_roundtrip_and_fail_closed_errors` |
| `vpnd/tests/runner_execution.rs` | 38 | `capture_timeout_terminates_real_make_child_and_grandchild` |
| `vpnd/tests/runner_execution.rs` | 97 | `run_and_capture_report_real_process_outcomes` |
| `vpnd/tests/secrets_gate.rs` | 30 | `hardening_rejects_missing_plaintext` |
| `vpnd/tests/secrets_gate.rs` | 36 | `hardening_rejects_symlinks_without_chmoding_the_target` |
| `vpnd/tests/secrets_gate.rs` | 52 | `hardening_regular_plaintext_sets_0600_and_keeps_it_readable` |
| `vpnd/tests/secrets_gate.rs` | 63 | `load_accepts_private_read_only_files` |
| `vpnd/tests/secrets_gate.rs` | 72 | `file_gates_reject_fifos_without_waiting_for_a_writer` |
| `vpnd/tests/secrets_gate.rs` | 96 | `file_gates_never_follow_concurrently_swapped_symlinks` |
| `vpnd/tests/secrets_gate.rs` | 152 | `load_rejects_symlink_even_to_compliant_file` |
| `vpnd/tests/secrets_gate.rs` | 169 | `load_rejects_loose_mode_on_held_handle` |
| `vpnd/tests/secrets_gate.rs` | 184 | `load_accepts_compliant_0600_regular_file` |
| `vpnd/tests/secrets_parse.rs` | 16 | `fixture_loads_without_error` |
| `vpnd/tests/secrets_parse.rs` | 21 | `find_client_hit_returns_correct_client` |
| `vpnd/tests/secrets_parse.rs` | 30 | `find_client_miss_returns_none` |
| `vpnd/tests/secrets_parse.rs` | 36 | `extra_preserves_unknown_top_level_keys` |
| `vpnd/tests/secrets_parse.rs` | 47 | `malformed_or_empty_secrets_fail_without_a_typed_payload` |
| `vpnd/tests/secrets_parse.rs` | 66 | `load_fails_gracefully_for_missing_file` |
| `vpnd/tests/secrets_parse.rs` | 72 | `load_rejects_group_readable_secrets` |
| `vpnd/tests/secrets_parse.rs` | 82 | `load_rejects_symlinked_secrets` |
| `vpnd/tests/secrets_parse.rs` | 94 | `fixture_exposes_nginx_xhttp_server_name` |
| `vpnd/tests/share_bundle.rs` | 14 | `urlencode_encodes_colon_and_slashes` |
| `vpnd/tests/share_bundle.rs` | 32 | `urlencode_matches_subscription_host_route_expectation` |
| `vpnd/tests/share_bundle.rs` | 60 | `urlencode_is_reversible` |
| `vpnd/tests/share_bundle.rs` | 73 | `share_bundle_directory_structure_index_html` |
| `vpnd/tests/share_bundle.rs` | 105 | `share_bundle_qr_svg_is_valid_xml` |
| `vpnd/tests/share_bundle.rs` | 122 | `recipient_subscription_url_matches_host_and_client` |
| `vpnd/tests/share_bundle.rs` | 151 | `build_sub_urls_token_path_with_host_and_port` |
| `vpnd/tests/share_bundle.rs` | 179 | `build_sub_urls_port_443_omitted` |
| `vpnd/tests/share_command.rs` | 29 | `share_generates_a_bundle_for_a_canonical_xray_client` |
| `vpnd/tests/share_command.rs` | 109 | `invalid_tokens_from_stdin_and_file_fail_before_emission` |
| `vpnd/tests/share_command.rs` | 169 | `missing_or_blank_host_fails_before_creating_a_bundle` |
| `vpnd/tests/share_command.rs` | 204 | `failed_qr_publication_removes_its_temp_file` |
| `vpnd/tests/share_command.rs` | 214 | `cli_bundle_artifacts_are_private_even_with_permissive_umask` |
| `vpnd/tests/update_cache.rs` | 23 | `fresh_cache_drives_actual_notice_and_suppresses_current_release` |
| `vpnd/tests/update_cache.rs` | 63 | `explain_reports_endpoint_without_creating_cache_or_needing_repository` |

## Python consumer suites

These baseline files mention vpnd or Rust build contracts. Read every assertion and retain behavioral checks; replace compiler/package-specific checks with Python delivery checks. Also discover transitive consumers during execution.

- `tests/unit/test_ci_dependency_selection.py`
- `tests/unit/test_make_strict_gates.py`
- `tests/unit/test_monitor_reality_target.py`
- `tests/unit/test_mutation_workflow.py`
- `tests/unit/test_probe_matrix_contract.py`
- `tests/unit/test_release_chain.py`
- `tests/unit/test_vpnd_cargo_deny_contract.py`
- `tests/unit/test_vpnd_msrv_contract.py`
- `tests/unit/test_vpnd_release_tags.py`
- `tests/unit/test_vpnd_sbom.py`

## Data assets

- Transfer all `vpnd/tests/snapshots/` golden data, keeping report schema assertions intact. Review only parser-generator formatting changes, never deleted command or flag coverage.
- Preserve `vpnd/tests/proptest_redact.proptest-regressions` as explicit generated-property regression examples.
- Preserve `vpnd/config/probe-matrix-target.example.json`, tracked probe-matrix configuration/examples referenced by tests and packaged `vpnd/templates/recipient.html`.
- Obtain the executable baseline in an isolated worktree through the build gate during implementation; never run credentialed handlers to characterize behavior.

The implementation must compare this inventory to its selected source revision. New upstream tests require new mappings before retirement; deletion of source tests is not proof of equivalence.
