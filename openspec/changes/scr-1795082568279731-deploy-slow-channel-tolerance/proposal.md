# Change: Tolerate a slow operator channel during deploy

Task ID: `SCR-1795082568279731`

## Why

On 2026-11-19 a production deploy of one node failed with `Timeout (32s) waiting for privilege escalation prompt` on a task inside the protected block. The management path was a relayed Tailnet route with a round-trip time of 130–260 ms. The failure came after protected ingress capture, so the next deploy had to run the `interrupted-protected-ingress-transaction` compensation and stop, and the operator then had to repeat dry-run and deploy. One short stall of the operator channel cost a complete extra transaction cycle.

The controller replaces the `ssh_args` of `ansible/ansible.cfg` with the strict options of `scripts/fleet_inspection.py`. The shared run-owned SSH master therefore has no keepalive, makes one connection attempt only, and Ansible waits only 32 seconds (its 30-second connection timeout plus 2) for the sudo prompt. The controller also starts a mutating deploy on a route whose quality it never measures.

## What Changes

- The run-owned SSH master that Ansible tasks share sends keepalives (`ServerAliveInterval=15`, `ServerAliveCountMax=8`) and makes up to three connection attempts. Readiness, recovery and every fresh SSH lockout proof keep the unchanged strict command.
- Ansible tasks in a controller run wait 90 seconds for the privilege-escalation prompt instead of 32 seconds.
- Ansible SSH retries stay disabled, because a retry after a lost connection can run a non-idempotent protected-transaction task a second time.
- Before a mutating deploy of a host whose management transport is a Tailnet address, the controller measures the route with `tailscale ping` and refuses with a categorical error when a probe is lost, when the median round-trip time is above 400 ms, or when it cannot measure the route. It reports whether the route is direct or relayed and prints no address. Dry-run and non-Tailnet transports are not gated.

## Capabilities

### New Capabilities

- `operations/deployment-channel-tolerance`: SSH session tolerance and the pre-mutation management-route gate of the deploy controller.

### Modified Capabilities

- None.

## Impact

- `scripts/deploy-controller.py` and `tests/unit/test_deploy_controller.py`.
- `docs/how-to/deploy.md` documents the gate, its refusal categories and the new timeouts.
- Operator workstations that deploy over Tailnet need the `tailscale` CLI on `PATH`. A deploy over a route that fails the gate now refuses before any host change instead of failing during the transaction.
- No Terraform, cloud-init, Ansible role, secrets schema or client contract changes.
