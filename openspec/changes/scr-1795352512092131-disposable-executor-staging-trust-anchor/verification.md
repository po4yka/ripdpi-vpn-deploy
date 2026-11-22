---
task_id: SCR-1795352512092131
change: scr-1795352512092131-disposable-executor-staging-trust-anchor
commit_sha: null
local: passed
local_evidence: "2026-11-22 working tree on baa165961: `python3 -m pytest tests/unit/test_provision_disposable_liveness_runtime.py` 25 passed (accepts the generator's own `openssl req -x509` certificate, CA:TRUE, CA:FALSE and no basicConstraints; refuses a bundle, a private key in the file, a CA-issued leaf, a same-name certificate signed by another key, expired, not yet valid, no SAN, IP-only SAN, DER and oversized input with no executor contact; installs into the executor store and runs update-ca-certificates only with an anchor); `tests/unit/test_disposable_liveness_make.py` 41 passed (the provision goal refuses unowned, `$(...)` and quoted values for all three fields; the anchor reaches the script only when given); `make docs-check` passed. `make -k -j 4 check` passed except a stale board (regenerated, `make task-check` then passed) and seven load-induced timeouts in unrelated modules (observability deadman, transport site transaction, bootstrap readiness, executable coverage), which passed when rerun serially (22 passed)."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change touches only the operator-side disposable executor provisioning; no deployed runtime changes.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: The disposable executor is deleted at de-onboarding; no production node or fleet sentinel changes.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-STAGING-TRUST-ANCHOR-INSTALL | SCR-1795352837575574 | `test_provision_installs_the_anchor_into_the_executor_store_only_when_given`, `test_provision_passes_the_staging_trust_anchor_only_when_given` | pass (local) |
| REQ-STAGING-TRUST-ANCHOR-VALIDATION | SCR-1795352837575574 | `test_trust_anchor_refuses_unsuitable_input_before_the_executor` (10 cases), `test_trust_anchor_accepts_one_valid_self_signed_certificate` (5 shapes) | pass (local) |
