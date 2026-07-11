# terraform/shared — provider-neutral inputs and cloud-init

## Design decisions

**Single cloud-init template** — `cloud-init.yaml.tftpl` is rendered by every
provider root with identical inputs. Behavior is consistent across providers
by construction.

**No secrets in here** — cloud-init creates the admin user, hardens sshd,
installs `python3`, drops a marker file at `/var/lib/cloud-init-vpn-bootstrap.done`,
and exits. The Ansible run handles the rest. Anything secret stays in SOPS.

**Bootstrap completion is fail-closed** — the first-boot command validates the effective SSH configuration, reloads `ssh.service`, and creates the completion marker in one `&&` chain. A failed validation or reload must leave the marker absent so external waiters cannot advance to Ansible.

## What's done well

- **Marker-based wait** — `scripts/wait-cloud-init.sh` polls for the marker file, not an arbitrary sleep. The marker is published only after SSH validation and reload succeed.
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
