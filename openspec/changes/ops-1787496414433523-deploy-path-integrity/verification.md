---
task_id: OPS-1787496414433523
change: ops-1787496414433523-deploy-path-integrity
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule plus a live-inventory dry-run cover gate behavior
live: required
live_evidence: null
client: not_applicable
client_evidence: no client-facing emitter or vpnd surface changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TAGGED-GUARDS | OPS-1787496118906514 | `test_tagged_convergence_executes_source_preflight_guards`: real Ansible executes the unchanged source pre-tasks with `--tags p0`; missing secrets, empty SSH allowlist and unapproved research/exception roles stop before the sentinel, while valid and approved-research inputs proceed | local and exact-main hosted PASS; live gate pending |
| REQ-BOOTSTRAP-GATED-DEPLOY | OPS-1787496118906556 | make -n deploy showing readiness prerequisite before playbook | pending |
| REQ-BOUNDED-WAIT | OPS-1787496118906208 | Real wait-script regressions cover cloud-init 0/1/2, missing marker, remote deadline retries, connected SSH deadline, and interruption cleanup | local PASS; full, remote and live gates pending |
| REQ-COHORT-SLUG-VALIDATION | OPS-1787496118906369 | `test_unknown_cohort_fails_before_terraform_and_preserves_inventory`: unknown profile, traversal-shaped slug, and malformed group name all fail before Terraform and preserve the last inventory | local and exact-main hosted PASS; live gate pending |
| REQ-SSH-ALLOWLIST-FAILFAST | OPS-1787496118906156 | terraform plan with empty allowlist failing validation block | pending |
| REQ-UNIQUE-HOST-ALIASES | OPS-1787496118906901 | `test_duplicate_host_alias_preserves_last_inventory`: both conflicting provider/environment pairs are diagnosed and the last inventory survives | local and exact-main hosted PASS; live gate pending |
| REQ-ROTATION-PREV-CONTRACT | OPS-1787496118906340 | rotation run leaving .prev byte-identical to pre-rotation config | pending |
| REQ-ROLLBACK-VALIDATE-FIRST | OPS-1787496118906432 | rollback rehearsal with incompatible target failing before symlink flip | pending |
| REQ-SMOKE-CLEANUP | OPS-1787496118906646 | smoke-test failure-path run leaving no transient units/workdir | pending |
| REQ-MAINTENANCE-SERVICE-GATE | OPS-1787496118906956 | os-maintenance check-mode run on host without the external unit | pending |
| REQ-TOGGLE-DEFAULT-PARITY | OPS-1787496118906821 | pytest parity sweep over playbooks vs all.yml | pending |
| REQ-LOCALE-INDEPENDENT-GATE | OPS-1787496118906614 | simulation under non-English LC_ALL passing the gate | pending |
| REQ-DECLARED-TOGGLE-SURFACE | OPS-1787496118906731 | grep of consumed enable_* keys vs all.yml defaults in pytest | pending |

## Gates

- Local: pytest named cases, shellcheck on touched scripts, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: `make dry-run` against live inventory including the new gates.
- Live: one deploy-path cycle exercising wait gate, rotation .prev, and rollback rehearsal order.

## Narrow inventory slice — 2026-08-28

- Base: `8d62d98aa7980b4fd5470e39ab65258b1c4cfe38`; worktree branch: `codex/high-inventory-guards-20260828`.
- Step `OPS-1787496118906369`: “Validate each COHORTS slug against the known group_vars/vpn-*.yml set during inventory rendering, failing loudly on unknown values.”
- Step `OPS-1787496118906901`: “Abort inventory rendering on duplicate host aliases across HOSTS pairs (or namespace aliases while keeping server_hostname as a host var).”
- Before implementation, all four added regression cases failed because the real renderer returned success. After the 15-line guard change, `mise exec -- python3 -m pytest tests/unit/test_render_inventory.py -q` passed all seven tests; `shellcheck scripts/render-inventory.sh` and `git diff --check` passed. A separate isolated real-renderer check accepted the known `p0` profile.
- Full `build-gate -- make check` passed with the pinned mise toolchain, a separate Cargo target, and two Cargo jobs; this includes `make validate`, 79 Terraform mock tests, 45 policy tests, all render/schema/snapshot checks, and release Rust tests/clippy. Python reported 1440 passed and one existing skipped real-network RealiTLScanner placeholder. The first attempt stopped at a missing sing-box PATH entry; the successful rerun used the retained official 1.13.16 archive after matching its GitHub asset SHA256 and verifying the extracted binary bytes. The canonical real sing-box/Xray parser gate passed.
- The new regressions use the existing Terraform output fixture in temporary repository directories; Terraform is stubbed and SSH is rejected. This proves local rendering behavior, not provider, staging, or live deployment behavior. These renderer regressions do not establish any other execution step or overall evidence category.

## Tagged safety guards — 2026-08-28

- Step `OPS-1787496118906514` adds `always` to the five existing secrets, SSH allowlist, tier-loader and tier-approval pre-tasks. Role defaults, runtime configuration and SSH migration are unchanged.
- Before the fix, real Ansible skipped all five source guards under `--tags p0`: four invalid-input regressions failed and both valid-input cases passed. After the fix, the entire listener-contract module passed 18 tests. Independent read-only review reran the same 18 tests and found no actionable issues; `make validate` passed.
- Combined inventory and tagged-guard source passed the full serialized `build-gate -- mise exec -- make -j1 check`: 1446 Python tests passed with one existing real-network placeholder skipped, 55 Bats tests passed, and Terraform/policy, real sing-box/Xray parser, release Rust tests and clippy gates passed. The inventory and tagged-guard source was subsequently integrated through protected PR #113: main `7da8b74f15530f5823a96527dd35954b538ab490` is byte-identical to the tested tree, and exact-main CI run `33170551316` passed all 51 jobs; CodeQL run `33170551119` and scorecard passed. Local main, origin/main, and the remote branch SHA matched. This does not establish live convergence.
- Tests preserve the source pre-tasks and real role-tier manifest, but replace host-mutating roles with a local debug sentinel. They do not execute `site.yml` against any host or prove fleet convergence. Combined local and remote gates are recorded separately; the overall task remains open.

## Bounded wait slice — 2026-08-28

- Base: `7da8b74f15530f5823a96527dd35954b538ab490`; branch: `codex/high-bootstrap-wait-20260828`. Only step `OPS-1787496118906208` is implemented here; deploy/dry-run readiness integration and SSH transport migration remain separate.
- The wait retains Terraform output routing, SSH key/port, and existing host-key policy. Each local SSH session has a deadline and owns a separate process group. The cloud-init phase permits 30 attempts with a 10-second session budget; each remote status wait uses GNU timeout with a five-second deadline and one-second kill grace. Local session timeout, remote deadline exhaustion, fatal/recoverable cloud-init errors, missing marker, and unavailable status/transport are categorical, without raw cloud-init output.
- Cloud-init distinguishes success (0), unrecoverable failure (1), and recoverable errors (2). Both nonzero outcomes refuse readiness. GNU timeout's installed help documents 124/137 and kill-after; those remote outcomes retry, while a local SSH deadline fails promptly.
- Tests first: three initial cases failed because error outcomes with an existing marker were accepted and raw output escaped; all three passed after classification/redaction. Three deadline cases then failed (remote deadlines misclassified; a real connected SSH child exceeded the test watchdog), and all six combined cases passed after bounded waiting. A deterministic SIGTERM injection immediately after real `Popen` returned reproduced an escaped child; flag-only cancellation plus cleanup under `finally` passed this case and both ordinary SIGTERM/SIGINT cases.
- `mise exec -- python3 -m pytest -q tests/unit/test_render_inventory.py`: 20 passed, including 13 new wait cases. A first full-module run had a test-setup watchdog expire before any SSH fixture started; setup now synchronizes on its atomically published PID record within the readiness budget, retaining the three-second post-signal cleanup assertion. `mise exec -- shellcheck scripts/wait-cloud-init.sh` and `git diff --check` passed without suppressions.
- Independent whole-module rerun: 20 passed. `make validate` passed, including Terraform validation, gitleaks, Ansible lint and syntax. The full `make check` was attempted three times: the first two stopped at Terraform Registry request timeouts; the third passed Terraform/policy/parsers and reported 1458 Python tests passed, one failed and one existing skipped placeholder. All 20 wait/renderer cases passed in that run; Rust and Bats were not reached.
- The failed existing `test_awg_namespace_is_removed_after_probe_failure` expected `blocked` but received `error`. Its source and runtime were unchanged from base. Eight fresh isolated reproductions on base all returned `blocked` with the `network` category; the intermittent failure's original category was not captured, so its cause is not established. Separate diagnostic-only commit `6c6caa3ef21f5d826f509e7e5c0a484e0b6702a1` adds the categorical result to that assertion without changing acceptance, timeouts or runtime behavior. A successful full local gate and exact-source hosted checks remain required before integration.
- Original source commit `71186606f018b079c38ae6a8321eaee0bdf278c9` passed hosted CI `33175393913` (51 jobs), CodeQL `33175393693`, and the remaining PR checks (63 success, one neutral). PR #114 remains draft. The branch then merged main `2009b6f694e326fa1f6d99333da497544b115cdd`, preserving both changes and verifying 1591 collected tests. The combined-tree full run reported 1534 passed, three failed, one existing skip: all three failures were the explicit real-restic prerequisite assertion because that invocation omitted the installed test-tool directory from PATH. The same unchanged three cases passed with the verified restic 0.16.4 tool directory restored (13.31 seconds). A complete rerun with all prerequisites remains required; no acceptance check was weakened.
- The tests execute the unchanged production script/remote shell and real GNU timeout, substituting only Terraform outputs, SSH transport, and the marker path. The spawn-window test additionally injects signal timing around real `Popen` in a temporary Python runtime shim; it is local fault-injection evidence, not provider or live proof. No host commands, Make gate changes or live acceptance were performed by this slice.
