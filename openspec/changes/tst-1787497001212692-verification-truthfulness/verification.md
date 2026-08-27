---
task_id: TST-1787497001212692
change: tst-1787497001212692-verification-truthfulness
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: "Pre-merge implementation candidate 5581b6fa31efa01fc11d3c136ba32f558bf8f4af passed CI run 33080350367, all 53 jobs including both full-stack variants, baseline on both distributions, AWG, exposure and firewall. The specification still requires final merge-SHA evidence after the external acceptance blockers are satisfied."
dry_run: not_applicable
dry_run_evidence: no Terraform surface changed; playbook gating verified via live-inventory runs
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule covers scenario changes
live: blocked
live_evidence: "Hosted native Linux scenarios passed in run 33080350367. The live verify/source-drift cycle remains pending: all three matching server peers are offline. Native fixtures are not live fleet proof."
client: not_applicable
client_evidence: no client emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-VERIFY-HOSTCLASS-GATING | TST-1787496118906453 | verify + smoke against subscription-only profile inventory | pending |
| REQ-DRIFT-FULL-IDENTITY | TST-1787496118906639 | negative source-drift run with mismatched revision fixture | pending |
| REQ-VERIFY-DEPLOYED-LISTENERS | TST-1787496118906882 | verify run with custom hysteria_port + enabled fallbacks | pending |
| REQ-IDEMPOTENCE-WHERE-DECLARED | TST-1787496118906321 | full-stack idempotence phase output showing second-run changed=0 | pending |
| REQ-SCENARIO-RUNS-ROLE | TST-1787496118906595 | rewritten amneziawg converge executing role tasks | pending |
| REQ-TESTING-DOCS-REALITY | TST-1787496118906567 | row-by-row matrix audit vs molecule.yml sequences | pending |
| REQ-SINGLE-SSH-LISTENER | TST-1787496118907256 | verify assertion output on socket-activated image | pending |

## Gates

- Local: touched molecule scenarios, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA including both full-stack variants.
- Live: one verify + source-drift cycle against live inventory.

## Observed implementation checks (2026-08-27)

`make check` exited 0: 1107 unit tests passed with one skipped test,
55 Bats checks, 83 Terraform mock tests, 45 Conftest tests, 102 snapshots,
strict Ansible lint, Rust MSRV and dependency checks, and 172 release tests.
The subsequent QR legacy-output regression slice passed 28 tests; full-stack
fixture guards passed for both inventories and the 14-test verification slice
passed with inherited privilege escalation enabled. Native Linux Molecule subsequently passed in run 33080350367 on exact
5581b6fa31efa01fc11d3c136ba32f558bf8f4af (all 53 jobs). Real staging/live
acceptance and final merge-SHA verification remain separate requirements.
