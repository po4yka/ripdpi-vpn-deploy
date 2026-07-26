# terraform/providers/vultr — tertiary provider

## Design decisions

**Same output schema as UpCloud + Hetzner** — including `ssh_port`, so
inventory and cloud-init waiting use the provider-declared listener rather
than assuming TCP/22.

**Plan + region constraints** — `vc2-1c-1gb` / `vhf-1c-1gb` only; restricted
to AMS / FRA / LHR for low-latency RU paths.

**Secondary IPv4 convergence is provider reboot plus guest proof** — `vultr_instance_ipv4.honeypot` keeps `reboot = true`, then `render-inventory.sh` polls the primary SSH address until the secondary IPv4 is present on a guest interface. Inventory must not publish `honeypot_listen_addr` from API state alone.

## What's done well

- **`backups_enabled = false`** — Vultr's built-in backups can store unencrypted
  snapshots. The `backup` role owns this via restic+age instead.

## Pitfalls

- **Vultr API rate limit is tight** — bulk `terraform apply` across many hosts
  hits 429s. Use `-parallelism=2`.
- **Floating IP is global, not regional** — but attachment is regional. Don't
  assume regional FIPs.
- **DDoS protection IPs flag VPN traffic** — never enable Vultr's "DDoS
  Protection" add-on; it routes through Vultr-owned scrubbers that inspect
  TLS metadata.
- **Vultr ASN (20473) is a heavily-flagged VPN exit** — same caveat as
  Hetzner; lean harder on REALITY camouflage + cohort tuning here.
- **UDP/443 edge rule ≠ UDP delivery** — `firewall.tf` opens UDP/443 under
  `enable_hysteria` (`vultr_firewall_rule.hysteria`, v4+v6), but a present rule
  does not guarantee the provider network delivers inbound UDP. After deploy,
  verify externally with `make burn-check` (QUIC probe); on-host `nft`/`ss`
  ACCEPT is not evidence. See `docs/PROVIDER-NOTES.md` → "UDP/443 edge
  reachability".
- **Secondary IPv4 needs live-provider evidence** — mock-provider tests prove the reboot flag and inventory gate, not Vultr's control-plane/guest timing. A real deploy completes this check when inventory rendering observes the address inside the guest; failure is blocking.
