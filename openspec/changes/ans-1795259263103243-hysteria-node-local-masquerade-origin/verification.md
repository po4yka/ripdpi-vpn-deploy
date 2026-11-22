---
task_id: ANS-1795259263103243
change: ans-1795259263103243-hysteria-node-local-masquerade-origin
commit_sha: 0712fdca2f
local: passed
local_evidence: "On base 502ccc540, 2026-11-21: make -k -j 4 check ran 12700 unit tests passed, 5 failed by timeout under parallel load and passed when rerun alone (protocol liveness sentinel, operator maintenance stdin, observability authority rotation, transport site transaction, deploy controller wrapper syntax check); task-check failed on a stale board and ci-fast-scripts on an undeclared hysteria_masquerade_dir, both fixed and rerun green. make snapshot-check: 200 templates match; ansible-lint on the hysteria role: passed. make molecule-test ROLE=hysteria did not run locally: the amd64 Colima VM had no outbound network, so the pinned image could not be pulled; CI runs that scenario."
remote_ci: passed
remote_ci_evidence: "PR 671 (head d026022264): 51 checks passed; only the Trivy scan of the old debian13 image failed (sudo CVE), which PR 674 fixed before the merge. Main CI run 44923464687 on 696cab2c64, which contains all four follow-up changes and the refreshed debian13 Molecule image (PR 674): 84 of 84 jobs passed on 2026-11-21, including the four pytest groups, native runtime integration, native transport runtime acceptance and native four-transport acceptance lanes, every Molecule group and the Trivy scans of the refreshed images. The hysteria Molecule scenario, which serves the published tree over TCP and refuses a group-writable tree, passed."
dry_run: required
dry_run_evidence: "Partial: make dry-run at 90442f787 with hysteria_public_site_dir set passed on the device-full-staging node and the public-site role published the bundle; a vpn-p2-udp dry-run is still pending (the p2-udp profile needs monitoring, watchdog and backup secrets that no staging profile disables)."
staging: required
staging_evidence: "Partial, 2026-11-22: one disposable UpCloud node vpn-ci-staging-acc1 (device-full-staging, source 90442f787) was provisioned with a pinned SSH host-key seed, Tailnet-enrolled (lock-signed key), ownership-migrated and deployed; the data plane converged (xray, hysteria, nginx, AWG active). The controller then refused the disposable four-profile proof (onboarding-refused): the generated staging certificate is self-signed and the operator Colima executor does not trust it, while the liveness profiles require verified TLS. The node was destroyed through make staging-destroy with verified provider absence. Observed on the node: the Hysteria config masquerade was type file with dir /var/lib/public-site/<bundle digest>/current. Not done: an HTTP/3 request (no HTTP/3 client was available) and the TCP HTTPS/HTTP answers of a vpn-p2-udp node."
live: required
live_evidence: Pending the next deploy of a production vpn-p2-udp node with its own site bundle.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-HY-MASQUERADE-NODE-LOCAL | ANS-1795259540409372 | tests/unit/test_udp_node_audit.py renders the file masquerade on every listener, the www-data supplementary group and validator admission; tests/unit/test_public_site_contract.py and test_deploy_controller.py cover the bundle preflight and snapshot for hysteria_public_site_dir; Molecule verify pending in CI; staging pending | partial |
| REQ-HY-MASQUERADE-FILE-ADMISSION | ANS-1795259522975988 | Role assert before candidate validation; node validator refuses a directory outside the publisher tree (tests/unit/test_udp_node_audit.py); Molecule refusal of a group-writable tree pending in CI | partial |
