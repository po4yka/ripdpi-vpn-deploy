# pyinfra read-only audit pilot

This directory is an experimental pyinfra pilot for observing deployed hosts. Ansible remains the source of truth for deployment, remediation, role ordering, templates, handlers, rollback, and transport configuration.

The pilot is intentionally limited to read-only commands. Do not port baseline, firewall, Xray, Hysteria, AmneziaWG, or other transport roles here without a separate design decision and review.

## Usage

Install pyinfra separately from the normal Ansible requirements, then pass explicit hosts:

```sh
PYINFRA_HOSTS=203.0.113.10 PYINFRA_SSH_USER=admin PYINFRA_SSH_KEY=~/.ssh/vpn_deploy make pyinfra-audit
```

Multiple hosts are comma-separated:

```sh
PYINFRA_HOSTS=203.0.113.10,203.0.113.11 make pyinfra-audit
```

`PYINFRA_SSH_PORT` is optional when a non-default SSH port is required.

## Inventory limitation

The existing `scripts/render-inventory.sh` target writes `ansible/inventory/generated.ini` for Ansible and relies on Ansible group vars, host vars, and playbook conventions. This pilot does not parse or merge that inventory yet. Use `PYINFRA_HOSTS` until there is a deliberate converter that preserves the Ansible inventory contract without making pyinfra part of the deployment flow.

## Current checks

- hostname and OS release;
- effective `sshd -T` values for security-relevant settings;
- `nft -c -f /etc/nftables.conf` syntax result;
- presence and JSON validity of `/var/lib/ripdpi-vpn-deploy/manifest.json`;
- `systemctl is-active` status for known services and timers.
