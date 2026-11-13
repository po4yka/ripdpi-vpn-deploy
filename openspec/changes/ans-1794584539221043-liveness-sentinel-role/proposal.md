# Change: Prepare a cloud liveness sentinel through an Ansible role

Task ID: `ANS-1794584539221043`

## Why

A fresh live node can only use `cloud-promotion-intent` with an independent cloud sentinel, and that sentinel needs pinned sing-box, Xray and the immutable AWG client toolchain. An earlier SSH installer was rejected: it installed packages outside Ansible, replaced the `xray-runtime` public symlink, changed the node before verifying digests, left unverified binaries installed, staged files in a world-writable path and upgraded unrelated packages. Ansible owns runtime state, so the preparation belongs in a role.

## What Changes

- New research-tier role `liveness-sentinel`, gated by `vpn.enable_liveness_sentinel` (default false), that installs the pinned engines into `/opt/ripdpi-liveness-sentinel/bin` after digest and version verification, installs the AWG toolchain through the existing offline installer, verifies `ip`, `curl` and `python3`, and publishes `expected-runtime.json`.
- New `contract/liveness-runtime-pins.json`, the single source for engine versions and digests; the disposable executor provisioner reads it instead of literals.
- `scripts/vpn-protocol-liveness.py` prefers engines in the role prefix and falls back to PATH.
- The live split-hop Node B enables the toggle and allowlists the role; every complete `vpn` map gains the key.
- Docs for sentinel onboarding, the cloud-sentinel deploy paragraph and the live Node B row.

## Capabilities

### New Capabilities

- `ansible/liveness-sentinel-role`: pinned probe engines for a cloud protocol-liveness sentinel.

### Modified Capabilities

- `ansible/split-hop-live-profiles`: the live Node B now differs from the staging Node B by exactly the sentinel toggle and its allowlist entry.

## Impact

- Ansible: one role, one toggle, one `site.yml` import, nine `group_vars` files with the new key.
- Scripts: provisioner pin loading and the probe engine lookup; behaviour and result shape of the disposable flow are unchanged.
- No Terraform, secrets schema, vpnd or client contract change. Converging the live Node B, building AWG bundles and fetching the pins stay separately authorized operator work.
