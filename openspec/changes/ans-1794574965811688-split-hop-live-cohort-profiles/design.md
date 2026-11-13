# Design: long-lived split-hop cohorts

## Context

The deployment controller resolves the per-host `vpn` map only from tracked `group_vars`, and split-hop roles are RESEARCH tier, so a live pair needs its own non-family cohorts. Staging proved the topology with disposable cohorts that turn monitoring, watchdog and backup off.

## Decisions

- **Node A base.** The live Node A uses `all.yml` overlaid with `vpn-device-full-tailnet`, the production device profile managed over the Tailnet, because the pair serves a real device and must stay recoverable and observable. Each file carries the complete `vpn` map in the key order of the staging cohorts, because the controller replaces canonical maps.
- **Node B base.** The live Node B reuses the staging Node B map unchanged. Monitoring stays off on Node B so that it publishes no listener; Node A's watchdog and transport canary traverse the tunnel and alert on a Node B outage.
- **Liveness.** A family Node A refuses device IPv6 by design, so its liveness policy sets `awg_ipv6: ipv4-only` (ANS-1794231660855533, REQ-SHF-LIVENESS). A fresh live node proves itself from an independent cloud sentinel through `cloud-promotion-intent`, not from an operator workstation.

## Risks

- Node B is a single point of failure for Node A's family traffic by design (fail-closed). The live pair carries only research devices.
- A family Node A still advertises IPv6 to AWG clients; clients fall back to IPv4 after the refusal.
