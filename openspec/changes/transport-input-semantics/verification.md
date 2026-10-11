---
task_id: SCT-1791617687019287
change: transport-input-semantics
commit_sha: "cf01f94a640913412f3316b5cb288881639712ce"
local: "passed"
local_evidence: "Complete local gate components passed across native macOS and Linux arm64 on unchanged runtime source cf01f94a640913412f3316b5cb288881639712ce. Mac validation and every ci-fast stage before test-unit passed; all four complete disjoint Linux ordinary-user portable groups passed (6340 tests passed across all four complete disjoint portable CI groups; group 1: 1585 passed, 4890 deselected, 5 warnings, 7 subtests passed in 255.95s (0:04:15); group 2: 1584 passed, 4891 deselected, 6 warnings, 9 subtests passed in 232.44s (0:03:52); group 3: 1585 passed, 4890 deselected, 5 warnings in 232.07s (0:03:52); group 4: 1586 passed, 4889 deselected, 2 warnings, 6 subtests passed in 256.55s (0:04:16)), all CLI tests passed (297 passed in 26.87s), lint and baseline transfer passed, and all 57 shell tests passed. No single make check invocation is claimed successful; earlier failures are retained below."
remote_ci: "passed"
remote_ci_evidence: "Protected-main CI run 38134843683 completed successfully on exact integrated source cf01f94a640913412f3316b5cb288881639712ce; all jobs succeeded, including portable, native, role, failure and full-stack checks. Scorecard, CodeQL and release-please completed successfully on the same source."
dry_run: not_applicable
dry_run_evidence: source-only capability; no controller or provider execution in this task
staging: not_applicable
staging_evidence: isolated native source acceptance owns this change; fleet rehearsal requires separate authorization
live: not_applicable
live_evidence: no production rollout is part of this source task
client: "passed"
client_evidence: "Complete supported real-client native cases passed in protected-main run 38134843683 at exact source cf01f94a640913412f3316b5cb288881639712ce; source-specific observations are retained below. These are isolated parser/runtime/client proofs, not fleet acceptance."
artifact: "passed"
artifact_evidence: "Exact integrated source cf01f94a640913412f3316b5cb288881639712ce passed all 86 hosted jobs; 163 rendered templates and golden snapshots matched locally. Complete scoped native artifacts and reviewed private-output/contract proofs are retained below; no new production artifact or fleet rollout is claimed."
---

# Verification

## Requirement evidence

Source observations below were obtained in the dedicated implementation worktree based on `8828ffebdbe42ad17d5f98433db78db1a0aa95eb` and committed at `6202c7ec93c075b6b5fd3b40065204e4f59d9461`. The integrated source revision `f8055ff0c4624a0a4e504e0fd2bc3823718f455b` subsequently passed all main CI jobs and its complete native lane. The five reviewed CodeQL alerts were individually dismissed with user authorization and verified audit comments; re-evaluation passed on the same source SHA; this record does not claim deployment or fleet acceptance.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-INPUT-COHORT | SCT-1791617711124536 | Complete affected portable suite: 383 passed, zero skips; missing/empty/unknown/duplicate cohort and actual controller early-refusal cases. Exact Xray 26.3.27 accepted the rendered candidate in the complete native suite. | passed |
| REQ-PROTO-INPUT-AWG | SCT-1791617712074772 | Complete portable consumer/semantic cases plus real AWG TUN/setconf host and explicit routed-prefix acceptance using source-pinned Go v0.2.12 and tools v1.0.20241018. Existing legacy consumers validate their consumed view; instance-selection changes remain separately tracked. | passed |
| REQ-PROTO-INPUT-HYSTERIA | SCT-1791617711124536 | Complete lifecycle/schema negative and privacy cases; exact Hysteria v2.9.0 accepted the installed validator and started the owned HTTPS proxy candidate. | passed |
| REQ-PROTO-INPUT-PRIVACY | SCT-1791617713075181 | Complete floor/schema/marker cases passed in the 383-test portable suite; coverage resolves 119 variables across 236 references; all 152 snapshots match. Complete affected Molecule scenarios passed; final full source gate passed with 5907 portable tests and 22 subtests. | passed |

## Observed validation

- Complete 13-file affected portable suite: 383 passed with `--fail-on-skip`; pinned Python 3.12 and genuine SOPS/age binaries were used.
- Complete `test_transport_semantics_native.py`: 3 passed with `--fail-on-skip` on owned Debian 13 Linux amd64 / Python 3.13.5, with checksum-verified Xray/Hysteria and exact source-pinned AWG builds. This proves parser/startup and real AWG control-client behavior, not fleet protocol traffic.
- `scripts/check-secrets-coverage.py`: passed (119 variables, 236 references).
- `scripts/render-snapshots.py`: passed (152 templates); no snapshot refresh needed.
- Independent security/spec review: APPROVE after correction of duplicate names, consumed AWG view and native fixture prerequisites.
- Strict OpenSpec validation, shellcheck and `git diff --check`: passed.
- Complete Molecule scenarios: Xray, Hysteria and AmneziaWG passed convergence, idempotence, verification and destruction. Hysteria also passed predictive check mode, malformed-candidate refusal and fixture upgrade. Existing optional missing-prepare warnings were observed; no cases were focused or disabled.
- Final `make check` through `build-gate` and pinned `mise`: passed. Complete portable suite: 5907 passed, 126 native cases deselected into their separate lane, 22 subtests passed, zero skips; Terraform validation/mock tests/policies, shell tests, workflow checks, secrets/schema/render checks, clippy, MSRV and complete Rust CLI tests passed.
- The complete exact native three-test file was rerun against the final duplicate-name guard: 3 passed, zero skips.
- Independent review approved globally unique client-name admission and its real normal/check-mode refusal regression; the complete semantics/schema suite passed 175 tests.
- An earlier complete run reported one blocked result in the unchanged REALITY monitor target-change case. Complete module reruns and 12 bounded diagnostic sequences passed; the final full run passed. No cause was confirmed. Its unchanged assertion now includes the existing redacted report on failure, and the final runner retained isolated diagnostic state. No retries, timeout changes, scanner changes or assertion weakening were introduced.
- Isolated inventory/topology/controller/bootstrap/SOPS repair coverage: 273 passed; ownership/native-CI/semantic fixture coverage: 166 passed; complete emitter coverage: 33 passed. Genuine jq avoided inactive-shim startup latency without changing the 20-second test timeout.
- Staged gitleaks after those test corrections: passed, no leaks found.
- Ruff through the workstation shim was unavailable; no Ruff result is claimed.

## Integrated producer follow-up

CI credential generation now emits the served nginx HTTPS origin for Hysteria rather than reusing the watchdog endpoint path. The disposable profile derives the same canonical origin from its generated hostname; the watchdog retains its separate exact canary endpoint. The genuine-crypto native regression checks schema admission and the producer/profile equality. All 134 native cases and all 6,205 portable cases plus 22 subtests passed on integrated source `f8055ff0c4624a0a4e504e0fd2bc3823718f455b` in main CI run `38107544582`, with zero selected skips. Both full-stack scenarios passed after their required credential preparation was present. The authorized CodeQL alert dispositions are complete; re-evaluation passed on the same source SHA, and the final refreshed local gate also passed; no live or vendor acceptance is inferred.

## Final local gate

The complete refreshed `build-gate -- make check` passed against the final runtime source and current task artifacts. Portable tests: 6,205 passed, 134 native cases assigned to their separately passed lane, 22 subtests passed, zero selected skips, 2,003.41 seconds. Python CLI: all 297 passed in 53.92 seconds; all 206 baseline transfer functions mapped to passing cases. All remaining task, schema, template, snapshot, dependency, secret, Terraform, Ansible, workflow, shell and package gates passed. The changes remain in review; no archive, deployment, registered vendor action or PR merge was performed.

## Closure reconciliation (2026-10-11)

The preceding sections retain their historical source and environment boundaries. The earlier verification SHA was `6202c7ec93c075b6b5fd3b40065204e4f59d9461`. The accepted integrated source for this closure is `cf01f94a640913412f3316b5cb288881639712ce`; protected-main CI run `38134843683` completed with every job successful. This supersedes earlier pending PR/hosted-check observations without claiming a new deployment. Runtime and source files are unchanged by the closure increment.

## Final closure acceptance (2026-10-12)

The closure snapshot `e6ac235439bc66f9bb2bf9d9c71a4dded780ac38` has byte-identical production runtime files to integrated source `cf01f94a640913412f3316b5cb288881639712ce`. Validation was assembled from the complete passed Mac `validate` and `ci-fast` pre-test stages, then the complete ordinary-user Linux `make test-unit-shard PYTEST_GROUP=1..4`, `make vpnd-lint vpnd-test vpnd-parity-check` and `bats tests/bats/` stages. Portable result: 6340 tests passed across all four complete disjoint portable CI groups; group 1: 1585 passed, 4890 deselected, 5 warnings, 7 subtests passed in 255.95s (0:04:15); group 2: 1584 passed, 4891 deselected, 6 warnings, 9 subtests passed in 232.44s (0:03:52); group 3: 1585 passed, 4890 deselected, 5 warnings in 232.07s (0:03:52); group 4: 1586 passed, 4889 deselected, 2 warnings, 6 subtests passed in 256.55s (0:04:16). CLI result: 297 passed in 26.87s. All 57 shell tests passed; all 206 baseline transfer functions mapped to passing cases. No selected tests were skipped and no assertions, deadlines, locks or production source were changed.

Earlier attempts retain their failed diagnostic status: tool activation, root-only runner admission, absent parser/cache prerequisites, existing Mac fixture deadlines, and the intermittent monolithic SSH recovery unit failure did not count as acceptance. Read-only tracing diagnosed the original failure. The acceptance snapshot isolates the adapter test clock interface from the shared standard-library time module; production behavior, assertions and deadlines are unchanged. The complete 118-test SSH module subsequently passed without tracing. The tracer observed Python subprocess polling consuming the shared test fake clock and making its fixed synthetic worker timestamps stale; production freshness checks remained intact. All four canonical CI groups subsequently passed without the diagnostic tracer and with unchanged production source and assertions. The Linux arm64 standalone `make check` stopped at a Scaleway cached-provider checksum mismatch; the repository lockfile was preserved and the already-passed native Mac Terraform validation supplied that component. This record claims passed components across both environments, not one successful standalone `make check`. Protected-main CI run `38134843683` passed all 86 jobs on `cf01f94a640913412f3316b5cb288881639712ce`, including the complete native, role, failure and full-stack lanes.
