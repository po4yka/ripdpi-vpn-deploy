## ADDED Requirements

### Requirement: REQ-P2S-PROFILE — The staging cohort keeps the p2-udp transport set

The repository MUST ship a family cohort `vpn-p2-udp-staging` whose `vpn` map equals the `vpn-p2-udp` map except that `enable_monitoring`, `enable_watchdog` and `enable_backup` are `false`, and whose `hysteria_masquerade_tcp` and `hysteria_resource_profile_default` equal the `vpn-p2-udp` values.

#### Scenario: Profile drift from the p2-udp transports

- **WHEN** `vpn-p2-udp` or `vpn-p2-udp-staging` changes a transport toggle or a Hysteria setting independently
- **THEN** the profile contract test fails.

#### Scenario: Same listener surface

- **WHEN** the listener manifest renders for `vpn-p2-udp-staging`
- **THEN** it equals the `vpn-p2-udp` manifest: Hysteria and AmneziaWG on UDP, and `hysteria-masquerade` on TCP/80 and TCP/443.

### Requirement: REQ-P2S-SECRETS — Staging secrets are sufficient

The profile MUST derive `public_site_canonical_url` from the generated staging frontend identity that `scripts/ci-bootstrap-secrets.sh` writes to `hysteria.masquerade_url`, and MUST NOT enable a role that needs monitoring, watchdog or backup credentials.

#### Scenario: Generated origin

- **WHEN** the profile origin renders with the staging `nginx_xhttp.server_name` and public port 8443 or 443
- **THEN** it equals the origin that the staging secrets generator writes for that port.

### Requirement: REQ-P2S-ADMISSION — Family gates still apply

The profile MUST be listed in `family_profiles`, and production validation for `vpn-p2-udp` MUST stay unchanged.

#### Scenario: Profile gate

- **WHEN** `scripts/check-deploy-profile.py` runs on the tree
- **THEN** it passes with `vpn-p2-udp-staging` inside `family_profiles` and no research or exception role enabled.
