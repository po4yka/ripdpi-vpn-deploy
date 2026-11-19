## Context

`scripts/deploy-controller.py` runs every playbook through `transport_variables()`, which sets `ansible_ssh_args` from `multiplexed()`. `multiplexed()` starts from `fleet_inspection.ssh_command()`, whose strict options contain `ConnectTimeout=10` and `ConnectionAttempts=1` and no keepalive, and replaces only the three control options. This host variable overrides the `ssh_args` line of `ansible/ansible.cfg`, so its `ServerAliveInterval=15` never applies. Ansible's SSH connection plugin waits `2 + timeout` seconds for the become prompt; `timeout = 30` in `ansible.cfg` gives the observed 32 seconds.

## Goals / Non-Goals

Goals: a short stall of the operator channel does not fail a task; a route that is already bad is refused before any host change.

Non-goals: running the protected transaction on the node, retrying tasks, changing readiness or lockout proofs, and changing `ansible/ansible.cfg` for non-controller callers.

## Decisions

- Add the keepalive and connection-attempt options only in `multiplexed()`. The strict command stays the single-attempt, no-master proof that lockout and recovery logic depend on.
- `ServerAliveCountMax=8` with a 15-second interval lets the master survive about 120 seconds of silence before ssh exits, and the keepalive also keeps relay and NAT state alive during long quiet tasks.
- Set `ansible_ssh_timeout: 90` in `transport_variables()` so the value travels with the host and also covers the source-drift playbook. Ninety seconds stays below the master's keepalive limit, so a dead master is still reported by ssh first.
- No `ansible_ssh_retries`: Ansible retries on ssh exit 255, which also happens when a connection drops after the remote module started, and a second run of a protected-transaction task is not safe.
- The route gate uses `tailscale ping --until-direct=false --c 10 --timeout 5s <address>` through the controller's bounded `run_command`, with a 90-second process limit. Each reply line has the form `pong from <peer> (<address>) via <path> in <n>ms`; `via DERP(` marks a relayed route. A probe without a reply line counts as lost. The thresholds are fixed values: zero lost probes and a median of at most 400 ms, which admits the relayed routes that operators use today and refuses routes on which a 90-second prompt wait is likely to expire.
- Reply lines carry a millisecond-rounded Go duration (`180ms`, `1.234s`, `0s`), so the parser accepts both units. A route is reported as direct only when every reply came from an `address:port` endpoint; DERP and peer-relay paths are relayed. A non-zero CLI exit with ten replies counts as unmeasured.
- The gate runs in deploy mode only, after readiness and before the source recheck of each host, so a source change during the probe is still refused. Dry-run changes nothing, so it does not need the gate. In a multi-host deploy earlier hosts may already have converged when a later host is refused.
- The CI run (`DEPLOY_CI_TAILNET_HANDOFF`) is not gated: it talks to a private root-owned `tailscaled` socket, and its runner-to-node path is not the operator channel this change protects. A host-name transport is not resolved or measured; inventories use addresses today.
- The keepalive options also reach the other callers of `multiplexed()` and `transport_variables()` (`bootstrap-tailnet.py`, `device_lifecycle_io.py`, `device_migration_io.py`), which drive the same kind of shared-master Ansible run.

## Contracts and ownership

`scripts/deploy-controller.py` owns the options, the variable and the gate. `scripts/fleet_inspection.py` is unchanged. The refusal categories are part of the controller's operator-visible error contract and are documented in `docs/how-to/deploy.md`.

## Risks / Trade-offs

- A dead channel now fails a task after about 92 seconds instead of 32. The transaction outcome is the same; the failure only arrives later.
- Operators who deploy over Tailnet need the `tailscale` CLI on `PATH`; without it the deploy refuses. This is deliberate: an unmeasured route is the failure this change prevents.
- The gate measures the route at one point in time; it cannot predict a later stall. The session options cover that case.

## Migration Plan

No data migration. The change applies to the next controller run. Rollback is a revert of the controller commit.
