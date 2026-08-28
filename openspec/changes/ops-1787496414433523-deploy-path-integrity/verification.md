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
| REQ-TAGGED-GUARDS | OPS-1787496118906514 | `test_tagged_convergence_executes_source_preflight_guards`: real Ansible executes the unchanged source pre-tasks with `--tags p0`; missing secrets, empty SSH allowlist and unapproved research/exception roles stop before the sentinel, while valid and approved-research inputs proceed | local PASS; remote and live gates pending |
| REQ-BOOTSTRAP-GATED-DEPLOY | OPS-1787496118906556 | make -n deploy showing readiness prerequisite before playbook | pending |
| REQ-BOUNDED-WAIT | OPS-1787496118906208 | wait script bound test with unreachable marker fixture | pending |
| REQ-COHORT-SLUG-VALIDATION | OPS-1787496118906369 | `test_unknown_cohort_fails_before_terraform_and_preserves_inventory`: unknown profile, traversal-shaped slug, and malformed group name all fail before Terraform and preserve the last inventory | local PASS; remote and live gates pending |
| REQ-SSH-ALLOWLIST-FAILFAST | OPS-1787496118906156 | terraform plan with empty allowlist failing validation block | pending |
| REQ-UNIQUE-HOST-ALIASES | OPS-1787496118906901 | `test_duplicate_host_alias_preserves_last_inventory`: both conflicting provider/environment pairs are diagnosed and the last inventory survives | local PASS; remote and live gates pending |
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
- Combined inventory and tagged-guard source passed the full serialized `build-gate -- mise exec -- make -j1 check`: 1446 Python tests passed with one existing real-network placeholder skipped, 55 Bats tests passed, and Terraform/policy, real sing-box/Xray parser, release Rust tests and clippy gates passed. This is local validation; exact-commit hosted checks and protected integration remain pending.
- Tests preserve the source pre-tasks and real role-tier manifest, but replace host-mutating roles with a local debug sentinel. They do not execute `site.yml` against any host or prove fleet convergence. Combined local and remote gates are recorded separately; the overall task remains open.
