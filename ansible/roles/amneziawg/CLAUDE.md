# role: amneziawg — P2 device-VPN with cohort obfuscation

## Design decisions

**Userspace AWG, not kernel WireGuard** — AmneziaWG 2.0 in userspace is the
only path that supports the cohort obfuscation params (jc/jmin/jmax/s1/s2 and
2.0 finalmask/headers). Kernel WG doesn't.

**Cohort profiles are config, not code** — `vars/cohorts/<carrier>.yml` is the
SOT. New cohort = new file. See `docs/AWG-COHORTS.md`. Currently shipped as
a YAML file: RTK South. The MTS / Beeline / MegaFon broad-rule baseline is
encoded as the role's hard-coded defaults (no separate cohort file needed —
that profile is the safe starting point on any unmeasured network).

**One peer key per device, never shared** — enforced by `scripts/new-client.sh`.
Reused keys break replay protection.

## What's done well

- **Cohort selection is explicit** — `vpn.awg_cohort` names a file under
  `vars/cohorts/`; there's no "auto" because cohort tuning is operator
  judgment, not a default. Empty string keeps the broad-rule baseline
  encoded in the role defaults — chosen deliberately, not silently.
- **Kill-switch in the emitted client** — `scripts/check-singbox-killswitch.py`
  validates the emitted bundle before it ships.

## Pitfalls

- **AWG 2.0 client app version skew** — issue #2457: clients on AmneziaWG
  client v1.0.x silently fall back to vanilla WG handshake when the server
  uses 2.0 finalmask. Pin client version in `docs/CLIENT-NOTES.md`.
- **MTU mismatch breaks roaming** — set `mtu = 1280` for cellular cohorts;
  1420 for Wi-Fi-primary. Wrong value silently corrupts large packets.
- **Endpoint port reuse with Hysteria** — both use UDP. See `firewall/CLAUDE.md`
  pitfall; pick distinct ports.
- **`jc` of 0 is not "off", it's "junk count 0"** — older clients interpret
  this as a malformed packet. Use the cohort's recommended floor.
