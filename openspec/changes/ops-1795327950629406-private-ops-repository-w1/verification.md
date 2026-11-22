---
task_id: OPS-1795327950629406
change: ops-1795327950629406-private-ops-repository-w1
commit_sha: null
local: required
local_evidence: "make -k check -j 4: tofu test, bats 92, vpnd 551, unit 12765 passed with one load-sensitive failure that passes alone; validate failed on staged gitleaks for literal key markers, fixed, then make validate passed. New tests: test_validate_ops_repo.py (20), test_deploy_controller.py two-checkout dry-run (fails on the previous controller), test_render_inventory.py external tfvars and output, test_terraform_env.py plan var-file. After independent review: validator tightened (content-based plaintext detection, sops.json, any .dec, encrypted-value check, symlinks, PGP/WireGuard keys, malformed policy, Git-committable scope), relative TFVARS_ROOT refused in Make; test_validate_ops_repo.py and test_terraform_env.py 42 passed; validator passes all 34 real kit SOPS documents in a scratch copy; gitleaks staged clean."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPSREPO-PIN | OPS-1795328289814121 | `pytest tests/unit/test_validate_ops_repo.py -k pin` | planned |
| REQ-OPSREPO-NO-PLAINTEXT | OPS-1795328289814121 | `pytest tests/unit/test_validate_ops_repo.py -k plaintext`; gitleaks in the ops repo | planned |
| REQ-OPSREPO-KIT-MAP | OPS-1795328275356745 | mapping table in `docs/how-to/local-operator-kit.md`; validator `-k authority` test | planned |
| REQ-OPSREPO-PUBLIC-HYGIENE | OPS-1795328289814121 | template placeholder test; review of `templates/ops-repo/` | planned |
| REQ-OPSREPO-ROLLBACK | OPS-1795328305307912 | Two-checkout plan and inventory selection tests, kit comparison and private-repository reject/approve runs | planned |
