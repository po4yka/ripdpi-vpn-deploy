---
task_id: OPS-1795351496232576
change: ops-1795351496232576-private-ops-repository-evidence-w1b
commit_sha: aa46b09758aa2b4e550b6d7b34aad67db06d6c56
local: passed
local_evidence: "pytest tests/unit/test_validate_ops_repo.py: 45 passed; scripts/validate-ops-repo.py on ops main 7e44faa: exit 0; validate-ops-environments.py --root ops --public-repo .: valid, upstream.lock pin reachable from origin/main; gitleaks git on the ops repository: no leaks found"
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy ci run 45014981101 on main at aa46b0975 (pull request 683, the W1 implementation): completed with success. Pull request 686 changes only task records."
dry_run: passed
dry_run_evidence: "check-mode dry-run of node-c through the ops inventory (ops config/inventories/current.ini at 7e44faa, ops SOPS documents and host pins) at source d7a08417, run by the core-d7a08417 fleet rollout: decrypt, dry-run and clean exit 0, passed, plaintext absent (kit receipt core-d7a08417-20261126/node-c-check.json, 2026-11-26T12:46Z)"
staging: not_applicable
staging_evidence: W1 changes input paths only and production inputs are byte-identical to the kit; decided at creation.
live: passed
live_evidence: "The private ops repository serves the live fleet inputs: the W4 rollout (f9d6a513) and the core-d7a08417 rollout read inventory, host pins and SOPS documents from it; its main rules and owner-only merges are in force (14 merged ops pull requests)."
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPSREPO-PIN | OPS-1795351556503213 | `test_pin_must_be_a_full_lowercase_commit_sha`, `test_pin_must_name_the_public_repository`; `validate-ops-environments.py --public-repo` finds the ops upstream.lock revision on public origin/main | passed |
| REQ-OPSREPO-NO-PLAINTEXT | OPS-1795351556503213 | plaintext, key, symlink and SOPS-metadata cases in `test_validate_ops_repo.py`; `validate-ops-repo.py` exit 0 and gitleaks clean on ops main 7e44faa | passed |
| REQ-OPSREPO-KIT-MAP | OPS-1795351556503213 | mapping table in `docs/how-to/local-operator-kit.md` (Mapping to the ops repository); `test_catalog_credentials_need_an_allowed_authority` | passed |
| REQ-OPSREPO-PUBLIC-HYGIENE | OPS-1795351556503213 | `test_template_holds_only_documentation_addresses`; operator inputs imported only into the private ops repository (ops pull request 3) | passed |
| REQ-OPSREPO-ROLLBACK | OPS-1795351595564040 | imported inventory (ops 7c8abe9) is byte-equal to kit config/inventory-audit-fixes-20261120/current-inventory.ini; `fleet_inspection.select_hosts` gives node-c and its sentinel node-b the same address, port, user and variables in ops and kit except `admin_ssh_public_keys` (the W4 CI key); ops and kit host pins are byte-equal; node-c check through the ops inventory passed | passed |
| REQ-OPSREPO-MERGE-GATE | OPS-1795351556503213 | ops main rules deletion, non_fast_forward, pull_request and update are active; merge-gate-probe run 45020331959: the workflow token could not land a change; the owner merged ops pull requests 2 to 15 | passed |
