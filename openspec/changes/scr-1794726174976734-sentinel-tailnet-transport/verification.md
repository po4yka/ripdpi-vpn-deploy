---
task_id: SCR-1794726174976734
change: scr-1794726174976734-sentinel-tailnet-transport
commit_sha: null
local: passed
local_evidence: On the working tree over fd5d4e03, tests/unit/test_cloud_promotion_scope.py passes 36 tests, including the public route, both Tailnet address families, a Tailnet route on port 2222, refusals for a foreign alias key and a public alias on a Tailnet route, and categorical refusals before any SSH for unrelated, loopback, integer and missing transports. An independent review found test gaps only; they are closed.
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The change affects only the operator-side SSH route to an existing sentinel; the production prepare and dry-run exercise it before any mutation.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client-visible behavior changes.
artifact: required
artifact_evidence: docs/how-to/deploy.md and scripts/DESIGN-NOTES.md describe the Tailnet route and its pin requirement.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SENTINEL-TRANSPORT-PUBLIC | SCR-1794726257687734 | test_cloud_scope_requires_distinct_state_bound_resources_and_live_original_pin, test_nondefault_sentinel_port_uses_one_canonical_pin_alias | passed |
| REQ-SENTINEL-TRANSPORT-TAILNET | SCR-1794726257687734 | test_tailnet_route_reaches_the_sentinel_pinned_for_its_state_address, test_tailnet_route_on_a_nondefault_port_checks_the_bracketed_pins, test_tailnet_route_refuses_an_unbound_identity | passed |
| REQ-SENTINEL-TRANSPORT-REFUSE | SCR-1794726257687734 | test_transport_outside_the_state_address_and_tailnet_refuses_before_ssh, test_cloud_scope_refuses_changed_or_local_sentinel | passed |
