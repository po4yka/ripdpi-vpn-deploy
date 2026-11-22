---
task_id: OPS-1795327950629406
change: ops-1795327950629406-private-ops-repository-w1
commit_sha: aa46b09758aa2b4e550b6d7b34aad67db06d6c56
local: passed
local_evidence: "make -k check -j 4: tofu test, bats 92, vpnd 551, unit 12765 passed with one load-sensitive failure that passes alone; validate failed on staged gitleaks for literal key markers, fixed, then make validate passed. New tests: test_validate_ops_repo.py (20), test_deploy_controller.py two-checkout dry-run (fails on the previous controller), test_render_inventory.py external tfvars and output, test_terraform_env.py plan var-file. After independent review: validator tightened (content-based plaintext detection, sops.json, any .dec, encrypted-value check, symlinks, PGP/WireGuard keys, malformed policy, Git-committable scope), relative TFVARS_ROOT refused in Make; test_validate_ops_repo.py and test_terraform_env.py 42 passed; validator passes all 34 real kit SOPS documents in a scratch copy; gitleaks staged clean."
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy pull request 683 merged as aa46b097: 79 checks success, 3 planned skips, 1 neutral."
dry_run: not_applicable
dry_run_evidence: "Operator decision 2026-11-22: the imported inventory and tfvars are byte-identical to the kit and the two-checkout tests prove the controller selects hosts from the ops path; the rendered-inventory and dry-run comparison runs at the W7 cut-over drill."
staging: not_applicable
staging_evidence: "Operator decision 2026-11-22: no staging run; W1 changes input paths only and production inputs are byte-identical to the kit."
live: passed
live_evidence: "2026-11-22: private repository po4yka/ripdpi-vpn-ops created; ruleset operator-merge-gate active on main (deletion, non_fast_forward, update, pull_request; admin bypass by pull request only); operator direct push refused with GH013; operator merges landed ops pull requests 2 and 3 (7c8abe9f). Imported byte-equal copies of the current inventory, four production tfvars, three node SOPS documents with their recipient policy, host pins, the catalog with authority on every credential and the OpenTofu receipt; validate-ops-repo.py and gitleaks (default and public rules) clean; make -n with the template fleet.mk resolves plan, inventory, known-hosts and SOPS inputs to the ops checkout. Workflow-token refusal deferred to W4 because private-repository Actions are blocked by account billing."
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPSREPO-PIN | OPS-1795328289814121 | test_validate_ops_repo.py pin cases; ops repository upstream.lock validated | passed |
| REQ-OPSREPO-NO-PLAINTEXT | OPS-1795328289814121 | test_validate_ops_repo.py; ops repository validator and gitleaks clean after import | passed |
| REQ-OPSREPO-KIT-MAP | OPS-1795328275356745 | mapping table in docs/how-to/local-operator-kit.md; catalog credentials carry authority | passed |
| REQ-OPSREPO-PUBLIC-HYGIENE | OPS-1795328289814121 | template documentation-address test; operator data only in the private repository | passed |
| REQ-OPSREPO-ROLLBACK | OPS-1795328305307912 | two-checkout tests; kit unchanged; imported inputs byte-equal to the kit | passed |
| REQ-OPSREPO-MERGE-GATE | OPS-1795328305307912 | effective rules on main; operator direct push refused (GH013); operator merged ops pull requests 2 and 3 | passed |

## Shared operational evidence ownership

| Source task | Operational owner | Requirement | Acceptance command | Evidence category | Source revision |
|---|---|---|---|---|---|
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-PIN | `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` | dry_run | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-NO-PLAINTEXT | `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` | dry_run | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-KIT-MAP | `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` | dry_run | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-PUBLIC-HYGIENE | `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` | dry_run | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-ROLLBACK | `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` | dry_run | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-PIN | `make dry-run ENV=staging` | staging | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-NO-PLAINTEXT | `make dry-run ENV=staging` | staging | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-KIT-MAP | `make dry-run ENV=staging` | staging | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-PUBLIC-HYGIENE | `make dry-run ENV=staging` | staging | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
| OPS-1795327950629406 | CIC-1795329226354380 | REQ-OPSREPO-ROLLBACK | `make dry-run ENV=staging` | staging | aa46b09758aa2b4e550b6d7b34aad67db06d6c56 |
