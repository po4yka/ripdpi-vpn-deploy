# Change: Add split-hop staging cohort profiles for Node A and Node B

Task ID: `ANS-1794322927427537`

## Why

The split-hop pilot guide tells the operator to enable `split-hop-egress` on Node B and `split-hop-ingress` (later `split_hop_family_egress`) on Node A through host vars. The deployment controller cannot apply that configuration: it resolves the per-host `vpn` map only from tracked `ansible/group_vars/vpn-*.yml` cohort files, it does not read `host_vars`, and `ANSIBLE_EXTRA_VARS_FILE` refuses the `vpn` and `allow_research_roles` keys. The only full-transport disposable staging cohort, `device-full-staging`, is a family profile, so research roles are forbidden in it. No supported input can therefore stage the split-hop pair that `ANS-1794231660855533` requires.

## What Changes

- New non-family cohort `vpn-split-hop-egress-staging`: Node B with `enable_split_hop_egress` and every client transport, transport egress and geodata explicitly off, with the `split-hop-egress` research allowlist in the same file. It satisfies the `no-public-listener` SSH promotion kind.
- New non-family cohort `vpn-split-hop-ingress-staging`: the exact `device-full-staging` map plus `enable_split_hop_ingress`, with the `split-hop-ingress` allowlist.
- New non-family cohort `vpn-split-hop-family-egress-staging`: the ingress profile plus `split_hop_family_egress: true`.
- The split-hop pilot guide names these cohorts, states that host vars and extra vars cannot carry the `vpn` map, and states that a fresh Node A first deploys on `device-full-staging` because the disposable onboarding intent admits only that cohort.

## Capabilities

### New Capabilities

- `ansible/split-hop-staging-profiles`: tracked cohort profiles that stage both split-hop nodes through the canonical deployment controller.

### Modified Capabilities

- None.

## Impact

- Ansible: three new `group_vars` files; no role, template or default changes. Family profiles are unchanged.
- Tests: the no-listener promotion test admits the shipped Node B profile; a new test pins Node A profiles to `device-full-staging`; the reviewed Tailnet profile list adds the three files.
- Docs: `docs/how-to/split-hop-pilot.md`, `docs/reference/deploy-profiles.md`.
- No Terraform, secrets schema, vpnd or client contract change. A production split-hop profile is out of scope; it needs its own reviewed cohort before any live family use.
