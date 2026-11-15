---
task_id: SEC-1794728936979277
change: sec-1794728936979277-revocation-and-pinned-delivery
commit_sha: 545221f8
local: passed
local_evidence: "make -k -j 4 check on the pre-commit tree: every target passed except test-unit, where two files failed (62 cases in test_client_drift.py, whose Terraform stub lacked the ssh_port output that issuance now reads, and the tracked-address guard on reverse-DNS literals in test_doh_lookup.py). Both were fixed and those files, with the identifier policy and docs index tests, then passed (106 cases); the other 12022 unit cases had passed in that run. Focused modules for rollback, share bundles, issuance SSH, the mirror and rotation passed; ansible-lint on the subscription-host role, snapshot-check, shellcheck and docs-check passed. Molecule for subscription-host did not run: the pinned Debian image has no arm64 manifest on the operator workstation. One independent review; its findings were fixed before the gate run."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request, including the subscription-host Molecule scenario, which is the first run of the mirror units under systemd.
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
