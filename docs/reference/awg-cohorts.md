# AmneziaWG cohort obfuscation profiles

> **Status:** Current · **Type:** reference · **Tier:** CORE · **Reviewed:** 2026-10-23

The `amneziawg_secrets.instances[].{wire_profile,jc,jmin,jmax,s1,s2,h1,h2,h3,h4,i1,i2,i3,i4,i5}` block is what
turns plain WireGuard into AmneziaWG. The role's broad defaults work
on most networks, but some DPI deployments apply WireGuard-shaped
rules that need cohort-specific tuning. This file lists the shipped
profiles; verify on the target network before locking.

## Source pinning invariant

The userspace role builds `amneziawg-go` and `amneziawg-tools` from upstream git.
Tags are mutable, so a family deploy must pin both the checkout ref and the exact
resolved commit SHA:

```yaml
amneziawg_go_version: "v0.2.12"        # tag or immutable commit ref to checkout
amneziawg_go_commit: "<40-hex-sha>"    # expected `git rev-parse HEAD`
amneziawg_tools_version: "v1.0.20241018"
amneziawg_tools_commit: "<40-hex-sha>"
```

The role refuses to build when either commit pin is empty, malformed, or does
not match the checked-out tree. This keeps tag-only pinning out of production and
turns an upstream tag re-point into a deploy-time failure instead of a silent
binary change.

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
| broad-rule baseline (role default) | 4 | 40 | 70 | 50 | 100 | random per instance | — (role defaults) |

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
runtime and uses its `wire_profile/jc/jmin/jmax/s1/s2/h1..h4/i1..i5` as defaults;
explicit values in each `amneziawg_secrets.instances[]` still win, so the cohort file
sets the profile and SOPS overrides anything per-deployment.

Leaving `vpn.awg_cohort` empty keeps the broad-rule baseline baked
into the role defaults — that is the right starting point on any
network without a documented profile.

`vpn.awg_cohort` supplies defaults for every instance; explicit per-instance
parameters win. A single instance uses the same nonempty list contract.

For singleton profiles, choose **random uint32 values per instance**, stored as
quoted decimal strings, outside the
`narrow-junk-sequential` profile — using the literal sequential set
`1, 2, 3, 4` everywhere creates a template the censor can train on.
All peers of an instance use the same headers. Use separate instances for
different wire profiles. Each header must be its standard message type
(`H1="1"`, `H2="2"`, `H3="3"`, `H4="4"`) or use values above four. The
engine rewrites other values at most four. The four closed intervals must not overlap, and
`148 + S1` must differ from `92 + S2`. Admission refuses these invalid inputs
before deployment or export.

Generate four candidate random 32-bit unsigned integers with:

```bash
for i in 1 2 3 4; do
  printf 'h%d: "%d"\n' "$i" "$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
done
```

Repeat generation if a value is at most four or two values match.

## When to deviate from the profile

- The handshake never completes from a specific network → try the
  `narrow-junk-sequential` values as a known-good shape, then
  re-randomise H1..H4 for any non-matching deployment.
- Handshake completes but stalls every ~30 s → capture packet loss, MTU,
  NAT state and traffic counters before changing the profile. Timing alone
  does not establish rate limiting or exclude a wire-profile mismatch.
- Handshake needs 3–4 retries → compare the selected profile with a control
  on the same path and record handshake and sustained-transfer results.
  The observation above does not establish acceptable reliability.

## arm64 Android / S3-S4 (must stay zero)

**`S3 = S4 = 0` must hold for any cohort targeting arm64 Android — which is
every family client.** S3/S4 are the junk-size parameters that feed the H4
transport-packet header writer (junk-header insertion on data packets). Per
`amneziawg-go#110` and amnezia-client #2582, a non-zero S3/S4 triggers the
affected H4 transport-header path on arm64 Android: the handshake succeeds and
the tunnel comes up, but transport packets are then **silently dropped** —
connected interface, zero data flow, no error surfaced. The last confirmed
broken combination is AmneziaVPN 4.8.15.5 with embedded awg-go v0.2.16.
Reproducer: `S1=47, S2=45, S3=38, S4=22` drops; `S3=S4=0` (keeping S1/S2)
restores connectivity.

The role does **not** emit S3/S4 today (`awg0.conf.j2` writes Jc/Jmin/Jmax,
S1/S2, H1–H4 and optional I1–I5), so the baseline retains zero S3/S4. The
amneziawg role fails the play if any cohort file, `amneziawg_secrets`, or
`instances[]` entry sets S3 or S4 to a non-zero value, citing `amneziawg-go#110`.

**Obfuscation tradeoff.** Holding `S3=S4=0` disables H4 junk-header insertion on
transport packets, so obfuscation is reduced to S1/S2 handshake-junk only —
there is no transport-packet-level junk to defeat a per-packet size/shape rule.
That is an accepted constraint while the verified safe floor in
`contract/amneziawg-arm64-version-floor.json` is unset: reliability on arm64
Android beats transport obfuscation that silently breaks the tunnel. If a
deployment genuinely needs transport-packet obfuscation against arm64 targets,
route it over VLESS+REALITY instead of AmneziaWG.

## Version-floor review

`contract/amneziawg-arm64-version-floor.json` is the machine-readable source of truth shared with the RIPDPI client. A weekly workflow checks the tracked upstream issue states and Amnezia client release notes. A changed issue state or a release that claims an S3/S4/H4 arm64 correction opens a rolling review issue; it never changes the candidate floor, verified floor, role guard, secrets schema, or client guard.

Before setting a verified floor, test the candidate on physical Android arm64 hardware using the same server and path for the non-zero reproducer and an `S3=S4=0` control. Complete at least three reconnects, verify bidirectional traffic, DNS, and a sustained transfer, capture the outbound H4 bytes and offsets, and record the app version, embedded core version and commit, ABI, Android version, and results. Relaxation is a coordinated deploy-and-client change and must also account for older clients still in the fleet.

## Operational notes

- The same H1..H4 set must be deployed on both server and client. If
  you rotate H values on the server, push the new client config (the
  `new-client.sh` flow handles this when `amneziawg_secrets.instances[].h*` is
  bumped).
- A single host can run several AmneziaWG instances at once — one
  `awg-quick@<name>.service` per entry under
  `amneziawg_secrets.instances`. Each instance has its own listen
  port + address pool + Jc/H1..H4 set, so you can serve the
  `narrow-junk-sequential` profile and a broad-rule profile from the
  same VPS without cross-contaminating fingerprints. Empty/missing instances
  and top-level shadow keys/peers refuse admission.

## Device issuance and revocation

Use `AWG_INSTANCE=<name> PROVIDER=<provider> ENV=<environment>` with
`scripts/new-client.sh <device>` for the all-profile transaction. Issuance uses
the selected server subnet, reserves server/network/broadcast and peer claims,
and stores distinct device keys plus the exact `awg_binding` in the encrypted
registry. It never stages plaintext on disk or emits recovery/server keys.

`make awg-issue CLIENT=<device> SOPS_FILE=<private-encrypted-file> PROVIDER=… ENV=… AWG_INSTANCE=…`
issues AWG alone. The corresponding `make awg-revoke` removes only that AWG peer
and recovery binding, preserving other transport identities and registry state.
The encrypted file must be owner-only `0600` in a private directory. Both verbs
share the canonical device writer lock and retain the prior document on failure.

Existing encrypted documents must be migrated explicitly to the instance list
and exact registry binding before issuance/export. There is no dual authority or
automatic migration of private operator documents.

Standalone export supports `OUTPUT=<new-file> scripts/emit-awg.sh <device>`
for a no-clobber owner-only recipient artifact in a private `0700` directory.
The configuration contains `PrivateKey = <CLIENT_PRIVATE_KEY>` and cannot
connect until the device's matching key is supplied separately. Issuance stores
that key in the encrypted registry and emits metadata; it does not create a
plaintext key file. Follow [Private-key handoff](ripdpi-bundle.md#private-key-handoff)
for the existing manual delivery process.
Existing, linked, shared or tracked output destinations refuse; ordinary stdout
remains available for an explicitly selected recipient. Device addresses are
unreserved IPv4 /32 and IPv6 /128 identities inside the selected instance's
pools; broader prefix routing requires explicit `address_kind: routed` ownership.

`new-client.sh --emit-uri` requires `OUTPUT=<new private recipient file>`
in a `0700` directory. The destination is reserved before enrollment and removed
on transaction failure. URI passwords never enter metadata stdout.

## Local source-upgrade candidate

`tests/integration/awg_source_candidate/sources.json` selects Go v3.1.20260828 and tools
v3.1.20260812 independently of the deployment examples above. Run
`build-gate -- make test-awg-source-candidate` against local Docker to build both
exact source pairs and exercise mixed-version TCP/UDP/DNS, captured packet
headers, reconnects and warm adoption/compensation in a disconnected Linux lab.
The command requires systemd, TUN and privileged containers inside the local
Docker VM; it creates no provider objects, published ports or workspace mounts.

The candidate has no production eligibility: the Go tag has no release object
at the recorded review, and Linux arm64 does not establish physical Android
acceptance. Deployment pins, wire fingerprints and the S3/S4 zero floor remain
unchanged. The lab uses the existing source publisher, but its explicit service
restart/rollback procedure does not claim automatic production-role data-plane
readiness or a fleet rollout.

## Device addresses and MTU

Every device peer has both host identities in its instance pools:

```yaml
allowed_ips:
  ipv4: "10.66.66.2/32"
  ipv6: "fd42:42:42::2/128"
```

An explicitly routed peer uses `address_kind: routed` with a typed map of its
owned prefixes. Scalar CIDRs are no longer accepted. Existing encrypted inputs
must be migrated deliberately under credential authorization before use;
regenerate device configurations after migration. Revocation removes both
families with the selected peer key.

`instances[].mtu` overrides `amneziawg_cohort.mtu`, which overrides
`amneziawg.mtu` (default 1420). Values must be integers from 1280 through 1420.
The lower bound retains IPv6 link support and the upper bound retains the
established tunnel ceiling; this is a supported configuration range, not a claim
that 1420 is optimal on every path. Server, standalone, bundle and liveness use
the same value. A constrained path can explicitly select 1280.

The approved uplink must have a usable IPv6 default route and a global source
address. An RA-derived route requires `net.ipv6.conf.<uplink>.accept_ra=2` so it
survives router forwarding mode; establish that through the host's network
configuration before deployment. The AWG role validates this prerequisite and
does not rewrite provider routing. NAT and forwarding are scoped to that uplink.

Run `make test-awg-dualstack-runtime` only in the explicitly isolated Linux
root/TUN native lab. Positive Linux results and Android native-core emulator
results retain their own evidence classes. Android acceptance for this change
is limited to the authorized arm64 emulator/native-core procedure below.

## Android baseline procedure

Use the RIPDPI consumer task's isolated Android JNI interop runner with a clean
consumer source commit, the exact pinned baseline AWG peer checkout and an
explicitly leased arm64 emulator. The current baseline keeps S3=S4=0. Generate a
fresh invocation nonce and an owner-only evidence directory, then run:

```bash
python3 "$PEER_ROOT/scripts/tests/run-android-awg-interop.py" \
  --peer-source "$AWG_PEER_SOURCE" --api 32 \
  --output-dir "$EVIDENCE_DIR" --nonce "$AWG_CLIENT_NONCE"
export AWG_CLIENT_EVIDENCE="$EVIDENCE_DIR/evidence.json"
export AWG_CLIENT_SOURCE_SHA="$(git -C "$PEER_ROOT" rev-parse HEAD)"
export PEER_ROOT AWG_CLIENT_NONCE AWG_CLIENT_EVIDENCE AWG_CLIENT_SOURCE_SHA
make verify-awg-dualstack-client-evidence
```

The evidence validator binds the invocation and exact client source to the
packaged native-library/APK digests, ABI/OS and measured IPv4/IPv6 TCP/UDP/DNS
records. Three native reconnect cycles run at each MTU endpoint, 1280 and 1420.
Missing or substituted logs/artifacts refuse; hand-written success records do
not establish acceptance.

This procedure produces **emulator/native-core** evidence. It does not establish
physical-device or Android VpnService/TUN acceptance. The
Linux native lane separately proves kernel forwarding, per-device revocation,
tunnel-death lockdown and complete activation compensation. Emulator evidence
does not establish production Android VPN policy. The separate hardware policy
for upgrading the non-zero S3/S4 version floor remains unchanged.

## Range and signature profile

Bundle version 2 uses `wire_profile: awg-3.1-ranges-v1`. Headers are canonical
strings such as `"11"` or `"1000-1999"`. I1-I5 use bounded tag programs and are
sent before handshake junk packets. The exact contract and limits are in
[ripdpi-bundle.md](ripdpi-bundle.md). Earlier source pairs admit singleton
headers without signatures. The reviewed 3.1 pair admits the supported ranges
and tags but retains its production hold. Keep S3/S4 zero until the physical
arm64 policy has qualifying evidence.

Before the coordinated version 2 rollout, add the named `wire_profile` to each
private instance and quote its current singleton H values. This preserves the
existing packet headers. Export fresh bundles after the client update; version 1
bundles are rejected. Private documents are not changed automatically.
