---
task_id: SEC-1794729384681094
change: sec-1794729384681094-edge-ingest-and-runner-gates
commit_sha: aba8fed5
local: passed
local_evidence: "Focused checks on the implementation tree, each exit 0: make tf-policy-verify (73 Rego tests), make tf-test, offline Hetzner and Vultr plans with placeholder tokens through scripts/check-tf-plan.sh, make snapshot-check, make docs-check, make shellcheck, make actionlint-check, make zizmor-check, make yamllint-check, ansible-lint for observability_control_plane and observability_agent, openspec validate --strict, and the focused pytest modules (1667 passed). Ten tests in that run failed for local reasons and are not caused by this change: nine need Linux or a pinned native binary or timed out under load and also fail on the unmodified commit or pass alone, and test_repository_identifier_policy reports addresses in tests/unit/test_doh_lookup.py, which this change does not touch. The full make check did not run here: the lead session runs it once on the integrated branch. Molecule did not run: the pinned image has no arm64 manifest on the operator workstation, so the edited observability_control_plane enabled scenario has no runtime evidence. One independent review; its findings on the relay rules, the Rego attachment helper and the runner test were fixed before the commit."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request, including the observability_control_plane enabled Molecule scenario, whose fixture pushes changed, and the rendered-plan policy job.
dry_run: required
dry_run_evidence: Pending dry-run of the collector host after merge.
staging: not_applicable
staging_evidence: The policy, workflow and test changes have no host effect; the relay change reaches the existing collector through the ordinary deploy transaction.
live: required
live_evidence: Pending collector deploy with a relay start on the new flags and stored series from each enrolled node, and one reviewed make repository-policy-plan against the live repository.
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-EIG-EDGE-FIREWALL | SEC-1794729475212458 | `server_metadata_test.rego`: denial of a changed plan with the firewall off; passes for creation, replacement, promotion, an interrupted first apply and an empty plan; missing-attachment and default-accept denials; a reference known only after apply passes. Offline Hetzner and Vultr plans pass the gate | passed |
| REQ-SEC-EIG-RELAY-LIMITS | SEC-1794729504775329 | `test_observability_control_plane_render.py`: rendered rules drop unknown names, labels and jobs and keep sender series; the relay lists equal the sender lists; limit flags; a zero or text budget is refused by the role. Relay goldens. No Molecule push over the limit was added, and the changed Molecule fixture pushes have not run | required |
| REQ-SEC-EIG-RUNNER-LANE | SEC-1794729526950019 | `test_required_protective_workflows.py`: runner gate with reject cases that name the file, publish triggers; `test_branch_protection_contract.py`: plan, apply, failed readback and weaker recorded value with a stub API. The live setting is not read | passed |
| REQ-SEC-EIG-AGENT-SETTINGS | SEC-1794729547422604 | `test_agent_instructions.py`: the tracked file passes; a hook, a status line command, shell and tool allow entries and a bypass mode are refused | passed |
