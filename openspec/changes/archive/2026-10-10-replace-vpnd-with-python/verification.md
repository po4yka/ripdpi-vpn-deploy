---
task_id: VPD-1791615284178957
change: replace-vpnd-with-python
commit_sha: b88a41ad86fbe4f6590a07067713e9ebb15aa53c
local: passed
local_evidence: "Exact b88a41ad build-gate -- make -j1 check exited 0 with Cargo/rustc/rustup denied: 5882 portable tests, 18 native-provider tests, 56 Bats, 297 vpnd cases and 206 baseline-function parity; package, dependency, lint, schema, snapshot, Terraform and policy gates passed."
remote_ci: passed
remote_ci_evidence: "Exact b88a41ad CI run https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853 succeeded, including required aggregate and all four native test/package surfaces. All 90 check statuses terminal: 89 success, one Trivy-neutral historical configuration comparison; no failed or pending checks."
dry_run: not_applicable
dry_run_evidence: Source/package migration retains canonical Make deployment/controller inputs; synthetic local orchestration tests do not access fleet configuration.
staging: not_applicable
staging_evidence: No rendered server configuration or VPN runtime changed; native installed-artifact checks cover the distribution change.
live: not_applicable
live_evidence: No production deployment, SSH or provider mutation is in scope.
client: not_applicable
client_evidence: Recipient/QR contracts and exact synthetic Apple Vision decoding are observed; authenticated VPN traffic and physical-device acceptance are outside scope.
artifact: passed
artifact_evidence: "All four exact-b88 Linux/macOS x86_64/arm64 package jobs succeeded with denied Rust tools. Local two-build wheel/sdist/native-bundle byte comparison, offline install, parser/resources/manuals and interruption/corrupt-upgrade recovery passed; five-runtime-package policy/audit and 13 SBOM closure tests passed."
---

# Verification

## Integration and archival follow-up

PR 283 merged as `6a606bf4a7f23d5ebee075ce58057ff2bec2a684` after all nine
required checks passed on `95a3178605a0c504617dfb0574a88067b0e191f5`.
Both revisions have Git tree `6f14f132efb982c0ce4795aefdaf1e5de6cb443d`.
The final dispatcher return clarification is bytecode-identical under Python
3.12; its 297 tests, 206-function parity, lint and offline package gate passed.

`taskctl verify --archive-ready` passed before archival. `taskctl openspec
archive` synchronized 16 added and two modified requirements, removing none.
Its two ignored-Purpose warnings were resolved by appending the approved delta
paragraphs to the existing main Purpose sections, preserving their prior scope.
Strict validation passed all 27 items, the permanent-inventory regression passed
without an active change, and independent archival review approved the result.

Post-merge main CI exposed a failed one-shot pending-queue depth assertion in
`ansible/roles/observability_agent/molecule/enabled/verify.yml`. The log confirms
restored-runtime readiness and the unit, generation and queue-inode assertions;
it does not record the failing metric value or prove data loss. The pinned sender
can hold a dequeued block during transport retry, outside the pending-byte gauge.
The approved fixture remediation now proves delivery of specific historical
samples after rollback, retaining the existing guards. Accepted follow-up source
is `ee5be722805dbc2424b1a0d2b931ef6bb6aedbd9`: Linux enabled Molecule job
114257384069 passed convergence, idempotence and verification, including exact
node, nonce and pre-cutover timestamp reception through the real native sink.
CI run https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38067272809 completed
successfully with all nine required checks passed, planned selector skips and a
neutral Trivy historical-configuration comparison. Independent security review
approved the fixture; runtime, dependencies and pins were unchanged.

The exact-ee5be722 Rust-free `build-gate -- make -j1 check` exited 0 with the
task-owned Docker socket: 5,897 portable tests, 18 native-provider tests, 56 Bats,
215 Terraform cases, 59 policy assertions, 152 snapshots, 297 vpnd cases,
206-function parity and all validation/lint/offline artifact gates passed.
The local enabled Molecule attempt could not create the unchanged pinned image
on ARM; native acceptance belongs to the successful Linux job, not that attempt.
The failed main run above remains historical evidence and is not reclassified.

## Acceptance boundary

Accepted implementation source is `b88a41ad86fbe4f6590a07067713e9ebb15aa53c`.
Pre-retirement observations below belong to `09e0a141cede37d6808673d207862c025bddfebb`;
Rust was retained until those gates completed. Python runtime and transferred
assertions were unchanged by retirement. The exact-b88 Rust-free local gate and hosted required checks also completed
successfully. Acceptance covers source, CI and installed artifacts; real provider,
host and authenticated VPN/client acceptance remain outside this migration scope.

## Observed implementation evidence

- Pre-retirement `build-gate -- make check`: exit 0; 5,882 portable Python tests,
  18 native-provider tests, 56 Bats cases, 297 vpnd cases (54.44s), 215 Terraform
  cases, 59 policy assertions and 152 rendered/golden snapshots. Complete transfer
  verified all 206 baseline functions and collected passed parameter cases.
- Python Ruff/type checks, reviewed five-runtime-package hash/license/non-yanked
  policy and pip-audit passed. Real isolated offline installation, two-build byte
  comparison for wheel/source/platform bundle and native-wheel SBOM checks passed;
  the SBOM consumer suite passed 13 cases.
- Hermetic full mutation run at pre-retirement source: 1,239 total = 943 killed,
  17 detected timeout and 279 remaining survivors. Independent review closed
  the identified security guard gaps; surviving findings retain the existing
  mutation reporting contract. `no_tests`, skipped, suspicious, interrupted and segfault counts were
  all zero; clean baseline, forced probe, all 50 functions and 270 eligible lane
  cases ran. Retained results: `vpnd/mutants/run.YuvKfy/mutmut-cicd-stats.json` and
  module metadata. All seven previously substantive lifecycle mutants were killed
  in this full run: worker 70, terminate 5, execute 31–35. Survivors are findings,
  not a claim that all mutants were killed; verified survivor exit 2 is accepted,
  whereas backend/export/partial failures remain failures.
- Pre-retirement hosted comparison: all 90 check statuses terminal, 89 success and one
  Trivy-neutral historical comparison. This is not exact-b88 acceptance.
- At b88, the 70-case retirement-focused target passed and independent security
  review approved the 71-file retirement delta. Exact synthetic QR payload
  `https://vpn.example.com/sub/synthetic-Token_123` was decoded by Apple Vision;
  tests also retain private outputs, HTML escaping and SVG background/dimensions.

## Exact-source acceptance

`build-gate -- make -j1 check` on b88 exited 0: 5,882 portable tests,
18 native-provider tests, 56 Bats cases, 297 vpnd cases (59.18s), complete
206-function parity and all prerequisite validation/artifact gates passed.
The 123 native-runtime cases deselected by the portable command remain in their
separate required hosted lane. Rust-refusal sentinels returned 97; pip's optional
`rustc --version` user-agent probes tolerated the unavailable compiler, and no
Cargo invocation or compiler-backed build was needed.

Required CI run
https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853
completed successfully. All 90 statuses are terminal: 89 success and one neutral
Trivy comparison warning for historical main configurations, with no failed or
pending check. The required aggregate, native runtime/Molecule lanes, CodeQL and
four native vpnd test/package surfaces succeeded.

Independently observed exact-b88 native package jobs:

| Platform | Observed result | Hosted job |
|---|---|---|
| Linux x86_64 | success | https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853/job/114222277480 |
| Linux arm64 | success | https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853/job/114222277417 |
| macOS x86_64 | success | https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853/job/114222277413 |
| macOS arm64 | success | https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38055244853/job/114222277497 |

Every platform package job installs hash-locked wheels offline, checks parser
help/resources/manuals, compares artifact bytes and verifies failed-upgrade
recovery with Cargo/rustc refusal sentinels. The other required jobs and final aggregate also completed successfully.

## Requirement evidence

All mappings below were exercised in the pre-retirement source/consumer gates.
The exact-b88 full gate and hosted native jobs passed the same obligations
after retirement. Evidence identifies executable assertions rather than names alone.

| Requirement | Execution step | Observed assertion mapping | Result |
|---|---|---|---|
| REQ-PYCLI-SURFACE | VPD-1791615721526525 | `vpnd/tests/test_cli.py`: `test_baseline_global_flag_scope_and_duplicate_matrix` rejects misplaced/duplicate flags and preserves explicit globals; `test_man_page.py` checks every visible flag; `scripts/check-vpnd-package.py` compares all 20 installed help scopes and parser refusals. | passed |
| REQ-PYCLI-PIPELINES | VPD-1791615723154686 | `vpnd/tests/test_deploy_lifecycle.py`: `test_pipeline_matches_makefile_order_before_unconditional_cleanup` asserts the exact transcript; reconverge/probe cases assert exact inventory host keys. `test_runner.py` asserts Terraform wrapper argv and Make scope; `test_core_mutation_coverage.py` refuses ambiguous service addresses. | passed |
| REQ-PYCLI-STATE | VPD-1791615722328162 | `vpnd/tests/test_registry.py::test_production_registry_io_roundtrip_and_fail_closed_errors` checks sorted TOML round-trip, concurrent atomic saves, 0600 and no stale temps; `test_host_crud.py` checks add/show/overwrite/remove JSON; `test_config.py` checks root/runtime resolution; `test_update_cache.py` checks TTL, future/corrupt cache and strictly newer releases. | passed |
| REQ-PYCLI-ARTIFACTS | VPD-1791615723996375 | `vpnd/tests/test_share_command.py` asserts exact config, subscription port, both QR files and permissions; `test_recipient_render.py` checks all sections and hostile-input escaping; `test_qr_encode.py` checks XML, dimensions, white canvas/crisp edges. Doctor tests check all six tar members and both streams; `test_ai_docs_emit.py` checks sorted index, concatenation and byte-preserved per-doc copies. Apple Vision decoded the exact synthetic subscription URL. | passed |
| REQ-PYSAFE-EXPLAIN | VPD-1791615723154686 | `vpnd/tests/test_host_crud.py::test_host_explain_never_changes_registry` compares registry bytes; `test_deploy_lifecycle.py::test_reconverge_explain_does_not_execute_or_harden_an_existing_file` checks no spawn/chmod; `test_core_mutation_coverage.py` keeps inventory visibly unresolved; doctor, ai-docs and update explain tests assert no command/export/cache and work outside a checkout where applicable. | passed |
| REQ-PYSAFE-PROCESSES | VPD-1791615722328162 | `vpnd/tests/test_runner.py` checks real dual-stream/rc behavior, owned descendant cancellation, unreaped leader reservation and 40 simultaneous captures. `test_probe_matrix_lifecycle.py::test_direct_and_foreground_signals_reclaim_probe_jobs_and_doctor_captures` has one 3-second exit/reaping deadline. `test_core_mutation_coverage.py` checks the shared spawn lock, real setup-error cleanup, closed-pipe live-leader cancellation, foreground-only kill and exact fatal exception handoff. | passed |
| REQ-PYSAFE-CLEANUP | VPD-1791615723154686 | `vpnd/tests/test_deploy_lifecycle.py`: `test_cleanup_runs_after_failure_and_original_error_wins`, `test_successful_pipeline_requires_successful_cleanup`, `test_reconverge_dry_run_cleans_plaintext_and_uses_scoped_inventory_name` and `test_deploy_and_reconverge_preserve_primary_failures_and_still_clean` assert cleanup once and primary-error precedence. | passed |
| REQ-PYSAFE-TRANSFER | VPD-1791615722328162 | `vpnd/tests/test_runner.py` validates per-key Make values and refuses before spawn; `test_secrets.py` exercises actual FIFO/symlink/race, mode and held-handle reads; `test_protected_file.py` rejects foreign ownership. `test_deploy_lifecycle.py` checks every decrypting caller stops on absent/unsafe plaintext and actual fd-chmod failure. The nine preserved obligations below identify their exact assertions. | passed |
| REQ-PYMATRIX-SCHEMA | VPD-1791615725580652 | `vpnd/tests/test_probe_matrix_snapshot.py::test_probe_matrix_report_snapshot` retains the baseline schema-3 snapshot bytes. `test_probe_matrix_inline.py` checks required paired targets, credential-only fingerprint exclusions, transport matching, windows and classifications; unknown evidence suppresses positive conclusions. | passed |
| REQ-PYMATRIX-SCHEDULE | VPD-1791615725580652 | `vpnd/tests/test_probe_matrix_inline.py::test_concurrent_collection_is_ordered_and_isolates_timeout` checks ordered concurrent results and isolated timeout; `test_fixed_rate_schedule_does_not_accumulate_sweep_time` checks monotonic fixed cadence. Lifecycle cases assert hanging controls continue real cells and oversized next polls stop safely; runner cases check immediate worker launch and late-cancellation spawn refusal. | passed |
| REQ-PYMATRIX-DURABILITY | VPD-1791615725580652 | `vpnd/tests/test_probe_matrix_lifecycle.py` checks real SIGINT/SIGTERM exit 130/143, private JSON/JSONL/lock modes, partial cell evidence, no synthetic cells during scheduled waits, durable last-good checkpoint after a failed write, exclusive output locks and descendant termination. | passed |
| REQ-PYDELIVERY-INSTALL | VPD-1791615726382311 | `vpnd/tests/test_delivery_installer.py` checks Python/root/platform/hash/archive/dependency/resource preflight before prefix mutation, real offline install outside the checkout, all 20 manuals and failure recovery. `scripts/check-vpnd-package.py` exercises installed CLI/parser/resources and corrupt upgrade. Exact-b88 package jobs succeeded on Linux/macOS x86_64/arm64 with Cargo/rustc refusal sentinels. | passed |
| REQ-PYDELIVERY-TESTS | VPD-1791615727227192 | `vpnd/test-inventory.md` preserves all 206 baseline identities; `vpnd/test-transfer.json` maps real annotated nodes. `scripts/check-vpnd-test-transfer.py` rejects stale source fingerprints, skipped/missing/failed phases and mapping drift. All 297 source cases and 206 functions passed before retirement. Six Hypothesis properties retain 256 examples and original seeds; original snapshots remain. `tests/unit/test_vpnd_test_transfer.py` verifies exact identities without OpenSpec. | passed |
| REQ-PYDELIVERY-INTEGRITY | VPD-1791615726382311 | `tests/unit/test_release_chain.py` and `test_vpnd_release_tags.py` assert version markers, validated tags and rerun-safe asset publication; `test_vpnd_dependency_contract.py` checks exact pins/hashes, fixed dispatch and no ignored vulnerabilities. `test_vpnd_sbom.py` validates native wheel dependency edges and rejects bad closure. Package checks compare wheel/sdist/platform bundle bytes and validate actual offline pip closure; provenance/SHA256SUMS remain in the release workflow. | passed |
| REQ-PYDELIVERY-RETIRE | VPD-1791615728004540 | At b88a41ad, exactly 57 Rust sources/tests and four Cargo files were removed after pre-retirement acceptance. `mise.toml`, hooks/CI/release/Make, Renovate and setup docs use Python; ignored legacy outputs, snapshots, seeds and historical inventory remain. The 70-case retirement target and independent 71-file delta security review passed. Exact-source full Rust-free `make check` and required CI aggregation passed. | passed |
| REQ-PYDELIVERY-ROLLBACK | VPD-1791615726382311 | `vpnd/tests/test_delivery_installer.py`: post-rename KeyboardInterrupt and real SIGTERM restore the previous native file or symlink and every manual; interrupted manual publication, failed offline pip/pip-check, stale assets and corrupt bundles refuse promotion. `test_host_crud.py` preserves operator registry formats; installation documents the native-binary-to-Python prerequisite break without state migration. | passed |
| REQ-MANPAGE-SYNC | VPD-1791615724808852 | `vpnd/tests/test_man_page.py` checks every command/visible flag and original value/default meanings against the live parser; `test_completions_snapshot.py` covers bash/zsh/fish snapshots, security flag descriptions, powershell/pwsh and invalid shell refusal. Installer tests require all 20 parser-derived packaged manuals and fixed argv for every completion backend. | passed |
| REQ-SHARE-BUNDLE-PERMS | VPD-1791615723996375 | `vpnd/tests/test_share_command.py` asserts 0700 output directory and all four files 0600 under permissive umask, preserved unrelated stale temps and QR publication-failure cleanup. `test_protected_file.py` exercises parallel private atomic writes without collisions; the writer uses held private files, fsync and atomic replace. | passed |

## Preserved main-spec regression obligations

These nine unchanged requirements remain covered by REQ-PYSAFE-TRANSFER and the
command/artifact obligations; no new normative identifier is introduced.

| Existing requirement | Execution step | Observed assertion mapping | Result |
|---|---|---|---|
| `REQ-MAKE-KV-CHARSET` | VPD-1791615722328162 | `vpnd/tests/test_runner.py` positive/rejection tables and first-failure no-spawn assertion; `test_core_mutation_coverage.py` rejects every C0/C1 control without exposing the value and accepts uppercase identifiers. Corresponding critical allowlist mutants are killed. | passed |
| `REQ-SECRETS-PATH-AUTHORITY` | VPD-1791615722328162 | `vpnd/tests/test_runner.py::test_target_carries_resolved_secrets_file_after_provider` checks explicit SECRETS_FILE; `test_deploy_lifecycle.py::test_share_without_xdg_decrypts_once_through_the_canonical_script` verifies one canonical decrypt and the same resolved path across consumers. | passed |
| `REQ-SECRETS-REDACTION-COVERAGE` | VPD-1791615724808852 | `vpnd/tests/test_proptest_redact.py` covers resolved/historical paths and preserved non-secret lines with 256 examples, original seeds and explicit Unicode separators; doctor in-process tests assert redaction in AI excerpts, every tar member and actual clipboard bytes; runner tests mask display without changing argv. | passed |
| `REQ-SECRETS-HARDEN-GATE` | VPD-1791615722328162 | `vpnd/tests/test_secrets.py` checks actual read-only/private handles, loose modes, missing files, FIFO nonblocking refusal and concurrently swapped symlinks; `test_protected_file.py` rejects foreign UID. Every decrypting caller and real fd-chmod failure is exercised in `test_deploy_lifecycle.py`. | passed |
| `REQ-SHARE-TOKEN-VALIDITY` | VPD-1791615723996375 | `vpnd/tests/test_share_command.py::test_invalid_tokens_from_stdin_and_file_fail_before_emission` asserts both sources, invalid/empty/non-ASCII values and no emitter/output; token-file cases reject symlinks/loose modes and accept private input; separator cases retain exact Unicode White_Space framing. | passed |
| `REQ-SHARE-HOST-RESOLUTION` | VPD-1791615723996375 | `vpnd/tests/test_share_command.py::test_missing_or_blank_host_fails_before_creating_a_bundle` refuses before output; its canonical-client success case asserts configured subscription port and exact URL. `test_share_bundle.py` checks encoded deep links and exact parsed rendered hostname. | passed |
| `REQ-JSON-FLAG-HONESTY` | VPD-1791615721526525 | `vpnd/tests/test_cli.py::test_json_flag_is_rejected_for_unsupported_subcommands` and the baseline scope/duplicate matrix reject unsupported/global/duplicate JSON; `test_host_crud.py::test_json_flag_emits_machine_readable_list_and_show` checks actual structured output. | passed |
| `REQ-CLIP-REQUIRES-AI` | VPD-1791615721526525 | `vpnd/tests/test_cli.py` asserts --clip without --ai is a parse-time error and the valid pair carries both flags. `test_doctor_mutation_coverage.py` exercises all four controlled clipboard executables, exact UTF-8/argv, failures and stdout fallback. | passed |
| `REQ-DOCTOR-RESILIENCE` | VPD-1791615724808852 | `vpnd/tests/test_doctor_resilience.py::test_all_steps_run_and_report_after_a_mid_run_failure` checks all six ordered steps, retained stdout/stderr and nonzero status; bundle cases keep failed evidence. In-process cases exercise missing/failing tools, AI exports and actual clipboard fallback without operator PATH. | passed |

## Historical planning evidence


The plan was authored against baseline
`5365cbd4b33dff5b3d0be0e1f8c5cb2c9d17ac50`. Static discovery enumerated 206 Rust
test functions and ten direct Python consumer suites. At that planning stage, no Rust/Python application
tests, builds, provider operations or installations had been performed for migration
acceptance. Planning validation results are recorded after the artifact set is
complete; they cannot change the required implementation evidence states above.

Historical planning observations on 2026-10-10:

- `./taskctl openspec cli validate replace-vpnd-with-python --strict --json`:
  valid, zero issues.
- `./taskctl generate-board` and `./taskctl validate`: 17 tasks and 55 steps
  valid, migration progress 0/9.
- `env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make task-check`:
  passed with the same 17-task/55-step contract result.
- OpenSpec status reports proposal, specs, design, tasks and verification
  present and planning complete. Implementation acceptance was still required at planning time.
