---
task_id: SCR-1795352512092131
change: scr-1795352512092131-disposable-executor-staging-trust-anchor
commit_sha: null
local: passed
local_evidence: "2026-11-22 working tree on baa165961: `python3 -m pytest tests/unit/test_provision_disposable_liveness_runtime.py` 27 passed (accepts the generator's own `openssl req -x509` certificate, CA:TRUE, CA:FALSE and no basicConstraints; refuses a bundle, a private key in the file, a CA-issued leaf, a same-name certificate signed by another key, expired, not yet valid, no SAN, IP-only SAN, two names, a wildcard, DER and oversized input with no executor contact; installs into the executor store and runs update-ca-certificates only with an anchor); `tests/unit/test_disposable_liveness_make.py` 41 passed (the provision goal refuses unowned, `$(...)` and quoted values for all three fields; the anchor reaches the script only when given); `make docs-check` passed. `make -k -j 4 check` passed except a stale board (regenerated, `make task-check` then passed) and seven load-induced timeouts in unrelated modules (observability deadman, transport site transaction, bootstrap readiness, executable coverage), which passed when rerun serially (22 passed)."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change touches only the operator-side disposable executor provisioning; no deployed runtime changes.
staging: required
staging_evidence: "Partial, 2026-11-23/24: make provision-disposable-liveness-runtime with STAGING_TRUST_ANCHOR set to the generated certificate of the disposable node vpn-ci-staging-acc4 installed it on two real Colima executors (arm64) and reported its SHA-256 fingerprint and the pinned runtime versions. No deploy reached the onboarding proof: every deploy stopped earlier during the first WARP install (nine first-install defects, fixed in PRs 694, 701, 704, 705, 710, 711, 712, 713 and 714). Verified-TLS four-profile acceptance through the anchor is therefore not done. The node was destroyed with verified provider absence, and the executor that the intent named was retired through the unbound path."
live: not_applicable
live_evidence: The disposable executor is deleted at de-onboarding. The `useSystemCA` profile field reaches a fleet sentinel only when its profile is next installed; fleet system stores carry the public CAs that issue production certificates, and no production node changes.
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
| REQ-STAGING-TRUST-ANCHOR-VALIDATION | SCR-1795352837575574 | `test_trust_anchor_refuses_unsuitable_input_before_the_executor` (12 cases), `test_trust_anchor_accepts_one_valid_self_signed_certificate` (5 shapes) | pass (local) |
| REQ-STAGING-TRUST-ANCHOR-XRAY | SCR-1795371731256603 | `test_four_profiles_are_materialized_with_only_named_client_material` asserts `useSystemCA` on the XHTTP outbound; on the 2026-11-22 executor the pinned Xray 26.10.31 reported `p1-xhttp` blocked with `x509: certificate signed by unknown authority` without the field and HTTP 204 with it | pass (local) |
