---
task_id: ANS-1795259263103243
change: ans-1795259263103243-hysteria-node-local-masquerade-origin
commit_sha: null
local: passed
local_evidence: "On base 502ccc540, 2026-11-21: make -k -j 4 check ran 12700 unit tests passed, 5 failed by timeout under parallel load and passed when rerun alone (protocol liveness sentinel, operator maintenance stdin, observability authority rotation, transport site transaction, deploy controller wrapper syntax check); task-check failed on a stale board and ci-fast-scripts on an undeclared hysteria_masquerade_dir, both fixed and rerun green. make snapshot-check: 200 templates match; ansible-lint on the hysteria role: passed. make molecule-test ROLE=hysteria did not run locally: the amd64 Colima VM had no outbound network, so the pinned image could not be pulled; CI runs that scenario."
remote_ci: required
remote_ci_evidence: Pending the PR checks, including the hysteria Molecule scenario that serves the published tree over TCP and refuses a group-writable tree.
dry_run: required
dry_run_evidence: Pending make dry-run on a vpn-p2-udp node with hysteria_public_site_dir set, under operator authorization.
staging: required
staging_evidence: Pending a disposable vpn-p2-udp node under operator authorization that answers HTTP/3, HTTPS and HTTP from the node-local site.
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
