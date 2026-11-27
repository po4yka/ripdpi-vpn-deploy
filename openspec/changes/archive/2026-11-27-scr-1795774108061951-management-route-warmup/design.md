## Context

`scripts/deploy-controller.py` runs, for each selected host, `wait_for_bootstrap` (a strict `ssh ... true` with a 15 s budget), the recovery foundation check and then, for `deploy` only, `require_management_route` (ten `tailscale ping` probes, 5 s each). The playbooks then share one run-owned SSH master with `ServerAliveInterval=15` and `ServerAliveCountMax=8`. The research for `OPS-1795702284251279` found two failure shapes on the relayed route: a cold relay region at the start of a run (about 23 s to connect, longer than the 15 s readiness budget) and a reply gap of 96 to 117 s after each change of the operator's home relay region (close to the 120 s session budget).

## Goals / Non-Goals

- Goal: a preview or deploy over a usable relayed route survives a home-region change; a preview over an unusable route stops in seconds.
- Goal: the same route gate and session budget in both modes, so a preview predicts whether the deploy will hold.
- Non-goal: a direct Tailnet path. That needs inbound UDP to tailscaled on every node, which exposes plain WireGuard flows on the node address; the research rejects it under the active fingerprinting threat model.
- Non-goal: Ansible SSH retries. A retry after a lost connection can run a protected-transaction task twice in a deploy; check mode gains nothing it needs from them.

## Decisions

- Warm-up is a separate unmeasured probe (`tailscale ping --until-direct=false -c 1 --timeout 30s`). Counting it in the ten-probe measurement would turn every cold start into `management-route-lossy`. Rejected: lengthening the readiness budget, which waits on SSH instead of establishing the relay path, and is shared with bootstrap.
- The gate moves before `wait_for_bootstrap` and runs in both modes. A dry-run that would stall is cheaper to refuse at the start than after 20 minutes; the deploy still measures before the source recheck, as now.
- The silence budget is 300 s (`ServerAliveCountMax=20`) for both modes. The longest observed reply gap was about 117 s; 300 s covers a gap that ends only on the next netmap update. A longer session wait is safe in a deploy too: when the client gives up, the remote command loses its session in the middle of a task, which is worse than waiting. Rejected: a longer budget only in check mode, because the failure it avoids is the same in both modes and the deploy has more to lose.
- New refusal category `management-route-unreachable` for a warm-up without a reply, so an operator can tell "no path at all" from a lossy or slow path.

## Contracts and ownership

- `scripts/deploy-controller.py`: `require_management_route` (warm-up, both modes), its call site in the host loop, `multiplexed` (`ServerAliveCountMax`).
- `tests/unit/` controller tests that pin the gate, the SSH options and the mode split.
- `docs/how-to/deploy.md`: the refusal categories and that previews are gated.
- No Terraform root, Ansible role, secrets schema or vpnd surface changes.

## Risks / Trade-offs

- A dead node takes up to 300 s instead of 120 s to fail a running task → the deploy still fails closed, and the route gate refuses an unreachable node before the run starts.
- A preview now needs the `tailscale` CLI on the operator machine for Tailnet transports → the CI handoff run and public transports stay ungated, as for deploy.
- The 15 s readiness probe can still meet a home change that starts between the warm-up and the probe → the warm-up shortens that window to seconds; the readiness budget stays strict because bootstrap relies on it.

## Migration Plan

Forward: ship the controller change and tests; the next preview and deploy use it with no input change. Rollback: revert the commit; no state, schema or node change is involved. Before archiving either change, reconcile `REQ-OPS-CHANNEL-GATE` and `REQ-OPS-CHANNEL-SESSION` of `scr-1795082568279731-deploy-slow-channel-tolerance` with this change, so the main specification states one gate and one budget. Live gate: one timed preview of a production node over the relayed route that passes the warm-up and the measurement.
