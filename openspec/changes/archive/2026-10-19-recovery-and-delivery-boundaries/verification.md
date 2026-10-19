---
task_id: OPS-1792305989358872
change: recovery-and-delivery-boundaries
commit_sha: 2f6ca0478e2578ea87ceb60ae28fd63fbddfc5d1
local: passed
local_evidence: Full make -j1 check passed on source 78a50c6c93f8e9fbfe1126925ff4905401b669ca, tree 523b0e873faabed4f4e1177fbd0a9fff6d81c377, with exit 0 and a clean checkout in 3337.767 seconds. The protected merge has the same tree. Log SHA256 773e238ee392c75570675a85baf9b65f9bbdb7a0ce5844b805140901bdcd60c3.
remote_ci: passed
remote_ci_evidence: Source PR CI 39244332000 passed all 92 jobs on virtual merge 71f86934f75e79079566fbfbf1a7c5b0510b95e3. Actual main CI 39258619952 attempt 1 passed all 92 jobs on protected merge 2f6ca0478e2578ea87ceb60ae28fd63fbddfc5d1. All five main workflows and nine protected contexts passed. All 47 exact fresh-main native cases and their cleanup passed.
dry_run: passed
dry_run_evidence: The full local gate passed 67 Bats cases, including 14 restore and 12 blue-green cases. Both synthetic recovery paths include current SSH and deployment admission and make no destructive stub calls. No real-host check mode or deployment was run.
staging: not_applicable
staging_evidence: The user prohibits deployment. No staging deployment or real-host check mode is in scope.
live: not_applicable
live_evidence: No production deployment, provider operation, SSH operation or credential action is in scope.
client: not_applicable
client_evidence: Producer refusal is tested with synthetic inputs. No physical-client or deployed-client acceptance is claimed.
artifact: passed
artifact_evidence: Accepted source and merge trees match. Complete portable and native manifests, cleanup, exact-source security analyses, manual role and runtime assertions, snapshots and independent source reviews passed. Whole main CI is recorded separately; task lifecycle receipts do not replace runtime acceptance.
---

# Verification

This record covers accepted source, protected merge and complete main CI
evidence. Task lifecycle receipts are recorded separately through `taskctl`.
No deployment is authorized by this record.

## Source and merge identities

| Boundary | Observed identity and result |
|---|---|
| Reviewed source | `78a50c6c93f8e9fbfe1126925ff4905401b669ca` |
| Accepted source tree | `523b0e873faabed4f4e1177fbd0a9fff6d81c377` |
| Source PR merge V | `71f86934f75e79079566fbfbf1a7c5b0510b95e3`, merging the reviewed source into `5c13c649dff5dd429696a6ea584b0441687473dc` |
| Protected main merge J | `2f6ca0478e2578ea87ceb60ae28fd63fbddfc5d1`, parent `5c13c649dff5dd429696a6ea584b0441687473dc`; tree equals the accepted source tree |
| Source delivery | [PR 331](https://github.com/po4yka/ripdpi-vpn-deploy/pull/331) merged through normal protected delivery; all nine required contexts passed, strict protection and administrator enforcement retained, no unresolved review threads |
| Actual J whole main CI | [Run 39258619952](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39258619952), attempt 1: all 92 jobs passed; all five workflows and nine protected contexts passed. Fresh-main native manifest: 47 exact cases, all passed with cleanup. |

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DR-ENV-ISOLATION | OPS-1792306162286391 | `test_terraform_env.py::test_default_alias_refuses_before_terraform`, `test_reserved_alias_refuses_backup_restore_and_cohort_before_private_inputs`, `test_prod_keeps_legacy_default_workspace`; Bats reserved-default and environment dry-run cases. Refusal precedes Terraform and private-input access; prod retains its legacy workspace. | Passed |
| REQ-DR-STATE-ATOMIC | OPS-1792306163221571 | `test_tf_state_backup.py::test_failed_encryption_publishes_no_partial_backup`, `test_concurrent_backups_remain_distinct_and_private`, `test_failed_restore_preserves_state_and_removes_private_candidate`, `test_fsync_failure_never_announces_success_or_prunes`, `test_nonprod_restore_uses_its_exact_state_path`. Real age fixtures verify private complete artifacts, prior-state preservation and owned cleanup. | Passed |
| REQ-DR-SHARE-READ | OPS-1792306164184160 | `test_subscription_share_permissions.py::test_actual_share_copy_repairs_modes_preserves_bytes_and_converges`; subscription-host `Verify nginx worker access and deny other local users`. Real Ansible repairs retained modes and preserves bytes; four directories are 0750, the nested file is 0640, the `www-data` account reads exact fixture bytes, and the `nobody` account cannot list or read. | Passed |
| REQ-DR-HOPPING-ADMISSION | OPS-1792306165929686 | `test_recipient_port_hopping.py::test_ripdpi_refuses_hopping_without_returning_partial_payload`, `test_actual_cli_refusal_has_no_partial_stdout`, `test_official_singbox_retains_supported_hopping`, `test_ripdpi_fixed_port_remains_supported`. Refusal precedes publication; supported exports remain valid. | Passed |
| REQ-DR-RESTORE-COMPLETE | OPS-1792306167846329 | `test_backup_restore_profile_completeness.py::test_missing_selected_artifact_cannot_replace_success`, `test_complete_selected_profile_restores_and_cleans`, `test_realm_absolute_tls_links_use_only_restored_targets`; `test_backup_profile_inputs.py::test_real_restic_selected_profile_pipeline`, `test_real_restic_realm_tls_symlink_dependencies_are_captured`; `test_backup_restore_drill_contract.py::test_drill_cleans_restored_secrets_before_atomically_publishing_success`. Real restic fixtures cover selected profiles and complete external TLS link chains; missing inputs fail before success and cleanup precedes publication. | Passed |
| REQ-DR-MIRROR-STOP | OPS-1792306168913886 | `test_subscription_mirror_lifecycle.py::test_retirement_refuses_uncertain_discovery`, `test_exact_timer_stops_before_service_and_only_loaded_units_are_disabled`, `test_retirement_precedes_payload_mutation_and_queued_handler_cannot_restart`. Role assertions verify timer-first retirement, inactive/disabled units after reload, all seven authority groups unchanged, check-mode nonmutation, repeated idempotence and exact administrative-mask retention. | Passed |
| REQ-DR-PROCEDURE | OPS-1792306169855109 | `test_restore_workflow_contract.py::test_recovery_plan_requires_admission_before_first_deploy`, `test_runbook_both_paths_require_shared_admission_and_exact_alias`, `test_recovery_plan_refuses_invalid_environment`; 14 restore and 12 blue-green Bats cases. Both recovery paths require current SSH, recovery foundation, Tailnet handoff, ownership migration and fresh deployment admission in order. | Passed |
| REQ-DR-DHCPV6 | OPS-1792306170781535 | `test_firewall_dhcpv6.py::test_render_scopes_both_port_pairs_to_one_effective_uplink`, `test_real_ansible_admission_refuses_before_mutation`, `test_exact_legacy_servers_never_create_a_global_prefix_accept`; native `test_dhcpv6.py::test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server` and `test_native_established_dhcpv6_tuple_cannot_cross_uplink_scope`. All original 12 bootstrap/rebind/legacy and six established-scope probes retain their positive and denial assertions; firewall role verifies the real uplink after repeated convergence. | Passed |

Named Python regressions are under `tests/unit/`; the two native DHCPv6 cases
are under `tests/native/transport_acceptance/`. The requirement rows establish
accepted source behavior. Integration step `OPS-1792306171697997` also requires
successful whole main CI for J. Its source and main gates passed. Task lifecycle
receipts remain separate from runtime acceptance.

## Observed checks

The complete local `make -j1 check` exited 0 on the accepted source with a clean
checkout. It passed 9194 unit tests, 45 subtests, 67 Bats cases, 322 vpnd tests,
Terraform validation and mock tests, policy checks, Ansible lint and syntax,
secret scans and snapshots. Its full log SHA256 is
`773e238ee392c75570675a85baf9b65f9bbdb7a0ce5844b805140901bdcd60c3`.
The result is transferred to J only through exact tree equality; it is not a
claim that a second local gate ran on J.

[Source CI 39244332000](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000)
completed successfully on V, attempt 1, with all 92 jobs successful. The exact
portable partition contains 9194 complete, disjoint cases. The exact native
partition contains all 47 selected cases across the core and two recovery
suites. DHCPv6 preflight, completion, lifecycle, hopping and both compensation
suites completed. Cleanup passed and all three owned outer containers were
removed. Four exact-V security analyses reported zero results; severity
thresholds and required checks were retained. Independent and structured source
review found no accepted actionable findings.

Manual semantic review read the executed assertions in these source-CI jobs:

- [subscription-host 118038788324](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038788324): share access/denial and modes passed; check mode preserved the running timer; timer-first retirement retained all seven authority groups and the administrative mask; repeated convergence had changed=0; destroy completed.
- [firewall 118038788293](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038788293): all 14 verify tasks ran without skips. All four IPv4/IPv6 timed entries survived real atomic replacement with `0 < remaining < previous`. Idempotence had changed=0 and destroy completed.
- [full-stack 118038787566](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038787566) and [full-stack-published 118038787653](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038787653): each ran all 11 verify tasks without skips, including targeted frontend recovery and private Hysteria hosts checks. Both had changed=0 on idempotence and completed destroy.
- [runtime 118038787254](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038787254): warm adoption 1, early rollback 10, ECH 13, full native 168, endpoint contract 10, delivery matrix 4, authenticated probes and guards 167, and final rollback 10 cases passed. UID/GID, reader-group and source-admission assertions ran; owned staging cleanup completed.
- [transport runtime 118038788027](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038788027) and [118038787704](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39244332000/job/118038787704): both configured shards passed all six cases each.

The source log index SHA256 is
`5ad1a548edfffc900a0fdfeeb1ad052f6bca72237ce51186600a471ec23e5760`.
The four-role capture receipt SHA256 is
`baeb9ca56e733192e7adf1ecf8847b813bfad2819e6db42a2187b26d62541d9c`.
Job conclusions alone were not used as proof of these semantic assertions.

## Protected main evidence

[Main CI 39258619952](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39258619952)
completed successfully on J, attempt 1, with all 92 jobs successful. Independent
acceptance verified the fresh J native case sets against the collected universe:
core 32, recovery 8 and 7, complete and disjoint, with no skips, duplicates or
foreign cases. All three raw records name J. Cleanup is true with empty resource
differences, and all three mandatory owned-container removal steps passed.
Both AWG pin and correction receipts match the expected source contract.

The fresh J manifest SHA256 is
`73ef55e6f5d82036e637aa88e24b2edeae6c455bbb872397d4cca1468f266daa`.
The core raw artifact 12191252242 SHA256 is
`47fb7037761b009a39b1959461d0612fc3d2d2ea368436dcda60293647e93e08`;
recovery artifact 12192052539 SHA256 is
`51140d491572801db1eb1964123da53bf8dd0c489ba45c8a68bb17a374f71df9`;
recovery artifact 12191937918 SHA256 is
`62e1a743c99a5b4b5ecbd17bb1228783c9bd7b87f0d4b0fe6172b7350f1fc6dc`.

The main CodeQL workflow 39258619364, REALITY validation 39258619366,
release-please 39258619516 and Scorecard 39258619464 also passed. All nine
protected status contexts passed. The main ref was J at acceptance. Source PR
results were not substituted for these main results. Later task metadata
commits must retain J as an ancestor and leave runtime source unchanged.

## Scope

The accepted fixture raises both veth ends before manual IPv6 addresses. Its
order regression and all 18 original packet assertions passed. Earlier
multicast-null observations did not uniquely prove a kernel cause; final CI
execution establishes the tested fixture outcome without such a causal claim.
Diagnostic retention before structured readiness remains limited; packet
observation fields do not expand production network authority.

No deployment, staging mutation, real-host check mode, provider action, SSH
operation, credential change or physical-client test was performed for this
task. Container runtime and synthetic recovery evidence does not establish
production service health or live client reachability. Those outcomes require
separate authorization and scoped acceptance.
