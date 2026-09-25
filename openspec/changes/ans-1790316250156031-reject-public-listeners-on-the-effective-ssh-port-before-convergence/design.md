## Context

`site.yml` renders the runtime listener manifest, rejects listener-vs-listener collisions with `scripts/check-listener-collisions.py`, and proves the manifest equals Terraform's `public_listener_contract`, all in controller-side pre_tasks. The effective SSH port is host state: the firewall role, `security-verify.yml`, and `verify.yml` all derive it from `sshd -T`, and `ansible_port` is only the controller's transport port, which operator overrides can point at a tunnel. See proposal.md for motivation.

## Goals / Non-Goals

- Goal: fail closed whenever a TCP public listener would claim the effective SSH port, before nftables or any listener role changes the host.
- Goal: cover the honeypot and every other contract listener with one check, including exact ports and port ranges.
- Non-goal: reserving other operator ports, changing the listener manifest or Terraform contract, or adding an allowlist escape hatch.

## Decisions

- Place the check in the firewall role, directly after "Require one effective SSH listener port". That is where the verified contract and the `sshd -T` port first meet, and the firewall's contract loop is what would open SSH to the world. It runs for `site.yml` (tagged `always`), for direct role runs, and in check mode, before any transport or honeypot role.
- Rejected: extending `check-listener-collisions.py` with an `ssh_ports` input fed by an `sshd -T` pre-task. The pre-task would run before `baseline` installs `openssh-server`, which the Molecule images do not ship, and feeding it `ansible_port` would trust a transport override instead of effective sshd state.
- Rejected: adding SSH to the runtime listener manifest. SSH is not part of Terraform's public listener contract, so `check-listener-contract.py` would reject the manifest.
- The check is not allowlistable: an allowlisted collision would still render a world-open accept on the SSH port.

## Contracts and ownership

- `ansible/roles/firewall/tasks/main.yml`: one assert consuming `public_listener_contract` and `firewall_effective_ssh_ports`.
- `tests/unit/test_firewall_ssh_port_reservation.py`: evaluates the real task with the pinned ansible-core templar.
- `ansible/roles/firewall/CLAUDE.md`, `ansible/roles/honeypot/CLAUDE.md`: knowledge-layer updates.
- No Terraform, secrets, `vpnd`, or manifest contract changes.

## Risks / Trade-offs

- The check runs after `baseline`, not in pre_tasks. Baseline changes nothing a colliding listener depends on, and the check still runs before nftables and every listener role, which is where the exposure would happen.
- The assert mirrors the template's target precedence (`port` when set, otherwise `port_range`), so an entry that sets both is judged by the port the rule actually opens. An entry with neither raises a template error instead of passing. `check-listener-contract.py` in `site.yml` and Terraform variable validation already reject both shapes; the mirror matters for direct role runs.

## Migration Plan

Forward: no migration. A deploy that currently opens SSH through a colliding listener stops at the firewall role until the operator moves the listener off the SSH port. Rollback: revert the commit; the check leaves no host state behind. Gates: the targeted unit tests, `make ci-fast`, and protected-main CI including the firewall Molecule and full-stack scenarios.
