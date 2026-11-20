# ANS-1795163654691828: Close UDP transport, firewall and split-hop gaps from the fleet audit

## Objective

A UDP transport node and a split-hop egress node converge to the properties in `network/udp-node-transport-hardening`.

## Ownership

`ansible/roles/{hysteria,amneziawg,firewall,baseline,split-hop-egress}/`, `ansible/group_vars/vpn-p2-udp.yml` (not `enable_watchdog`), `ansible/templates/listener-manifest.json.j2` (Hysteria entries), `scripts/transport_semantics.py`, `scripts/ripdpi_cohort_fingerprint.py`, `scripts/verify-public-listeners.py` (DHCPv4 rule), `scripts/observability-contract.py` (one listener name), their unit tests and snapshots, `docs/reference/deploy-profiles.md` and `docs/reference/awg-cohorts.md`. One writer; the nftables and sysctl templates have no other writer in the parallel audit sessions.

## Execution

- [x] ANS-1795164676595975 Serve the Hysteria masquerade over TCP and set the BBR default for vpn-p2-udp with render and manifest tests #bug !high @item:ANS-1795163654691828
- [x] ANS-1795164874348070 Set the connection tracking budget and file-max in the baseline sysctl policy with render tests #bug !high @item:ANS-1795163654691828
- [x] ANS-1795165069064981 Clamp forwarded AmneziaWG TCP, lower the MTU default to 1280 and accept scoped DHCPv4 replies with render and verifier tests #bug !high @item:ANS-1795163654691828
- [x] ANS-1795165219611950 Resolve split-hop egress uplink and peer port, add its destination boundary and sandbox its policy loader with render tests #bug !high @item:ANS-1795163654691828
- [x] ANS-1795165353614351 Sandbox awg-quick, refuse the partial published AmneziaWG shape and complete the cohort fingerprint input check with unit tests #bug !high @item:ANS-1795163654691828
- [ ] ANS-1795165481080593 Run the narrow checks, Molecule where available and make check, then record evidence in verification.md #bug !high @item:ANS-1795163654691828

## Verification

Local: `tests/unit/test_udp_node_audit.py` and the changed unit test files, `make snapshot-check`, `make molecule-test` for the changed roles where Docker allows, `make check`. Remote CI: the pull request checks. Dry run and live: provider contract update, `make dry-run` and deployment per node under separate operator authorization. Client: redelivered AmneziaWG configurations carry the new MTU. Staging and artifact gates do not apply.
