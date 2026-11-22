# Change: Add a disposable staging profile for the p2-udp transports

Task ID: `ANS-1795351855549662`

## Why

`ANS-1795259263103243` needs a dry-run of a `vpn-p2-udp` node, because only that profile sets `hysteria_masquerade_tcp` and leaves Hysteria as the sole TCP/443 owner. The deployment controller resolves the `vpn` map only from tracked `ansible/group_vars/vpn-*.yml` cohort files, and `ANSIBLE_EXTRA_VARS_FILE` refuses the `vpn` key, so a staging node cannot turn roles off for one run. `vpn-p2-udp` enables monitoring, watchdog and backup. Its watchdog requires an operator-owned HTTPS canary and a `watchdog` Hysteria client, which disposable staging secrets do not carry, and monitoring and backup acceptance are not in the scope of a transport dry-run. Its committed `public_site_canonical_url` is a neutral placeholder that a staging run must replace. No staging profile has the p2-udp transport set.

## What Changes

- New family cohort `vpn-p2-udp-staging`: the exact `vpn-p2-udp` `vpn` map with `enable_monitoring`, `enable_watchdog` and `enable_backup` set to `false`; the same `hysteria_masquerade_tcp` and `hysteria_resource_profile_default`; and the generated disposable staging origin that `scripts/ci-bootstrap-secrets.sh` writes to `hysteria.masquerade_url`, as `vpn-device-full-staging` uses.
- `ansible/role-tiers.yml` lists the profile under `family_profiles`, so research and exception roles stay forbidden in it.
- The deploy profile reference and the Ansible folder note name the profile, its listener contract and its dry-run inputs.

## Capabilities

### New Capabilities

- `ansible/p2-udp-staging-profile`: a tracked cohort profile that dry-runs the p2-udp transport set on a disposable staging node with staging secrets only.

### Modified Capabilities

- None.

## Impact

- Ansible: one new `group_vars` file and one `family_profiles` entry; no role, template, default or production profile change. `vpn-p2-udp` and its monitoring, watchdog and backup requirements are unchanged.
- Tests: the profile guard test pins the new map to `vpn-p2-udp` with the three roles off; the listener contract, Tailnet profile set, neutral origin and staging origin tests include the new file.
- Docs: `docs/reference/deploy-profiles.md`, `docs/reference/architecture.md`, `ansible/CLAUDE.md`.
- No Terraform, secrets schema, validator, vpnd or client contract change. The disposable onboarding intent still admits only `device-full-staging`, so this profile covers dry-runs and deploys to an already onboarded node, not the first onboarding deploy.
