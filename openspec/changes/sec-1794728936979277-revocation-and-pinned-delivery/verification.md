---
task_id: SEC-1794728936979277
change: sec-1794728936979277-revocation-and-pinned-delivery
commit_sha: 27c95d74ea1143d071236d48406be51603556321
local: passed
local_evidence: "make -k -j 4 check on the pre-commit tree: every target passed except test-unit, where two files failed (62 cases in test_client_drift.py, whose Terraform stub lacked the ssh_port output that issuance now reads, and the tracked-address guard on reverse-DNS literals in test_doh_lookup.py). Both were fixed and those files, with the identifier policy and docs index tests, then passed (106 cases); the other 12022 unit cases had passed in that run. Focused modules for rollback, share bundles, issuance SSH, the mirror and rotation passed; ansible-lint on the subscription-host role, snapshot-check, shellcheck and docs-check passed. Molecule for subscription-host did not run: the pinned Debian image has no arm64 manifest on the operator workstation. One independent review; its findings were fixed before the gate run. Integrated gate on the tree of cb173d5a, before its rebase onto two task-bookkeeping commits of main (all six tasks on one branch): make -k -j 4 check passed every target except test-unit, where 12170 cases passed and one failed, test_tailnet_network_executor.py::test_expiry_serializes_with_forward_mark_and_rolls_back_true; it is timing-sensitive under the parallel run, passes alone and with its file, and this branch changes no tailnet code."
remote_ci: passed
remote_ci_evidence: "CI run 43712765464 on main at 827d555e: 81 jobs passed. The two failed native jobs (native runtime integration 3/4, native four-transport acceptance core-1) failed only at tests/unit/test_xhttp_endpoint_contract_native.py line 154, a parsing defect in a test of XRY-1794729068388916. The subscription-host Molecule scenario passed; it is the first run of the mirror units under systemd. Its first run on the pull request failed on a repeated mirror retirement, which 827d555e fixes."
dry_run: required
dry_run_evidence: Pending dry-run of the subscription host and the transport nodes after merge.
staging: required
staging_evidence: Pending one mirror pull and publication on a staging subscription host with a pinned build worker key.
live: required
live_evidence: Pending deploy, one revocation with a share bundle, and one issuance over pinned SSH.
client: not_applicable
client_evidence: No client payload format changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-RPD-ROLLBACK-REVOCATION | SEC-1794728996747903 | `test_transport_runtime_adapter.py`: readmission refusals, the plan function with a recording transaction, and the refusal category on stderr; a live refusal is pending | required |
| REQ-SEC-RPD-SHARE-REVOCATION | SEC-1794729007676570 | `test_subscription_share_redaction.py` runs the role tasks through ansible-playbook: a revoked bundle is removed, a declared revoked token gets none, other bundles stay; Molecule pending | required |
| REQ-SEC-RPD-PINNED-PAYLOAD-SSH | SEC-1794729019627773 | `test_client_registry.py`: a stub ssh records the argument list of both issuance calls | passed |
| REQ-SEC-RPD-MIRROR-IDENTITY | SEC-1794729019627773 | `test_subscription_mirror.py`: credential ownership, unit users and ordering, the input guard through ansible-playbook, fetch and publish behaviour; the units have not run under systemd | required |
| REQ-SEC-RPD-DATA-KEY-ROTATION | SEC-1794729031539704 | `test_operator_admission.py`: order of the two sops calls, restore on either failure, refusal at a stale copy | passed |
