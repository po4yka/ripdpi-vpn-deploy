---
task_id: SEC-1793385377599445
change: sec-1793385377599445-reality-admission-delivery-repairs
commit_sha: 91f1d57c32c41929eaf4c93fb9335ea07313d02a
local: passed
local_evidence: On 91f1d57c32c4, the narrow tests for every requirement passed, as did snapshot-check, make shellcheck, docs-check and all pre-commit hooks. In the full make -k -j 4 check, every target passed except test-unit (31 failures) and the vpnd tests plus vpnd-package-check (9 failures). The same failures reproduce on clean main 6297d207 in this container, which has no IPv6, runs as root and has no native tools. Native lanes for the touched native tests were not runnable locally.
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
