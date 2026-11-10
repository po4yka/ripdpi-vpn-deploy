# Design: split-hop staging cohort profiles

## Context

`scripts/deploy-controller.py` resolves the effective `vpn` map from `all`, `vpn` and the host's cohort files, then the host's inventory metadata, then operator overrides. `scripts/validate-ansible-extra-vars.py` limits overrides to a narrow non-secret allowlist without `vpn`. Inventory metadata carries no `vpn` map. A tracked cohort is therefore the only supported per-host source. The disposable onboarding intent (`scripts/disposable_promotion.py`) requires the host's cohort membership to be exactly `vpn-device-full-staging`.

## Decisions

- Three profiles instead of one profile with an operator toggle: each staging step (B egress, A ingress, A family scope) is a reviewed, git-visible configuration, as the research tier requires.
- Node A profiles copy the full `device-full-staging` map. The deployment controller replaces maps, so a partial map would silently turn transports off; the contract test pins the copy.
- Node B keeps Tailnet management and turns transport egress and geodata off: it has no recipient transport that needs them.
- Names describe the configuration (`split-hop-egress`, `split-hop-ingress`, `split-hop-family-egress`) and the `-staging` scope, consistent with `device-full-staging`.
- Fresh Node A sequence: first deploy on `device-full-staging` with the disposable intent, which onboards the four-profile sentinel; then re-render with `split-hop-ingress-staging` and deploy with the promotion config that the first deploy produced; then `split-hop-family-egress-staging`.

## Alternatives rejected

- Allow `vpn` in `ANSIBLE_EXTRA_VARS_FILE`: it would let an untracked file enable research roles and change any toggle on any host, which the narrow override contract exists to prevent.
- Add research roles to `device-full-staging`: it is a family profile; `check-deploy-profile.py` forbids research roles there.
- Read `host_vars` in the controller: a second per-host source with different precedence than Ansible's would need its own review and still leave research enablement outside the reviewed cohort files.

## Rollback

Delete the three files and revert the guide. No role behaviour changes, so hosts in other cohorts are unaffected.
