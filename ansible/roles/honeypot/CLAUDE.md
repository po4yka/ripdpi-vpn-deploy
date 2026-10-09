# role: honeypot — active-probing detection

## Design decisions

**Same-host honeypot for cheap signal** — binds one plausible-looking listener
on `honeypot.port` (`honeypot_port: 4443` in `group_vars/all.yml`) that records
hits without responding. Any hit is a probing signal because legitimate users
have no reason to touch them.

**Logs only; no auto-block** — feeds `monitoring`'s probing summary.
Auto-blocking probers is bait — they rotate IPs faster than we can ban.

**Metrics use a shared writer group** — the textfile directory is root-owned,
setgid and sticky for `node_exporter_textfile`; the honeypot service receives
group write access while monitoring can manage the directory without revoking
it or letting one producer replace another producer's metrics.

**Connection logs are actively size-bounded** — a dedicated systemd timer checks the honeypot logrotate policy every five minutes. The listener reopens `connections.log` for every event, so rename + `create 0640 honeypot honeypot` is safe and avoids `copytruncate` data-loss races.

**Rolling metrics use calendar windows** — every textfile flush evicts minute buckets outside `[now-59, now]`, including after a completely idle period. The current-minute gauge is zero unless the newest bucket belongs to the current wall-clock minute.

**Listener families follow rendered inventory** — IPv4 always binds to `honeypot.listen_addr`; when inventory contains `server_ipv6`, startup also binds `[::]` with `IPV6_V6ONLY=1`. Both sockets are created before either accept loop starts, so a missing promised family fails the service rather than degrading silently.

**Hetzner floating IPv4 needs guest ownership** — Terraform assigns the address at the provider edge; this role adds its `/32` to the gathered default IPv4 interface before binding. A root oneshot unit with only `CAP_NET_ADMIN` is required by the listener, so boot and restart restore the address. Converge compares the actual guest address before starting the unit and restarts it if an external change removed its address. Unit names include the address and interface: reconfiguration stops and removes only obsolete role-owned units, whose `ExecStop` removes their exact previous address. Other providers retain their existing guest convergence path.

**Address removal is idempotent only for absence** — `ExecStop` inspects the exact interface and skips deletion when the owned `/32` is already absent. Inspection errors, malformed replies and deletion failures still fail the unit; another address or the same address with a different prefix is never removed. This allows drift repair to restart an active oneshot after its address was removed externally.

## What's done well

- **Banner-free** — every honeypot port closes silently after TCP accept.
  No fingerprintable response.
- **Rotated log files** — same retention as `monitoring`.

## Pitfalls

- **Do not publish a primary IPv4 as the dedicated address** — the role refuses that assignment before networking changes. A nondefault routed interface must be selected explicitly through `honeypot_secondary_interface` and already exist.

- **Don't expose a honeypot port that legit ops uses** — e.g., if you SSH on
  2222 yourself, do not honeypot 2222. The firewall role fails convergence
  when any TCP public listener, the honeypot included, claims the effective
  `sshd -T` port. Other operator ports you use are not checked.
- **Honeypot ports must be in the firewall allow-list** — otherwise nftables
  drops before the honeypot sees the hit, and you record nothing.
- **Verify each enabled address family separately** — a matching TCP port on IPv4 does not prove the provider's IPv6 firewall opening has a consumer. Keep Molecule and `security-verify.yml` assertions split across `ss -4` and `ss -6`.
- **Rate-limit log writes** — a broad scan can fill the disk otherwise. Keep the in-process event cap, the 10M logrotate threshold, the five-minute timer, and bounded archive retention together.
- **Canary shares the relay IP — observability, not guaranteed early warning** — because the honeypot listeners and the REALITY/VLESS port live on the same IP, a probe that targets the honeypot port and a probe that targets the VPN port are identical from a routing perspective. Under netflow-seeded or infrastructure-enumeration targeting, the adversary may probe both ports simultaneously or probe the VPN port directly without ever hitting the canary. The canary therefore provides a useful probing signal when it fires, but the absence of a canary hit does NOT mean the VPN port was not probed. A separate-IP canary (different VPS, same operator) is the path to real early-warning with meaningful lead time.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `honeypot_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
