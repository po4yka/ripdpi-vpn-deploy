---
task_id: SEC-1792306869763633
change: security-delivery-audit
commit_sha: b9c2eb8071590f2b9e672034bbab575450970a6c
local: passed
local_evidence: "Full make check on 91c99bf1f9debdca295aa383ffc9e288febcfb13 exited 0: 8318 portable tests and 45 subtests, 65 BATS, 322 vpnd; 228 native cases deselected. The only later change removed five redundant test imports; its complete module passed 81 tests with fail-on-skip. All other bytes are identical. Accepted candidate and actual merged main have the same tree."
remote_ci: passed
remote_ci_evidence: "PR 332 merged as b9c2eb8071590f2b9e672034bbab575450970a6c with the accepted 3036c6fb candidate tree. Candidate CI 39131984939 passed all 92 jobs. Actual-main CI 39136968257 completed successfully at 2026-10-18 15:40:19 UTC with all 92 jobs successful. Exhaustive exact-main check-runs contain 97 success and one expected dispatch skip; all nine protected contexts passed. CodeQL, scorecard, REALITY validation and release-please also passed on the exact main SHA."
dry_run: not_applicable
dry_run_evidence: Source-only change; no real inventory or credentials are used.
staging: not_applicable
staging_evidence: No external rollout is authorized or required for source repair.
live: not_applicable
live_evidence: Source and isolated runtime scope only; no fleet outcome is claimed.
client: not_applicable
client_evidence: Unsupported consumer profiles are refused; no new client traffic capability is claimed.
artifact: passed
artifact_evidence: "Candidate core artifact 12139411496 and actual-main core artifact 12141150443 each passed all 29 cases and cleanup with no differences. Actual-main result SHA-256 is 8a2fc603f5da5956148fef379e0cff89fc6bfb9c9da44b952584e3e45f357eef. All eight engine identities and case outcomes match. Reviewed template snapshots and the fresh 31-contract peer comparison passed; all 16 requirements below have named regression evidence."
---

# Verification

PR #332 was squash-merged at 2026-10-18 14:39:18 UTC as `b9c2eb8071590f2b9e672034bbab575450970a6c`, with parent `140d0897c9f952deba943c74451de63c95241e3a`. Its tree `162a4303c6df0cb0c843f4ddc1f682d624ffc8cc` is exactly the accepted candidate tree. Actual merged-source CI passed. This record accepts the source repairs. The task remains in review until its separate archival commit.

## Source and validation evidence

| Boundary | Observed evidence | Result |
|---|---|---|
| Full local gate | `make check` on `91c99bf1f9debdca295aa383ffc9e288febcfb13`, tree `3500d02ec7141b88b436093e2e14f322c7456dc5`, exited 0. Results: 8,318 portable tests and 45 subtests, 65 BATS, 322 vpnd tests; 228 native cases were deselected for Linux CI. | passed on stated source |
| Test-only cleanup | Candidate `3036c6fbf7ad66155c77ea47666ad7d1343d0a42` removes exactly five redundant local `import json` lines from `tests/unit/test_four_transport_runner.py`. Its complete module passed 81 tests in 2.74 s with `--fail-on-skip`. Structured autoreview found no findings, confidence 0.99. All other bytes, including production, native producer and parser code, are identical to `91c99bf1`. | passed within this boundary |
| Exact-candidate CI | [Run 39131984939](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39131984939) completed SUCCESS. All 92 selected jobs passed, including [required checks](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39131984939/job/117702447890). Exhaustive exact-SHA check-runs and PR rollup each contained 99 results: 98 success and one neutral. No failure, cancellation, timeout or pending result remained. | passed |
| Exact-candidate native core | [Core job 117689115951](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39131984939/job/117689115951), artifact `12139411496`: 29/29 cases passed, including both AWG dual-stack cases; cleanup was true with no differences. Tested synthetic merge `3169fb5bc818ae5eb0fdb56fbf8784255cf4a990` has the candidate and base as parents and tree `162a4303c6df0cb0c843f4ddc1f682d624ffc8cc`. | passed with exact tree binding |
| Actual main code | [PR #332](https://github.com/po4yka/ripdpi-vpn-deploy/pull/332) squash merge is observed. Main commit `b9c2eb8071590f2b9e672034bbab575450970a6c` has the same tree as accepted candidate `3036c6fb`. | merged; source tree matches |
| Actual-main native core | [Core job 117703359224](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39136968257/job/117703359224), artifact `12141150443`, passed 29/29 cases and cleanup with no differences. Artifact source is actual main `b9c2eb8071590f2b9e672034bbab575450970a6c`; all eight engine identities and case outcomes equal the accepted candidate artifact. Result SHA-256: `8a2fc603f5da5956148fef379e0cff89fc6bfb9c9da44b952584e3e45f357eef`. | passed with actual-main binding |
| Actual main CI | [Run 39136968257](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39136968257) completed SUCCESS at 2026-10-18 15:40:19 UTC. All 92 jobs passed. Exhaustive check-runs contain 97 success and one expected dispatch skip; all nine required contexts and all five workflows passed on the exact merged SHA. | passed |

The local gate and the later test-only cleanup are separate observations. No full local `make check` run on the merged commit is claimed. Candidate CI and merged-source CI are also separate gates.

Canonical command for the test-only cleanup module:

```sh
python3 -m pytest -q tests/unit/test_four_transport_runner.py --fail-on-skip
```

## Requirement evidence

The named regressions and completed candidate and actual-main CI accept all sixteen requirements. Earlier overlapping scoped counts are not final-gate totals.

| Requirement | Execution step | Focused behavior and regression evidence | Final result |
|---|---|---|---|
| REQ-AUDIT-AGE-DATA-KEY | SEC-1792306995752496 | Compromise recovery rotates the SOPS data key before new application credentials. `tests/unit/test_hardware_age_migration.py::test_real_sops_compromise_sequence_replaces_the_exposed_data_key` uses real synthetic SOPS/age and rejects the retired identity. | passed |
| REQ-AUDIT-AGE-RECIPIENT | SEC-1792306995752496 | Hardware selection binds one serial/slot and resumes without generation. `tests/unit/test_hardware_age_migration.py::test_released_commented_recipient_selects_one_exact_identity`, `::test_resume_keeps_identity_and_never_generates`; `tests/unit/test_hardware_age_make.py` covers literal selectors and command admission. | passed |
| REQ-AUDIT-AGE-MIGRATION | SEC-1792306995752496 | Additive migration retains document-specific recovery recipients and publishes only verified candidates. `tests/unit/test_hardware_age_migration.py::test_real_sops_explicit_additive_migration_preserves_each_recovery_path`, `::test_real_candidates_are_not_published_when_any_stage_fails`. | passed |
| REQ-AUDIT-RESTIC-GENERATION | SEC-1792306995752496 | Compromise guidance retains old local/remote repository generations until replacement backup and isolated restore pass. `tests/unit/test_hardware_age_migration.py::test_real_restic_password_change_keeps_the_prior_snapshot` verifies real synthetic restic snapshot continuity and distinct-generation guidance. | passed |
| REQ-AUDIT-STATE-PUBLICATION | SEC-1792306995752496 | State backup publishes complete synced ciphertext without overwriting an existing recovery name. `tests/unit/test_tf_state_backup.py::test_failed_encryption_never_publishes_a_recovery_name`, `::test_signal_removes_only_owned_incomplete_ciphertext`, `::test_same_timestamp_refuses_overwriting_complete_snapshot`. | passed |
| REQ-AUDIT-HTTP-ORIGIN | SEC-1792306996420715 | All three audited clients refuse redirects; notification origins require HTTPS. `tests/unit/test_authenticated_http.py::test_clients_do_not_send_bearer_to_any_redirect` uses real local HTTP servers for five redirect statuses and same/cross-origin targets; `::test_notification_origin_refuses_before_transport` checks admission. | passed |
| REQ-AUDIT-SUB-PUBLICATION | SEC-1792306997096858 | One atomic document binds subscription payload and expiry; malformed documents cannot fall back to legacy authority. `tests/unit/test_subscription_document.py::test_readers_racing_refresh_only_observe_complete_generations`, `::test_process_death_before_atomic_rename_preserves_old_document`, `::test_malformed_document_never_falls_back_to_legacy_authority`; HTTP, retention and mirror integration retain private route admission and expiry categories. | passed |
| REQ-AUDIT-HY-EXTRAS | SEC-1792306997096858 | Inherited PR #328 repair retains metadata for every Hysteria outbound. `tests/unit/test_client_payload_recipient_boundaries.py::test_multihost_hysteria_extras_retain_each_tag_and_distinct_source_metadata` checks exact tags and distinct source data. | passed |
| REQ-AUDIT-HY-COMPATIBILITY | SEC-1792306997096858 | Inherited PR #328 repair refuses unsupported RIPDPI hopping export and retains the official sing-box profile. `tests/unit/test_client_payload_recipient_boundaries.py::test_ripdpi_hysteria_hopping_refuses_instead_of_emitting_a_partial_profile`, `::test_official_singbox_retains_exact_hysteria_hopping`. | passed |
| REQ-AUDIT-BUNDLE-SEMANTICS | SEC-1792306997096858 | Bundle admission rejects shape-valid but invalid peer, key, address, hopping and calendar values with categorical diagnostics. `tests/unit/test_bundle_schema.py::test_shape_valid_peer_semantics_refuse_without_echo`, `::test_awg_relational_semantics_refuse`, `::test_shape_valid_invalid_calendar_expiry_refuses`; valid endpoint boundaries remain accepted. | passed |
| REQ-AUDIT-ALERT-ENVIRONMENT | SEC-1792306996420715 | Expected-target labels use the finite-silence gateway environment. `tests/unit/test_observability_control_plane_expected_targets.py::test_generated_alert_scope_matches_finite_silence_authority` renders each configured environment and compares labels through real gateway admission. | passed |
| REQ-AUDIT-TELEGRAM-FLOOD | SEC-1792306996420715 | All alert and canary send/edit attempts share the full monotonic deadline. `tests/unit/test_observability_telegram_delivery.py::test_flood_deadline_survives_sequential_real_http_webhooks_and_expires`, `::test_learned_flood_deadline_blocks_concurrent_real_http_webhooks`, `::test_canary_send_and_edit_share_alert_flood_deadline` use real local HTTP; short retry, final-attempt, busy and invalid-response boundaries remain covered. | passed |
| REQ-AUDIT-SSH-HYBRID | SEC-1792306997783845 | Managed policy prefers supported hybrid key exchange, retains Curve25519 fallback and guarded previous-policy rollback, and rejects finite-field DH. `tests/unit/test_sshd_ownership.py::test_managed_policy_prefers_supported_hybrid_and_refuses_modp`, `::test_baseline_promotes_exact_previous_policy_and_retains_rollback`; controller/bundle ownership tests retain transaction coverage. | passed |
| REQ-AUDIT-INVENTORY-ENCODING | SEC-1792309914259442 | Both base64 sites strip CR/LF without weakening typed inventory admission. `tests/unit/test_render_inventory.py::test_wrapped_base64_keeps_one_typed_host_line` covers LF/CRLF with observability on/off, the real renderer, strict decode and exact typed host values. | passed |
| REQ-AUDIT-WORKSPACE-DISCOVERY | SEC-1792315298976050 | Private seekable Git input removes the duplex pipe deadlock while retaining timeout, byte identity and filter refusal. `tests/unit/test_workspace_status.py::test_large_git_metadata_duplex_preserves_every_path_byte`, `::test_empty_metadata_input_delivers_eof_to_real_git`, `::test_blocked_git_metadata_query_keeps_its_deadline`, `::test_large_index_keeps_active_filter_refusal_without_execution`. | passed |
| REQ-AUDIT-NATIVE-EVIDENCE | SEC-1792324119267556 | Future AWG failures retain only five closed diagnostic categories. `tests/unit/test_four_transport_runner.py::test_real_pytest_junit_serializes_producer_property_for_runner` executes the actual probe failure/timeout hooks through real pytest JUnit. The module also rejects duplicate properties/JSON keys, oversized data, invalid types/cycles, private values, foreign cases and non-failures. Traffic acceptance, retries and timeouts stay unchanged. | passed |

## Review and contract evidence

The sole neutral check is [Trivy 117689633940](https://github.com/po4yka/ripdpi-vpn-deploy/runs/117689633940): the historical six-SARIF configuration comparison. This is not a CodeQL result. CodeQL on candidate `3036c6fb` succeeded; analysis `1975876814` retains known false-positive alert `1305`, and analysis `1975871062` has zero alerts. The five repeated-import notes are gone. There are zero unresolved review threads; this count does not describe CodeQL alerts.

Federation on candidate `3036c6fb` passed, with reported count 201. The final peer refresh at 2026-10-18T15:38:46+00:00 observed actual client main `e82b513ff8ad9da3f6163a52a71ac8337f1f1877` through the API before and after the object comparison. All 31 non-README contract blobs have the same path set and exact bytes as deploy main `b9c2eb8071590f2b9e672034bbab575450970a6c`, tree `162a4303c6df0cb0c843f4ddc1f682d624ffc8cc`. Paired task `TST-1792309202117414` remains done, 3/3; its issue, execution record and close receipt are byte-identical to terminal source `7409cd0154234fee588bd148ed2b07e3365cc286`. Both receipt content hashes are valid. Review `48e6329b40de95a76d1afd8a3fd7a46e3c41898d` is an ancestor of terminal `7409cd0154234fee588bd148ed2b07e3365cc286`, which remains an ancestor of actual client main. The owning seven JVM tests remain bound to `34fc33d082b94573ac2dcd278c030ed0b02e1f11`; no new JVM run was performed. The peer worktree remained clean and detached at `7409cd0154234fee588bd148ed2b07e3365cc286`.

Both Hysteria repairs were inherited from PR #328, integrated at `a14c339ccf8db8bce10bce5da22380a813a41605`; they were not implemented again. The synthetic SOPS fixture correction drains ciphertext stdin before returning fixture JSON. Its 128 KiB boundary regression preserves the production reader limits and deadlines.

## Historical native failure

Run `39122516322` on candidate `dcc25c2745cf97a7dbc82e210bb55c27ef407ca8` failed the one-member AWG dual-stack completion case. Sixteen other completion cases passed and cleanup showed no differences. Artifact `12134503970` retained generic failure locations without family, reconnect cycle or traffic phase. The cause remains unproved; no checksum cause is attributed to this run. The later categorical diagnostic repair cannot recover the missing historical detail or make a failed traffic assertion pass.

The older `91c99bf1` CI was cancelled for the five-line cleanup. Cancellation is neither a new native failure nor acceptance. The accepted `3036c6fb` run and exact-tree core artifact supply separate later evidence.

## Acceptance limits

The source repairs and regressions do not accept deployment, real credential migration, hardware/PIN/touch operations, remote restore, live SSH convergence, monitoring rollout, human Telegram receipt or physical-client VPN performance. These remain separate from source acceptance. Telegram cooldown is process-local and clears on relay restart, as specified.
