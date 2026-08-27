# role: amneziawg — P2 device-VPN with cohort obfuscation

## Design decisions

**Userspace AWG, not kernel WireGuard** — AmneziaWG 2.0 in userspace is the
only path that supports the cohort obfuscation params (jc/jmin/jmax/s1/s2 and
2.0 finalmask/headers). Kernel WG doesn't.

**Cohort profiles are config, not code** — `vars/cohorts/<slug>.yml` is the
SOT. New cohort = new file. See `docs/AWG-COHORTS.md`. Currently shipped as
a YAML file: `narrow-junk-sequential`. The broad-rule baseline (long junks
+ non-zero S1/S2 + random per-peer H1..H4) is encoded as the role's
hard-coded defaults — no separate cohort file needed, that profile is the
safe starting point on any unmeasured network.

**One peer key per device, never shared** — enforced by `scripts/new-client.sh`.
Reused keys break replay protection.

**Source refs require matching immutable commits** — the secrets example and
both bootstrap generators emit each source tag with its resolved commit SHA.
The role verifies the checkout still resolves to that SHA before building.
Build receipts bind the installed binaries to those resolved commits, so
check mode reports only actionable binary drift and never runs a compiler.

**arm64 S3/S4 floor is a cross-repo policy** — `contract/amneziawg-arm64-version-floor.json` records known-broken versions, tracked upstream issue states, and candidate/verified floors. A release claim only opens a revalidation issue; the role and client remain fail-closed until physical arm64 evidence establishes a safe floor.

## What's done well

- **Molecule executes role tasks** — pinned source trees and explicit no-TUN
  binaries exercise guards, build receipt comparison, config and systemd
  lifecycle. They are not evidence of upstream binary or tunnel liveness.

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
- **Issue closure is not proof of an arm64 fix** — amnezia-client #2582
  reproduced S3/S4 failure after an earlier claimed fix. Never weaken the
  guard from release notes alone; follow the tracker checklist.
- **Config changes restart instances, briefly dropping tunnels** — the
  handler uses a full `systemd` restart (not reload): `awg-quick strip`
  cannot apply address/route changes and aborts on inactive instances.
  Expect a seconds-long tunnel interruption on every peer/config change;
  schedule AWG config waves accordingly.
- **The tools build output is `src/wg`, not `src/awg`** — `/usr/bin/awg` is
  created by `make install`. Using the installed name as the source artifact
  makes every check-mode run report false drift.
