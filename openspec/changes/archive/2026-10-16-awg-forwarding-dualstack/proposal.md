## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

# Change: Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU

Task ID: `ANS-1791618048083304`

## Why

The single-instance firewall still forwards and masquerades only awg0 even when the supported role interface differs. Ordinary issued peers have one IPv4 identity while recipient configurations capture the IPv6 default route without provisioning or authorizing an IPv6 source. Independent fixed MTU values prevent an explicit constrained-path configuration.

Audit coverage: A10, A21; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Use effective instance names for forwarding, uplink-scoped NAT comments, verification contracts and positive data-plane coverage.
- Provision and authorize both IPv4 and IPv6 device identities and update server, encrypted peer schema, enrollment, bundle, standalone config, revocation and liveness consumers together.
- Introduce one validated per-instance or technical-profile MTU input with deterministic precedence shared by server, client output and liveness.
- Preserve default-drop forwarding, explicit uplink isolation, per-device revocation and the IPv6 kill switch while delivering actual IPv6 traffic.

## Capabilities

### New Capabilities

- `transports/awg-forwarding-dualstack`: deliver interface-correct dual-stack amneziawg forwarding and configurable mtu.

### Modified Capabilities

- None.

## Impact

- ansible/roles/firewall/templates/nftables.conf.j2
- ansible/roles/firewall/CLAUDE.md
- ansible/roles/amneziawg/templates/awg0.conf.j2
- ansible/roles/amneziawg/defaults/main.yml
- ansible/roles/amneziawg/tasks/instances.yml
- ansible/roles/amneziawg/CLAUDE.md
- secrets/schema.json
- scripts/validate-secrets.py
- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- contract/ripdpi-bundle.schema.json
- docs/RIPDPI-BUNDLE.md
- docs/AWG-COHORTS.md
- tests/unit/test_firewall_egress_policy.py
- tests/unit/test_real_vps_awg_nat_lane.py
- tests/unit/test_bundle_schema.py
- Source implementation, paired PRs and arm64 Android emulator acceptance are authorized; physical-device acceptance is excluded by owner request. Private-input mutation, provider action and deployment remain outside this change.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
