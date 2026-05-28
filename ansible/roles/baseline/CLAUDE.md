# role: baseline — every host starts here

## Design decisions

**Sets ground state, not policy** — installs sysctl baseline, time sync
(`systemd-timesyncd`), SSH hardening drop-in, and IP-forwarding sysctl when
AmneziaWG is in scope. Doesn't open ports; doesn't install Xray/nginx. Other
roles layer on top.

**No reboots from this role** — package upgrades that need a reboot are
flagged via the `reboot_required` fact and surfaced at the end of `verify.yml`.
A reboot mid-deploy would burn idempotency.

## What's done well

- **Single source for sysctl** — `templates/sysctl-vpn.conf.j2` consolidates
  kernel tunables (`net.ipv4.tcp_fastopen`, `tcp_bbr`, UDP buffer sizes, etc).
  Loaded at priority 90 so cloud-init defaults can't override.
- **Time sync via `systemd-timesyncd`** — installed and enabled. REALITY breaks
  if clocks drift > 90 s; `verify.yml` asserts sync state.
- **SSH hardening via drop-in** — `templates/sshd_config.d-hardening.conf.j2`
  is dropped at `/etc/ssh/sshd_config.d/20-ansible-hardening.conf` with
  `validate: sshd -t -f %s` before activation.
- **IP forwarding is conditional** — enabled only when `vpn.enable_amneziawg`
  is true; removed when disabled. Avoids forwarding on P0-only nodes.

## Pitfalls

- **Does not install `chrony` or `unattended-upgrades`** — time sync is
  `systemd-timesyncd` (distro default on Debian 13/Ubuntu 24.04). Unattended
  upgrades are not configured by this role; operators add them separately.
- **`systemd-resolved` stub listener is disabled** — the role drops
  `/etc/systemd/resolved.conf.d/no-stub.conf` (`DNSStubListener=no`) so
  port 53 is free for the dns-morph-bridge role when enabled.
- **`PasswordAuthentication no` is set by cloud-init *first*** — baseline
  doesn't re-set it. If you ever rip out cloud-init, this assumption breaks
  silently (the SSH connection survives because keys still work; the
  password path is suddenly open).
- **Hostname change requires re-running cloud-init handlers** — don't
  change `ansible_hostname` mid-deploy.
