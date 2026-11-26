---
task_id: SEC-1795328680299474
change: sec-1795328680299474-ci-identities-environments-w4
commit_sha: null
local: passed
local_evidence: "tests/unit/test_validate_ops_environments.py and tests/unit/test_ci_age_revocation.py: 32 passed (real sops 3.13.3 and age); scripts/validate-ops-environments.py --root on ops main 7e44faa: valid, and check_catalog over all 14 tofu-plan and tofu-apply secret pairs returns no findings"
remote_ci: required
remote_ci_evidence: null
dry_run: passed
dry_run_evidence: "baseline check (dry-run) with both admin keys at source f9d6a5139 and ops d0cd346 passed on node-a, node-b and node-c (kit receipts w4-ci-key-f9d6a513-20261124/node-*-check.json); the reviewed preview adds only the CI key to the admin authorized_keys and removes nothing (node-*-preview-review.json)"
staging: not_applicable
staging_evidence: "Owner decision on 2026-11-26: the baseline Molecule scenario that writes both admin keys and then revokes the CI key, plus the real SOPS rotation test, cover the revoke; no staging revoke drill was run."
live: passed
live_evidence: "baseline deploy with both admin keys at source f9d6a5139 and ops f852e94 passed with verify, security-verify, smoke-test and protocol liveness on node-a, node-b and node-c (w4-ci-key-f9d6a513-20261124/node-*-deploy.json); ops ci-identities-bootstrap run 45226532049 generated the CI identities, and its rerun refused to replace them (w4-overwrite-refusal-drill-20261125.json); Tailnet policy change validated and applied (tailnet-policy-ci-tags-20261123.json) and ops tailnet-policy run 45550835434 succeeded; provider and state tokens stored and catalogued (w4-*-ci-env-secrets-*.json, ops #15)"
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIID-SEPARATE | SEC-1795328879513998 | baseline Molecule scenario writes the operator and CI keys, revokes the CI key and keeps the operator key (`ansible/roles/baseline/molecule/default/verify.yml`) | passed |
| REQ-CIID-SEPARATE | SEC-1795328913746423 | `tests/unit/test_ci_age_revocation.py`: after `sops updatekeys` the retained pre-revocation CI stanza still opens the document; after `sops rotate -i` it does not, and the operator key still decrypts. The deployment documents hold the operator and CI recipients (ops #10). Provider tokens are separate service identities per environment (ops #15) | passed |
| REQ-CIID-ENV-MATRIX | SEC-1795328868236026 | `pytest tests/unit/test_validate_ops_environments.py -k matrix` | passed |
| REQ-CIID-BOOTSTRAP | SEC-1795328902011315 | `pytest tests/unit/test_validate_ops_environments.py -k bootstrap`; ops run 45226532049 receipt with the public halves (`ci-identities-generated-20261123.json`); refused overwrite (`w4-overwrite-refusal-drill-20261125.json`); token revocation (`w4-ci-bootstrap-token-revoked-20261125.json`) | passed |
| REQ-CIID-MERGE-GATE | SEC-1795328902011315 | ruleset and environment receipt (`w4-environments-ruleset-20261125.json`); ops merge-gate-probe run 45020331959: the workflow token could not land a change on main | passed |
| REQ-CIID-MUTATION-TRIGGER | SEC-1795328868236026 | `pytest tests/unit/test_validate_ops_environments.py -k trigger`; environment branch policy in `w4-environments-ruleset-20261125.json` | passed |
| REQ-CIID-UNTRUSTED-INPUT | SEC-1795328868236026 | `-k untrusted_input` (typed toggle previews; target, pin, symlink, rename and non-descendant head defer) and `-k preview` (no secret before `--pr`) | passed |
| REQ-CIID-LEAST-PRIVILEGE | SEC-1795328913746423 | ops catalog entries with scope, expiry and revocation (ops #15); kit receipts `w4-scw-ci-env-secrets-20261125.json`, `w4-upcloud-ci-env-secrets-20261126.json`, `w4-vultr-ci-env-secrets-20261126.json`, `w4-tailscale-ci-oidc-20261126.json`. UpCloud offers no read-only level, so its plan token is write-capable (accepted risk). No new token has made an API call yet; the first W7 run exercises them | passed |
