---
name: linux-hardening
description: Linux hardening conventions for vpn-deploy nodes — baseline role, nftables (not UFW/iptables), SSH, sysctl, fail2ban/sshguard, watchdog. RU-TSPU-aware. Use when editing ansible/roles/baseline, ansible/roles/firewall, ansible/roles/watchdog, or auditing a fresh node. vpn-deploy project variant.
---

# Linux Hardening (vpn-deploy)

The `baseline` and `firewall` Ansible roles establish the hardening floor. cloud-init does
only the bare minimum (admin user + SSH key + python3). Everything else is Ansible.

## Roles owning hardening

| Role | Owns |
|---|---|
| `baseline` | sshd, sysctl, sudoers, journal limits, time sync |
| `firewall` | nftables policy and tables |
| `policy-ratelimit` | nftables rate-limit chains for probed endpoints |
| `watchdog` | health + restart timers (see `[[systemd]]`) |
| `honeypot` | optional decoy SSH on a different port |

## Hard rules

- **No UFW.** No iptables-restore. **nftables is the only firewall.** UFW examples from
  upstream are wrong here.
- **No password SSH.** `PasswordAuthentication no`, `PermitRootLogin no` are baseline.
- **No root cron entries.** All scheduled work is systemd timers (`[[systemd]]`).
- **No `chmod 777`, no `chown -R` on `/`.** Audit anything that recursively touches
  permissions.
- **IP forwarding is conditional.** `net.ipv4.ip_forward=1` is required for AmneziaWG nodes
  (P2) and prohibited on P0/P1-only nodes. Gate via the `amneziawg` role.

## SSH (baseline role)

Floor `/etc/ssh/sshd_config.d/10-baseline.conf`:

```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
MaxAuthTries 3
MaxSessions 4
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
AllowUsers admin
X11Forwarding no
PermitUserEnvironment no
AllowAgentForwarding no
AllowTcpForwarding no
```

Honeypot role moves the real sshd to a non-22 port; default 22 then hosts a tarpit. Both
listening sockets must be allowed in nftables, not just port 22.

## nftables (firewall role)

```nft
table inet vpn-deploy {
    chain input {
        type filter hook input priority filter; policy drop;

        iifname "lo" accept
        ct state { established, related } accept
        ct state invalid drop

        # SSH (admin allowlist)
        tcp dport { 22, {{ ssh_real_port }} } ip saddr @ssh_allowlist accept

        # P0 / P1
        tcp dport { 443, {{ nginx_xhttp_port }} } accept

        # P2
        udp dport 443 accept                      # Hysteria2
        udp dport {{ amneziawg_listen_port }} accept

        # ICMP rate-limited
        icmp type echo-request limit rate 5/second accept
        icmpv6 type echo-request limit rate 5/second accept
    }

    chain output  { type filter hook output  priority filter; policy accept; }
    chain forward { type filter hook forward priority filter; policy drop; }
}
```

Rate-limit chains for subscription endpoints are added by `policy-ratelimit` — keep them
out of the base policy file.

## sysctl floor

`/etc/sysctl.d/99-vpn-deploy.conf`:

```ini
# Network
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Kernel
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.yama.ptrace_scope = 2
fs.suid_dumpable = 0
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.protected_fifos = 2
fs.protected_regular = 2
```

For AmneziaWG nodes, the `amneziawg` role appends `net.ipv4.ip_forward = 1` in a separate
drop-in (`/etc/sysctl.d/30-amneziawg.conf`).

## Intrusion response

- `fail2ban` (or `sshguard`) installed by baseline, scoped to sshd. Bantime 1h. **No
  permanent bans** on disposable nodes — recreate, do not repair.
- `watchdog` timer checks `systemctl is-failed` for the protocol units and reboots only
  after N consecutive failures.

## Validation

- `make ci-fast` runs the role's molecule scenario in a container; this validates sshd
  config, nftables ruleset, and sysctl drop-ins parse.
- Post-deploy: `make verify` runs reachability + SSH banner + nftables ruleset hash.

## Don'ts

- **No `chmod -R` in roles** without a `find` filter scoping it.
- **No `LISTEN_ADDR=0.0.0.0` on management endpoints.** vpnd's debug surfaces bind localhost.
- **No `wget | sudo bash` installers.** All package installs go through apt/dpkg or a
  pinned binary fetched via Ansible `get_url` with a checksum.
- **No `ALLOWED_USERS=*`** in sshd. The allowlist is a literal username.

## See also

- `ansible/roles/baseline/CLAUDE.md`
- `ansible/roles/firewall/CLAUDE.md`
- `ansible/roles/policy-ratelimit/CLAUDE.md`
- `[[systemd]]` — service-level hardening
- `[[security-review]]` — what to look for in PRs touching these roles
