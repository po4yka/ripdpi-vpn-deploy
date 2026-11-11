---
task_id: ANS-1794396376228431
change: ans-1794396376228431-awg-split-family-uplinks
commit_sha: null
local: passed
local_evidence: "On base 6aa18fe9: tests/unit/test_awg_dualstack.py and test_firewall_egress_policy.py (138 passed; the split render and eth1 admission cases fail without the change), make snapshot-check (187 templates unchanged), nft -c on Ubuntu 24.04 for single, split and split-with-NAT-port-range rulesets, ansible-lint on roles/firewall and roles/amneziawg, check-secrets-coverage. The wider AWG/firewall unit selection has the same 17 Linux-only native failures on macOS as clean main."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending the staging Node A dry-run with firewall_awg_uplink6_interface eth1 under ANS-1794231660855533.
staging: required
staging_evidence: "Read-only: the patched scripts/awg_uplink.py on the UpCloud staging Node A refused --interface eth0 alone and admitted --interface eth0 --interface6 eth1 (networkd-owned RA). Deployment pending under ANS-1794231660855533."
live: not_applicable
live_evidence: No production host sets the new variable in this change.
client: not_applicable
client_evidence: AWG client traffic through the staging pair is evidence for ANS-1794231660855533.
artifact: not_applicable
artifact_evidence: No released artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ASU-ADMISSION | ANS-1794397013800385 | `tests/unit/test_awg_dualstack.py::test_separate_ipv6_uplink_is_admitted_only_when_named` and `::test_uplink_names_are_admitted_without_firewall_role_defaults`; read-only run on staging Node A | Passed |
| REQ-ASU-FORWARD | ANS-1794397013800385 | `tests/unit/test_firewall_egress_policy.py::test_awg_separate_ipv6_uplink_pins_each_family_to_its_interface` and `::test_awg_separate_ipv6_uplink_keeps_the_provider_nat_port_range_per_family`; `nft -c` | Passed |
| REQ-ASU-COMPAT | ANS-1794397013800385 | `make snapshot-check`; `tests/unit/test_firewall_egress_policy.py::test_split_hop_family_scope_keeps_both_families_on_the_tunnel` | Passed |
