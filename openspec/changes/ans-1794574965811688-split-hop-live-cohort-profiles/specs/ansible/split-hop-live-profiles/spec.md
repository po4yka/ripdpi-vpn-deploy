## ADDED Requirements

### Requirement: REQ-SHL-EGRESS — Live Node B publishes no client listener

The repository MUST ship a non-family cohort `vpn-split-hop-egress-live` whose content equals `vpn-split-hop-egress-staging`, so every client transport stays off and `allow_research_roles` lists exactly `split-hop-egress`.

#### Scenario: Live Node B drifts from the listener-free staging map

- **WHEN** the live or the staging Node B profile changes independently
- **THEN** the profile contract test fails.

### Requirement: REQ-SHL-INGRESS — Live Node A keeps production device transports and recovery

The repository MUST ship non-family cohorts `vpn-split-hop-ingress-live` and `vpn-split-hop-family-egress-live` whose complete `vpn` maps equal the `all.yml` map overlaid with `vpn-device-full-tailnet`, with monitoring, watchdog and backup enabled. Both MUST enable `enable_split_hop_ingress`, only the family profile MUST enable `split_hop_family_egress`, and both MUST list exactly `split-hop-ingress` in `allow_research_roles`.

#### Scenario: Live Node A drifts from the device profile

- **WHEN** a live Node A profile disables backup, monitoring or watchdog, or changes a transport toggle independently of `vpn-device-full-tailnet`
- **THEN** the profile contract test fails.

### Requirement: REQ-SHL-ADMISSION — Research gates still apply

The live cohorts MUST NOT be family profiles, and every family profile MUST remain free of research roles.

#### Scenario: Profile gate

- **WHEN** `scripts/check-deploy-profile.py` runs on the tree
- **THEN** it passes with the three live cohorts outside `family_profiles`.
