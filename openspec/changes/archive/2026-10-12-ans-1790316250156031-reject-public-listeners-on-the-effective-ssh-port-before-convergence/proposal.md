# Change: Reject public listeners on the effective SSH port before convergence

Task ID: `ANS-1790316250156031`

## Why

Nothing prevents an enabled public listener from sharing the effective SSH port. The honeypot binds `honeypot.port` (default `honeypot_port: 4443`) and is meant to look like SSH, so an operator can plausibly set it to the port sshd actually uses. `scripts/check-listener-collisions.py` compares public listeners only with each other, the runtime listener manifest does not carry the SSH port, and the firewall role never compares the two. The failure is silent and security-relevant: the firewall's public-listener-contract loop renders an unrestricted `tcp dport <ssh> accept`, which accepts SSH from sources outside `allowed_ssh_cidrs`, while the listener itself either fails to bind or races sshd for the port. The honeypot role's documentation currently records the gap as "Nothing checks this automatically".

## What Changes

- Firewall convergence fails closed, before the rendered nftables ruleset is installed and before any listener role runs, when any TCP entry of the public listener contract (exact port or port range) covers the effective SSH port derived from `sshd -T`.
- The failure names the colliding contract listeners and the SSH port. It cannot be suppressed by `listener_collision_allowlist`, because the collision always opens SSH beyond its source restriction.
- UDP listeners on the SSH port number stay allowed.

## Capabilities

### New Capabilities

- `ansible/ssh-port-reservation`: the effective SSH port is reserved from the public listener contract at firewall convergence.

### Modified Capabilities

- None

## Impact

- Ansible layer only: `ansible/roles/firewall/tasks/main.yml` gains one assert that runs for `site.yml`, direct firewall role runs, and check-mode dry runs.
- Operator-visible: a deploy whose public listener contract covers the SSH port now aborts at the firewall role instead of converging with world-open SSH. No correctly configured deploy changes behavior.
- No Terraform, secrets schema, listener manifest, or `vpnd` contract changes.
