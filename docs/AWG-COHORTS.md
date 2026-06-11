# AmneziaWG cohort obfuscation profiles

The `amneziawg_secrets.{jc,jmin,jmax,s1,s2,h1,h2,h3,h4}` block is what
turns plain WireGuard into AmneziaWG. The role's broad defaults work
on most networks, but some DPI deployments apply WireGuard-shaped
rules that need cohort-specific tuning. This file lists the shipped
profiles; verify on the target network before locking.

## Why this matters

Plain WireGuard Initiation messages are deterministically identifiable:
148 bytes, fixed field layout (4-byte type, 4-byte sender index, 32-byte
ephemeral public key, 48-byte encrypted static key, 28-byte encrypted
timestamp, 16-byte MAC1, 16-byte MAC2). A DPI engine can match on that
size + layout, then apply periodic 20–30 s stalls to "kill the
reconnection cycle" rather than RST. AmneziaWG randomises the size
(`Jc` junk-count, `Jmin/Jmax` junk-length bounds) and headers
(`H1..H4`) so the Initiation no longer fits the rule.

## Shipped profiles

| Profile | Jc | Jmin | Jmax | S1 | S2 | H1..H4 | Cohort file |
|---|---|---|---|---|---|---|---|
| `narrow-junk-sequential` | 4 | 10 | 50 | 0 | 0 | 1, 2, 3, 4 | `ansible/roles/amneziawg/vars/cohorts/narrow-junk-sequential.yml` |
| broad-rule baseline (role default) | 4 | 40 | 70 | 50 | 100 | random per peer | — (role defaults) |

`narrow-junk-sequential` targets DPI rules that discriminate against
the broad-baseline shape (long junks + non-zero S1/S2) but still
accept the compact form with sequential header magic. Behaviour
observed against such a rule: the handshake completes most of the
time but occasionally stalls and the client needs 3–4 retries.

## Selecting a profile

Cohort profiles ship as YAML files under
`ansible/roles/amneziawg/vars/cohorts/<slug>.yml`. Activate one by
setting `vpn.awg_cohort: <slug>` in `ansible/group_vars/all.yml` (or
a host-specific group_vars file). The role reads the cohort file at
runtime and uses its `jc/jmin/jmax/s1/s2/h1..h4` as defaults;
explicit values in `amneziawg_secrets` still win, so the cohort file
sets the profile and SOPS overrides anything per-deployment.

Leaving `vpn.awg_cohort` empty keeps the broad-rule baseline baked
into the role defaults — that is the right starting point on any
network without a documented profile.

`vpn.awg_cohort` is ignored when `amneziawg_secrets.instances` is
non-empty: multi-instance layouts carry their own per-instance
obfuscation parameters and choose the profile inline (see
"Operational notes" below for the multi-instance pattern).

H1..H4 should be **random integers per peer** outside the
`narrow-junk-sequential` profile — using the literal sequential set
`1, 2, 3, 4` everywhere creates a template the censor can train on.
Generate four random 32-bit unsigned ints with:

```bash
for i in 1 2 3 4; do
  printf 'h%d: %d\n' "$i" "$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
done
```

## When to deviate from the profile

- The handshake never completes from a specific network → try the
  `narrow-junk-sequential` values as a known-good shape, then
  re-randomise H1..H4 for any non-matching deployment.
- Handshake completes but stalls every ~30 s → keep current H1..H4;
  the issue is upstream rate-limiting, not the Initiation shape.
- Handshake works but client reports "sometimes 3–4 retries" → that
  matches the documented `narrow-junk-sequential` probabilistic
  behaviour; no further change needed.

## arm64 Android / S3-S4 (must stay zero)

**`S3 = S4 = 0` must hold for any cohort targeting arm64 Android — which is
every family client.** S3/S4 are the junk-size parameters that feed the H4
transport-packet header writer (junk-header insertion on data packets). Per
`amneziawg-go#110` (amnezia-client #2582, no fix as of 2026-05-28), a non-zero
S3/S4 triggers a byte-offset misalignment in the H4 header writer on `awg-go`
arm64 (Android 14, awg-go v0.2.16): the handshake succeeds and the tunnel comes
up, but transport packets are then **silently dropped** — connected interface,
zero data flow, no error surfaced. Reproducer from upstream: `S1=47, S2=45,
S3=38, S4=22` drops; `S3=S4=0` (keeping S1/S2) restores connectivity.

The role does **not** emit S3/S4 today (`awg0.conf.j2` writes only Jc/Jmin/Jmax,
S1/S2, H1–H4), so the baseline is already safe. This is enforced forward: the
amneziawg role fails the play if any cohort file, `amneziawg_secrets`, or
`instances[]` entry sets S3 or S4 to a non-zero value, citing `amneziawg-go#110`.

**Obfuscation tradeoff.** Holding `S3=S4=0` disables H4 junk-header insertion on
transport packets, so obfuscation is reduced to S1/S2 handshake-junk only —
there is no transport-packet-level junk to defeat a per-packet size/shape rule.
That is an accepted constraint while #110 is open: reliability on arm64 Android
beats transport obfuscation that silently breaks the tunnel. If a deployment
genuinely needs transport-packet obfuscation against arm64 targets, route it
over VLESS+REALITY instead of AmneziaWG until upstream fixes #110.

## Operational notes

- The same H1..H4 set must be deployed on both server and client. If
  you rotate H values on the server, push the new client config (the
  `new-client.sh` flow handles this when `amneziawg_secrets.h*` is
  bumped).
- A single host can run several AmneziaWG instances at once — one
  `awg-quick@<name>.service` per entry under
  `amneziawg_secrets.instances`. Each instance has its own listen
  port + address pool + Jc/H1..H4 set, so you can serve the
  `narrow-junk-sequential` profile and a broad-rule profile from the
  same VPS without cross-contaminating fingerprints. Empty / missing
  `instances` keeps the legacy single-instance behaviour.
