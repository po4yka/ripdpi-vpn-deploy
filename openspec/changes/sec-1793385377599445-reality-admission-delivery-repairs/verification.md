---
task_id: SEC-1793385377599445
change: sec-1793385377599445-reality-admission-delivery-repairs
commit_sha: c7c2dd99fc446cb642a2ca1ab832056fb69f10da
local: passed
local_evidence: On c7c2dd99fc44, the narrow tests for every requirement passed. snapshot-check, make shellcheck, docs-check, all pre-commit hooks and all 70 bats tests passed; bats ran with the pinned Python on PATH because a mise shim under the test's temporary HOME lacks PyYAML. In the earlier make -k -j 4 check, test-unit (31 failures), vpnd-test (9), vpnd-package-check and bats-test failed. PR CI exposed four new_client_atomic.bats failures from a fixture without xhttp_path; that fixture is fixed and the four tests reproduced and then passed. The other failures reproduce on clean main 6297d207 in this container: no IPv6, root, no native tools, and the mise HOME shim. Native lanes for the touched native tests were not runnable locally.
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending an authorized per-node dry-run that previews the rendered maxTimeDiff and probe fingerprint changes.
staging: required
staging_evidence: Pending a staging converge with the 90-second replay window and an authenticated P0 probe.
live: required
live_evidence: Pending an authorized production deploy and verify.
client: required
client_evidence: Pending import of an emitted share URI in a VLESS client and authenticated traffic.
artifact: required
artifact_evidence: Snapshot goldens, the re-encrypted sample fixture and the reference docs were updated; PR review pending.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REALITY-REPLAY-WINDOW | SEC-1793385515086119 | test_p0_reality_shape_contract.py replay-window render and preflight tests; xray golden shows maxTimeDiff 90000 | Local passed; remote CI and deploy required |
| REQ-XRAY-PRODUCTION-PIN | SEC-1793385515749582 | test_xray_version_pin.py allowlist parity and Templar preflight cases (prod unlisted refused, staging admitted) | Local passed; remote CI and deploy required |
| REQ-PROBE-FINGERPRINT | SEC-1793385516458547 | test_probes_present_the_configured_recipient_fingerprint renders watchdog REALITY/XHTTP and smoke with firefox | Local passed; remote CI and deploy required |
| REQ-SHARE-URI | SEC-1793385517096983 | test_uri_qr_encodes_one_complete_share_uri_without_changing_secrets (exact URI; ambiguous selection refused; secrets byte-identical) | Local passed; remote CI and deploy required |
| REQ-BUNDLE-TOPOLOGY-TRUTH | SEC-1793385517743702 | test_emit_bundle_host_selection.py asserts split_hop_egress false with the ingress responder enabled | Local passed; remote CI and deploy required |
| REQ-XHTTP-PATH-SECRECY | SEC-1793385518379176 | test_published_or_absent_path_is_refused plus the existing-path acceptance cases; bootstrap emits 16 random bytes | Local passed; remote CI and deploy required |
