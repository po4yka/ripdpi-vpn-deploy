# SEC-1794029167060487: Harden server configuration from rollout lessons

## Objective

Rollouts reproduce from source without hand-set monitoring flags or out-of-repo firewall rules, and operator failures name their cause.

## Ownership

- `ansible/roles/observability_agent/`, `ansible/roles/observability_control_plane/` alert rules, `contract/observability-metric-manifest.example.json`, `scripts/tailnet_firewall.py`, `scripts/tailnet_management.py`, `scripts/tailnet-configure.py`, `scripts/bootstrap-tailnet.py`, `scripts/observability-operator.py`, `scripts/fleet-maintenance.py`, `scripts/deploy-controller.py`, their tests and docs, `AGENTS.md`.

## Execution

- [ ] SEC-1794030485989065 Derive the self-steal certificate series from the host and alert on a missing series #bug @item:SEC-1794029167060487
- [ ] SEC-1794031569118515 Render observer private ingress and Kuma Telegram egress in the Tailnet foundation #bug @item:SEC-1794029167060487
- [ ] SEC-1794032178100678 Record failing task names and type busy-lock and missing-inventory refusals #bug @item:SEC-1794029167060487
- [ ] SEC-1794032683487075 Align the kit access rule and record rollout operating notes #bug @item:SEC-1794029167060487

## Verification

- Focused unit, promtool, snapshot and lint checks; remote CI. The agent change reaches nodes with the next monitoring rollout; the observer foundation input applies when the observer is recreated or its foundation is reapplied.
