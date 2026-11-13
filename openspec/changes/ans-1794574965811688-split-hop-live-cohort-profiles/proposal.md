# Change: Add long-lived split-hop cohorts for a live research pair

Task ID: `ANS-1794574965811688`

## Why

Split-hop family egress (ANS-1794231660855533) passed staging, but its live and client acceptance needs a long-lived pair that serves a real device. The only split-hop cohorts are disposable staging profiles: Node A keeps monitoring, watchdog and backup off and inherits the staging transports. Split-hop roles are RESEARCH tier, so they cannot enter a family profile, and the deployment controller reads the `vpn` map only from tracked `group_vars`.

## What Changes

- New non-family cohort `vpn-split-hop-egress-live`: the same map and research allowlist as the staging Node B, so it keeps the `no-public-listener` SSH promotion kind.
- New non-family cohort `vpn-split-hop-ingress-live`: the `all.yml` map with the `vpn-device-full-tailnet` transports, monitoring, watchdog, backup and Tailnet management, plus `enable_split_hop_ingress`, with the `split-hop-ingress` allowlist.
- New non-family cohort `vpn-split-hop-family-egress-live`: the live ingress profile plus `split_hop_family_egress: true`.
- The deploy-profile reference and the split-hop pilot guide name the live cohorts and the `awg_ipv6: ipv4-only` liveness policy for a family Node A.

## Capabilities

### New Capabilities

- `ansible/split-hop-live-profiles`: tracked cohort profiles for a long-lived split-hop research pair.

### Modified Capabilities

- None.

## Impact

- Ansible: three new `group_vars` files; no role, template or default changes. Family profiles stay free of research roles.
- Tests: contract tests pin both live Node A profiles to `all.yml` plus `vpn-device-full-tailnet` and the live Node B to the staging Node B; the reviewed Tailnet profile list adds the three files.
- Docs: `docs/reference/deploy-profiles.md`, `docs/how-to/split-hop-pilot.md`.
- No Terraform, secrets schema, vpnd or client contract change. Provisioning, the live deploy and the device check stay separately authorized operator work under ANS-1794231660855533.
