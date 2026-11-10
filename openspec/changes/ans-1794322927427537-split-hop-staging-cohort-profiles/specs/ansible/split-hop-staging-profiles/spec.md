## ADDED Requirements

### Requirement: REQ-SHS-EGRESS — Node B staging cohort publishes no client listener

The repository MUST ship a non-family cohort `vpn-split-hop-egress-staging` whose complete `vpn` map enables `enable_split_hop_egress`, sets `enable_xray_reality`, `enable_nginx_xhttp`, `enable_hysteria` and `enable_amneziawg` explicitly to `false`, and whose `allow_research_roles` lists exactly `split-hop-egress`.

#### Scenario: No-listener promotion admits the shipped profile

- **WHEN** a host in this cohort has an empty provider listener contract and a `no-public-listener` promotion entry
- **THEN** the deployment controller admits the entry and proceeds to SSH without the sentinel proof validator.

### Requirement: REQ-SHS-INGRESS — Node A staging cohorts keep the staging transports

The repository MUST ship non-family cohorts `vpn-split-hop-ingress-staging` and `vpn-split-hop-family-egress-staging` whose `vpn` maps equal the `device-full-staging` map except that both enable `enable_split_hop_ingress` and only the family profile enables `split_hop_family_egress`. Both MUST list exactly `split-hop-ingress` in `allow_research_roles`.

#### Scenario: Profile drift from the staging transports

- **WHEN** `device-full-staging` or either Node A profile changes a transport toggle independently
- **THEN** the profile contract test fails.

### Requirement: REQ-SHS-ADMISSION — Research gates still apply

The new cohorts MUST NOT be family profiles, and every family profile MUST remain free of research roles.

#### Scenario: Profile gate

- **WHEN** `scripts/check-deploy-profile.py` runs on the tree
- **THEN** it passes with the three cohorts outside `family_profiles`.
