---
task_id: ANS-1794729221714172
change: ans-1794729221714172-awg-per-instance-wire-shape
commit_sha: 6962e101
local: passed
local_evidence: "Focused modules passed (388 tests: test_transport_semantics, test_secrets_schema, test_amneziawg_version_floor, test_bootstrap_awg_handoff, test_provider_listeners_parity, test_listener_contract, test_docs_index, test_agent_instructions); the new tests fail with the non-test changes reverted. make tf-test exit 0 (278 provider runs), make tf-policy-verify, snapshot-check, shellcheck, docs-check and ansible-lint for the amneziawg role exit 0. The complete unit collection ran once: every remaining failure is a native_runtime test that needs Linux, or the tracked-address check on tests/unit/test_doh_lookup.py from 839b45f8, which this change does not touch. make check did not run here: the lead runs one gate on the integrated branch. Molecule for the amneziawg role did not run: the pinned image has no arm64 manifest on the operator workstation. One independent review found no high or medium defect."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request, including the amneziawg and full-stack Molecule scenarios.
dry_run: required
dry_run_evidence: Pending dry-run of each production node; a node with published values or port 51820 must refuse.
staging: required
staging_evidence: Pending a staging deploy with the published fixture values, which must still pass.
live: required
live_evidence: Pending replacement of the values on each production instance, the provider plan for the new port, and the deploy.
client: required
client_evidence: Pending redelivery of the device configurations and one handshake per instance.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-SHAPE-GENERATED | ANS-1794729302489703 | `test_transport_semantics.py`: 200 generated sets are in bounds, admitted and distinct; the redraw after equal sizes and after the published set; the CLI flag. `test_bootstrap_awg_handoff.py`: two real bootstrap runs write different generated values | passed |
| REQ-PROTO-AWG-SHAPE-EXPLICIT | ANS-1794729302489703 | `test_secrets_schema.py`: strict production refuses the published set and names the replacement path, staging accepts it, every document requires the five values; `test_transport_semantics.py`: effective fallback refused, cohort set admitted, real preflight refuses on `env: prod` before mutation | passed |
| REQ-PROTO-AWG-SHAPE-HEADERS | ANS-1794729321608732 | `test_amneziawg_version_floor.py` runs the guard through real `ansible-playbook`: padded instance with a low header refused on prod, measured and staging accepted, random headers accepted; Molecule pending in CI | passed |
| REQ-PROTO-AWG-SHAPE-PORT | ANS-1794729336937986 | `test_secrets_schema.py` and `test_transport_semantics.py` for port 51820; `firewall.tftest.hcl` in the four roots: the legacy list has no AmneziaWG entry and the contract carries exactly the declared UDP port (rule-level on both address families for one root, existing per-listener rule tests for the others); provider plan and live port pending | passed |
