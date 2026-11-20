---
task_id: ANS-1795163654691828
change: ans-1795163654691828-udp-node-audit-hardening
commit_sha: null
local: required
local_evidence: "On base 5f82a695, 2026-11-20: the 69 unit test files that cover the changed areas plus tests/unit/test_udp_node_audit.py, 2177 passed; 2 failed for local reasons and not from this change (test_ci_real_deploy needs github.com, which was unreachable; test_ssh_listener_verification timing test passes alone). make snapshot-check exit 0 (189 templates). ansible-lint on the three changed task files exit 0. taskctl validate exit 0. nft 1.1.3 parsed a rendered ruleset with the new rules with no syntax error. Not run locally: make check, the full unit suite and Molecule, because six parallel sessions held the workstation at a load average near 360."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending the provider listener contract update and a per-node dry-run under operator authorization.
staging: not_applicable
staging_evidence: No staging-only path; Molecule in CI and the per-node dry-run cover the host changes.
live: required
live_evidence: Pending deployment of the UDP node under operator authorization, then TCP/443 and UDP/443 probes, the connection tracking maximum and the forward-chain rules read back.
client: required
client_evidence: Pending a redelivered AmneziaWG configuration with MTU 1280 and one device that keeps MTU 1420.
artifact: not_applicable
artifact_evidence: No built or published artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-HY-TCP-MASQUERADE | ANS-1795164676595975 | `tests/unit/test_udp_node_audit.py::test_masquerade_site_answers_tcp_only_where_the_profile_selects_it`, `::test_native_acme_keeps_tcp_80_for_its_challenge`, `::test_listener_manifest_names_the_masquerade_ports`; `tests/unit/test_listener_contract.py` | Passed locally; CI pending |
| REQ-HY-MASQUERADE-NO-SELF-ORIGIN | ANS-1795164676595975 | Role assert in `ansible/roles/hysteria/tasks/enable.yml`; Molecule `hysteria` in CI for the unchanged default path | Passed locally; CI pending |
| REQ-HY-CONGESTION-DEFAULT | ANS-1795164676595975 | `tests/unit/test_udp_node_audit.py::test_udp_profile_default_is_bbr_and_a_stated_profile_wins` | Passed locally; CI pending |
| REQ-CONNTRACK-BUDGET | ANS-1795164874348070 | `tests/unit/test_baseline_sysctl_recovery.py`; `make snapshot-check`; Molecule `baseline` in CI | Passed locally; CI pending |
| REQ-AWG-MSS-MTU | ANS-1795165069064981 | `tests/unit/test_udp_node_audit.py::test_forwarded_awg_tcp_is_clamped_to_the_instance_mtu_before_conntrack_accepts`, `::test_default_mtu_has_one_value_across_role_admission_and_firewall`; `tests/unit/test_awg_dualstack.py` | Passed locally; CI pending |
| REQ-DHCPV4-REPLY | ANS-1795165069064981 | `tests/unit/test_udp_node_audit.py::test_dhcpv4_reply_is_scoped_to_the_ipv4_uplink_before_conntrack`; `tests/unit/test_security_verify_listeners.py::test_scoped_dhcpv4_reply_is_not_a_public_listener`, `::test_other_udp_68_accepts_stay_refused` | Passed locally; CI pending |
| REQ-SPLIT-HOP-EGRESS-DEFAULTS | ANS-1795165219611950 | `tests/unit/test_udp_node_audit.py::test_split_hop_egress_follows_the_observed_uplink_and_the_ingress_port`, `::test_explicit_split_hop_interface_and_port_still_win` | Passed locally; CI pending |
| REQ-SPLIT-HOP-EGRESS-BOUNDARY | ANS-1795165219611950 | `tests/unit/test_udp_node_audit.py::test_split_hop_egress_refuses_private_destinations_before_its_forward_accept`; `make snapshot-check` for the loader unit | Passed locally; CI pending |
| REQ-AWG-UNIT-SANDBOX | ANS-1795165353614351 | `make snapshot-check`; Molecule `amneziawg` in CI | Passed locally; CI pending |
| REQ-AWG-PUBLISHED-SHAPE | ANS-1795165353614351 | `tests/unit/test_transport_semantics.py::test_production_refuses_the_published_port_and_value_set` and the generator tests | Passed locally; CI pending |
| REQ-COHORT-FINGERPRINT-INPUT | ANS-1795165353614351 | `tests/unit/test_bundle_schema.py::test_absent_wire_profile_is_the_contract_constant_and_other_gaps_refuse`, `::test_cohort_fingerprint_golden` | Passed locally; CI pending |
