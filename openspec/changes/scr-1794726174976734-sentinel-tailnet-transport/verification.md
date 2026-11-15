---
task_id: SCR-1794726174976734
change: scr-1794726174976734-sentinel-tailnet-transport
commit_sha: da6fb86d0e85b9bd99bb7b8c6ab17ad4409cf3fe
local: passed
local_evidence: On the working tree over fd5d4e03, tests/unit/test_cloud_promotion_scope.py passes 36 tests, including the public route, both Tailnet address families, a Tailnet route on port 2222, refusals for a foreign alias key and a public alias on a Tailnet route, and categorical refusals before any SSH for unrelated, loopback, integer and missing transports. An independent review found test gaps only; they are closed.
remote_ci: passed
remote_ci_evidence: PR 606 CI passed on its head, and main CI run 43689450170 passed on da6fb86d.
dry_run: passed
dry_run_evidence: On 2026-11-15 the production node-b prepare at da6fb86d admitted sentinel node-a over its Tailnet address through cloud_promotion_scope; the same input refused at fd5d4e03 because public SSH to the sentinel timed out. The following dry-run passed with 5 changed and 0 failed tasks.
staging: not_applicable
staging_evidence: The change affects only the operator-side SSH route to an existing sentinel; the production prepare and dry-run exercise it before any mutation.
live: passed
live_evidence: On 2026-11-15 the node-b deploy at da6fb86d passed deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness; the sentinel install and the external-vantage proof ran over the Tailnet management route and reported healthy with p1-xhttp ok.
client: not_applicable
client_evidence: No client-visible behavior changes.
artifact: passed
artifact_evidence: docs/how-to/deploy.md and scripts/DESIGN-NOTES.md describe the Tailnet route and its pin requirement.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SENTINEL-TRANSPORT-PUBLIC | SCR-1794726257687734 | test_cloud_scope_requires_distinct_state_bound_resources_and_live_original_pin, test_nondefault_sentinel_port_uses_one_canonical_pin_alias | passed |
| REQ-SENTINEL-TRANSPORT-TAILNET | SCR-1794726257687734 | test_tailnet_route_reaches_the_sentinel_pinned_for_its_state_address, test_tailnet_route_on_a_nondefault_port_checks_the_bracketed_pins, test_tailnet_route_refuses_an_unbound_identity | passed |
| REQ-SENTINEL-TRANSPORT-REFUSE | SCR-1794726257687734 | test_transport_outside_the_state_address_and_tailnet_refuses_before_ssh, test_cloud_scope_refuses_changed_or_local_sentinel | passed |
