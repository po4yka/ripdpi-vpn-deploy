---
task_id: SCR-1795352512092131
change: scr-1795352512092131-disposable-executor-staging-trust-anchor
commit_sha: d09191ca4ba8dc38e69441f0f4dca7916109e39f
local: passed
local_evidence: "2026-11-22 working tree on baa165961: `python3 -m pytest tests/unit/test_provision_disposable_liveness_runtime.py` 27 passed (accepts the generator's own `openssl req -x509` certificate, CA:TRUE, CA:FALSE and no basicConstraints; refuses a bundle, a private key in the file, a CA-issued leaf, a same-name certificate signed by another key, expired, not yet valid, no SAN, IP-only SAN, two names, a wildcard, DER and oversized input with no executor contact; installs into the executor store and runs update-ca-certificates only with an anchor); `tests/unit/test_disposable_liveness_make.py` 41 passed (the provision goal refuses unowned, `$(...)` and quoted values for all three fields; the anchor reaches the script only when given); `make docs-check` passed. `make -k -j 4 check` passed except a stale board (regenerated, `make task-check` then passed) and seven load-induced timeouts in unrelated modules (observability deadman, transport site transaction, bootstrap readiness, executable coverage), which passed when rerun serially (22 passed)."
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy ci run 45426312839 on main at d09191ca4: completed with success. That revision differs from the staging revision 60a371e4b only in task and OpenSpec records. The ci run 45420645053 on main at 60a371e4b itself failed in the job native runtime integration (1/4)."
dry_run: not_applicable
dry_run_evidence: The change touches only the operator-side disposable executor provisioning; no deployed runtime changes.
staging: passed
staging_evidence: "2026-11-23/24, partial: make provision-disposable-liveness-runtime with STAGING_TRUST_ANCHOR set to the generated certificate of the disposable node vpn-ci-staging-acc4 installed it on two real Colima executors (arm64) and reported its SHA-256 fingerprint and the pinned runtime versions. No deploy reached the onboarding proof: every deploy stopped earlier during the first WARP install (nine first-install defects, fixed in PRs 694, 701, 704, 705, 710, 711, 712, 713 and 714). Verified-TLS four-profile acceptance through the anchor is therefore not done. The node was destroyed with verified provider absence, and the executor that the intent named was retired through the unbound path. 2026-11-24/25, revision 60a371e4b, disposable node vpn-ci-staging-acc5 (Debian 13): the anchor was installed on two more Colima executors (arm64) from the node's generated certificate. A deploy with cohort device-full-staging completed its Ansible play (ok=892, failed=0), onboarded the executor and created the binding, then ended with exit code 2: the controller's promotion proof returned promotion-proof-failed about 30 seconds after onboarding, cause not determined. About two minutes later the same command, scripts/sshd-promotion-proof.py with the promotion configuration that the controller wrote, returned status passed in 6 seconds: decision healthy, control ok, p0-reality, p1-xhttp, p2-hysteria2 and p2-amneziawg all ok with an authenticated handshake and DNS through the tunnel, and a fresh AmneziaWG handshake. The executor's Xray reached the node's XHTTP profile with verified TLS through the installed anchor. Accepted by the owner on the rerun of the proof; a deploy whose own promotion proof passes was not observed. The node was destroyed with verified provider absence, the expired first executor was retired through make retire-expired-disposable-liveness, the bound executor and its client were de-onboarded, and the Tailnet device and key were deleted."
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
| REQ-STAGING-TRUST-ANCHOR-INSTALL | SCR-1795352837575574 | `test_provision_installs_the_anchor_into_the_executor_store_only_when_given`, `test_provision_passes_the_staging_trust_anchor_only_when_given` | passed |
| REQ-STAGING-TRUST-ANCHOR-VALIDATION | SCR-1795352837575574 | `test_trust_anchor_refuses_unsuitable_input_before_the_executor` (12 cases), `test_trust_anchor_accepts_one_valid_self_signed_certificate` (5 shapes) | passed |
| REQ-STAGING-TRUST-ANCHOR-XRAY | SCR-1795371731256603 | `test_four_profiles_are_materialized_with_only_named_client_material` asserts `useSystemCA` on the XHTTP outbound; on the 2026-11-22 executor the pinned Xray 26.10.31 reported `p1-xhttp` blocked with `x509: certificate signed by unknown authority` without the field and HTTP 204 with it; on 2026-11-25 the four-profile proof through the anchor returned passed on the disposable node vpn-ci-staging-acc5 (step SCR-1795353017817845) | passed |
