---
task_id: ANS-1795260057878312
change: ans-1795260057878312-split-hop-ingress-fail-closed-teardown
commit_sha: null
local: passed
local_evidence: "On base 502ccc540, 2026-11-21: make -k -j 4 check exit 2, with every check passed except task-check (board stale after taskctl start); ./taskctl generate-board, then make task-check exit 0. The unit suite passed 12692 tests, make snapshot-check passed 200 templates, ansible-lint passed. The two native split-hop test files ran as root in a privileged Linux container (kernel 6.8.0, nftables 1.1.3): 3 passed. With the base templates and boundary.yml, the same native tests fail. The family test failed with curl exit 28 after 3.04 s, which is the timeout this change removes. The routing test failed because table 200 was empty. make molecule-test ROLE=split-hop-ingress could not run locally, because the amd64 Molecule image does not run on this arm64 Colima VM (exec format error); CI runs it."
remote_ci: required
remote_ci_evidence: Pending the PR checks, including Molecule split-hop-ingress. The native split-hop lane runs on the main push only.
dry_run: required
dry_run_evidence: Pending make dry-run on a split-hop ingress node under operator authorization.
staging: required
staging_evidence: Pending a disposable Node A and Node B pair under operator authorization. Stop the tunnel, then check that a device flow gets ICMP unreachable, that a guarded frontend connect fails within one second, that no packet leaves by the direct uplink, and that retirement leaves no rule, route or reject chain.
live: not_applicable
live_evidence: No production split-hop pair exists yet.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SPLIT-HOP-DOWN-FORWARD-ERROR | ANS-1795260140617842 | `tests/unit/test_split_hop_native.py::test_family_scope_sends_recipient_and_device_egress_only_through_b`: with the tunnel down, the device connect fails with curl exit 7 in under 1 s, and the uplink listener receives nothing. Staging is pending. | local passed |
| REQ-SPLIT-HOP-DOWN-LOCAL-REJECT | ANS-1795260176389101 | Both native tests: guarded-UID connects fail with exit 7 in under 1 s, and own-address listeners stay reachable. After the replayed loader restart (tunnel stop, loader start, tunnel start), routing through B recovers. Staging is pending. | local passed |
| REQ-SPLIT-HOP-RETIREMENT-CLEAN | ANS-1795260207966094 | `tests/unit/test_split_hop_retirement_native.py`: the real disable tasks remove the ingress table, the fwmark rule and the maximum-metric unreachable route, and they leave foreign state in place. Staging is pending. | local passed |
