# terraform/shared — provider-neutral inputs and cloud-init

## Design decisions

**SSH bootstrap owns only Port and auth primitives** — tunable hardening and
algorithm lists belong to baseline's 20- drop-in. Never duplicate its keys in
10-: baseline rejects overlaps, including legacy X11Forwarding on old nodes.

**Single cloud-init template** — `cloud-init.yaml.tftpl` is rendered by every
provider root with identical inputs. Behavior is consistent across providers
by construction.

**No secrets in here** — cloud-init creates the admin user, hardens sshd,
installs `python3`, drops a marker file at `/var/lib/cloud-init-vpn-bootstrap.done`,
and exits. The Ansible run handles the rest. Anything secret stays in SOPS.

**Bootstrap completion is fail-closed** — the first-boot command creates the runtime directory required by minimal images, validates the effective SSH configuration, reloads `ssh.service`, and creates the completion marker in one `&&` chain. A failed validation or reload must leave the marker absent so external waiters cannot advance to Ansible.

## What's done well

- **Marker-based wait** — `scripts/wait-cloud-init.sh` treats the marker file as authoritative after cloud-init reaches a terminal state. This tolerates provider-image recoverable warnings while still failing when SSH validation or reload did not publish the marker.
- **Admin user is non-root** — root SSH is disabled by cloud-init in the
  same boot; the Ansible inventory connects as the admin user with sudo.

## Pitfalls

- **Cloud-init `user_data` is plaintext in TF state** — never put secrets
  here. Even with state encryption, this is operator-readable.
- **`runcmd:` runs every boot if not gated** — guard with a marker check or
  cloud-init's `once-per-instance` semantics.
- **`packages:` is provider-quirky** — some providers' images strip apt
  sources at boot. The template installs only the bare minimum
  (`python3`, `sudo`); everything else is Ansible's job.
- **SSH host key regeneration is one-shot** — done by cloud-init on first
  boot. Don't re-run, or recipients pinning host keys will see a "MITM" warning.
- **Newer distro images socket-activate SSH** — `ssh.service` is inactive on
  first boot (Ubuntu 24.04 observed 2026-08), so a bare
  `systemctl reload ssh` in runcmd fails and the fail-closed marker never
  publishes. The bootstrap runs `systemctl enable --now ssh` before the
  reload; keep that ordering if you touch the chain.
