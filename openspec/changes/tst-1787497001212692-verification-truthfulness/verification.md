---
task_id: TST-1787497001212692
change: tst-1787497001212692-verification-truthfulness
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: no Terraform surface changed; playbook gating verified via live-inventory runs
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule covers scenario changes
live: required
live_evidence: null
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
