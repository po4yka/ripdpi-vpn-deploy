# role: baseline — every host starts here

## Design decisions

**Sets ground state, not policy** — installs sysctl baseline, time sync
(`systemd-timesyncd`), SSH hardening drop-in, and IP-forwarding sysctl when
AmneziaWG is in scope. Doesn't open ports; doesn't install Xray/nginx. Other
roles layer on top.

**No reboots from this role** — package upgrades that need a reboot are
flagged via the `reboot_required` fact and surfaced at the end of `verify.yml`.
A reboot mid-deploy would burn idempotency.

**SSH policy lives in `security_controls`** — the role still owns the drop-in,
but operator posture knobs live under `security_controls.ssh_*`, not `vpn.*`.

## What's done well

- **Single source for sysctl** — `templates/sysctl-vpn.conf.j2` consolidates
  kernel tunables (`net.ipv4.tcp_fastopen`, `tcp_bbr`, UDP buffer sizes, etc).
  Loaded at priority 90 so cloud-init defaults can't override.
- **Forwarding is isolated from hardening** — `90-vpn.conf` keeps forwarding
  disabled; `91-vpn-forward.conf` is the only place that enables IPv4/IPv6
  forwarding, and only when AmneziaWG is enabled.
- **Time sync via `systemd-timesyncd`** — installed and enabled. REALITY breaks
  if clocks drift > 90 s; `verify.yml` asserts sync state.
- **SSH hardening via drop-in** — `templates/sshd_config.d-hardening.conf.j2`
  is dropped at `/etc/ssh/sshd_config.d/20-ansible-hardening.conf` with
  `validate: sshd -t -f %s` before activation.
- **SFTP is internal and managed once** — the packaged `Subsystem sftp` line is
  commented before the drop-in declares `internal-sftp`, avoiding duplicate
  Subsystem directives on Debian/Ubuntu while preserving Ansible file transfer.
- **Moduli pruning is optional and idempotent** — when
  `security_controls.ssh_prune_moduli` is true, `/etc/ssh/moduli` is pruned to
  groups with field 5 >= 3071, with `/etc/ssh/moduli.prev` as local backup.
- **IP forwarding is conditional** — enabled only when `vpn.enable_amneziawg`
  is true; removed when disabled. Avoids forwarding on P0-only nodes.

## Pitfalls

- **Does not install `chrony` or `unattended-upgrades`** — time sync is
  `systemd-timesyncd` (distro default on Debian 13/Ubuntu 24.04). Unattended
  upgrades are not configured by this role; operators add them separately.
- **`systemd-resolved` stub listener is disabled** — the role drops
  `/etc/systemd/resolved.conf.d/no-stub.conf` (`DNSStubListener=no`) so
  port 53 is free for the dns-morph-bridge role when enabled.
- **Cloud-init still creates the admin user first** — baseline hardens sshd
  after the first connection succeeds. Don't remove the cloud-init admin-user
  path unless another first-boot access path replaces it.
- **`RequiredRSASize` is opt-in** — default `security_controls.ssh_required_rsa_size`
  is `0` so older OpenSSH versions never see an unsupported directive.
- **Hostname change requires re-running cloud-init handlers** — don't
  change `ansible_hostname` mid-deploy.
