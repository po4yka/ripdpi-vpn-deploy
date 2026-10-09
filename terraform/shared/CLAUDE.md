# terraform/shared — provider-neutral inputs and cloud-init

## Design decisions

**Single cloud-init template** — `cloud-init.yaml.tftpl` is rendered by every
provider root with identical inputs. Behavior is consistent across providers
by construction.

**No secrets in here** — cloud-init creates the admin user, hardens sshd,
installs `python3`, drops a marker file at `/var/lib/cloud-init-vpn-bootstrap.done`,
and exits. The Ansible run handles the rest. Anything secret stays in SOPS.

**Bootstrap completion is fail-closed** — the first-boot command creates the runtime directory required by minimal images, validates the effective SSH configuration, reloads `ssh.service`, and creates the completion marker in one `&&` chain. A failed validation or reload must leave the marker absent so external waiters cannot advance to Ansible.

**Bootstrap SSH ownership is explicit** — `10-cloud-init-hardening.conf` starts with a managed ownership header and contains only the listener port plus the four first-boot authentication primitives. Runtime SSH policy belongs to the later controller transaction.

**Packaged image ownership is bounded** — bootstrap consumes the root-owned
mode-0644 `60-cloudimg-settings.conf` only with exact bytes
`PasswordAuthentication no\n`. Its removal shares the canonical publication
rollback and fsync boundaries. Modified content or metadata refuses before
writes; successful bootstrap leaves the canonical 10/20/50 layout.

**Disposable CI identity arrives on a separate disk** — UpCloud adds the public
`bootstrap-ssh-seed.py` installer to its cloud config only when a CI seed is set.
It mounts the UUID-bound disk read-only, validates the private key against its
public digest, and atomically installs it before the existing fail-closed SSH
bootstrap chain. Private key bytes never enter cloud-init or command arguments.
Image creation pins e2fsprogs 1.47.0 on Linux (1.47.4 for native macOS tests), uses
rootless `mke2fs -d`, and disables `orphan_file` for the supported guest kernels.
The filesystem utilities use the upstream GPL-2.0 license; no runtime Python
dependency or custom guest image is introduced.

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
  sources at boot. The template installs only what first-boot
  bootstrap needs (`python3`, `python3-apt`, `sudo`, `ca-certificates`, `curl`,
  `jq`); everything else is Ansible's job.
- **SSH host key regeneration is one-shot** — done by cloud-init on first
  boot. Don't re-run, or recipients pinning host keys will see a "MITM" warning.
- **Newer distro images socket-activate SSH** — `ssh.service` is inactive on
  first boot (Ubuntu 24.04 observed 2026-08), so a bare
  `systemctl reload ssh` in runcmd fails and the fail-closed marker never
  publishes. The bootstrap runs `systemctl enable --now ssh` before the
  reload; keep that ordering if you touch the chain.
