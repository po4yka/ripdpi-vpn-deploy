# Xray-core release-line tracker

Pinned version: see `secrets/prod.secrets.example.yaml` →
`xray.version`. The repo policy is: stay on the GitHub-tagged Latest
build, never on a Pre-release in production.

This file tracks notable behavioural changes per release so an
operator deciding when to bump the pin can see the surface they're
crossing.

## v26.2.6 — 2026-02-06

- **XHTTP CDN bypass options** — new headers that make XHTTP look
  more like organic browser traffic, useful for CDN-fronted XHTTP.
- **Finalmask UDP expansion** — Finalmask now covers WireGuard UDP,
  Shadowsocks AEAD/2022 UDP. Variants `XDNS`, `XICMP`, `header-*`,
  `mkcp-*` added.
- **Dynamic Chrome User-Agent** — Xray-core HTTP requests now use a
  dynamic Chrome UA by default, replacing the static `Go-http-client`
  string. No config change required.

## v26.3.27 — 2026-03-27 (current Latest as of 2026-07-26)

- **REALITY auto-probe defence** improvements.
- **ECH full mode** — `echForceQuery` default changed to `"full"`.
- **Finalmask Sudoku** byte-distribution obfuscation. The
  `vpn.xray_finalmask` group_vars toggle in this repo enables this.
- Warning emitted when listening on non-443 ports — non-443 listeners
  are pushed onto the IP blacklist faster.
- Warning when REALITY target SNI is Apple/iCloud — flagged for fast
  ban.
- New `pinnedPeerCertSha256` (outbound-side); deprecates
  `allowInsecure`.
- New `trustedXForwardedFor` sockopt for XHTTP/WS inbounds. The
  `vless-xhttp-localhost` inbound in this repo's xray config template
  uses it.
- uTLS gained the browser-facing `X25519MLKEM768` key share. This
  updates the outer TLS fingerprint and is distinct from VLESS
  Encryption (PQE), which operates inside VLESS and first appears on
  the later Pre-release line.

## v26.4.x — Pre-release as of 2026-04-30

- Carries Xray v26.4.25 + KCP obfs + TCP Masks (per 3xui-v2-9-releases-
  april-2026 digest). KCP obfs is an additional UDP transport surface;
  TCP Masks is a new Finalmask family for TCP.
- Production policy: stage-only until promoted to Latest.

## v26.5.3 — Pre-release as of 2026-05-09

**Breaking changes — schema migration required before upgrading:**

- `echForceQuery` field is **removed**. ECH is now always forced when
  configured. Any config containing `echForceQuery` will fail to
  parse. The changelog-driven breaking-change guard fails if the field
  is present.
- ALPN `["h2","http/1.1"]` is now permitted in the **outer TLS layer**
  for WSS / HUS transports. Prior versions rejected this; the
  rejection itself was an Xray-specific fingerprint.
- New `finalRules` egress filter. Freedom now applies built-in safety
  fallbacks on server-side and reverse-proxy traffic; an unconstrained
  first `allow` rule is required to preserve the earlier direct-routing
  behaviour. The guard activates this requirement when the pin reaches
  v26.5.3.
- ICMP tunnel transport added.
- **VLESS Encryption (PQE)** — an ML-KEM-768 + X25519 VLESS encryption
  layer with its own server/client settings. It is not the uTLS
  `X25519MLKEM768` ClientHello key share noted under v26.3.27. Adoption
  remains on HOLD under `PQ-REALITY-ADOPTION.md`.

## v26.5.9 — Pre-release as of 2026-05-09

- Continues the VLESS Encryption (PQE) release line introduced in
  v26.5.3. It does not change this repository's HOLD decision.

## v26.6.1, v26.6.22, v26.6.27 — Pre-release as of 2026-07-10

- These tags remain marked Pre-release upstream. v26.6.27 updates the
  cryptographic dependency that supplies ML-KEM, but no stable release
  or supported-client transition has occurred.
- Production remains pinned to the GitHub-tagged Latest release. See
  `PQ-REALITY-ADOPTION.md` for the separate STAGING and PRODUCTION
  eligibility gates.

## v26.7.11 — Pre-release as of 2026-07-26

- The tag remains marked Pre-release and its release entry carries no
  repository-adopted migration guidance.
- It does not satisfy the stable-release or supported-client gates for VLESS
  Encryption over REALITY.
- Production therefore remains pinned to v26.3.27. Any evaluation belongs to
  an isolated staging cohort and still passes the guards below.

The fenced registry below is the machine-readable source for CI. `always`
rules apply before an upgrade when the migration is backwards-compatible;
`pinned-at-least` rules activate only when `xray.version` reaches the declared
release. Selectors must match at least one object and assertions apply to every
match.

```yaml xray-ci-guards
guards:
  - id: ech-force-query-removed
    applies_from: v26.5.3
    activation: always
    document: example-secrets
    select:
      path: xray
    forbid:
      path: echForceQuery
    message: Remove xray.echForceQuery before upgrading Xray-core.
  - id: freedom-final-rules-allow
    applies_from: v26.5.3
    activation: pinned-at-least
    document: rendered-xray
    select:
      path: outbounds
      where:
        protocol: freedom
    require:
      path: settings.finalRules.0
      equals:
        action: allow
    message: Add an unconstrained first allow rule to every Freedom outbound before upgrading Xray-core.
  - id: pq-reality-hold
    applies_from: v26.5.3
    activation: always
    document: rendered-xray
    select:
      path: inbounds
      where:
        protocol: vless
        streamSettings.security: reality
    require:
      path: settings.decryption
      equals: none
    message: Keep VLESS Encryption over REALITY on HOLD; see docs/PQ-REALITY-ADOPTION.md.
```

## Production rollout policy

1. Bump `xray.version` in the secrets schema and SOPS files only when
   the target tag is GitHub-tagged Latest, not Pre-release.
2. Run `make ci-fast` — it executes `check-xray-breaking-changes.py`,
   which derives version-aware config migrations from this release line.
3. Run on a staging cohort for ≥48 hours before fleet rollout.
4. Capture `xray test -config` output in the deploy log; refuse to
   restart xray on a host where the new config fails parse.
5. Keep the previous binary at `/opt/xray/bin/xray.prev` for
   single-flag rollback (`make rollback-xray
   ROLLBACK_XRAY_VERSION=vX.Y.Z`).

VLESS Encryption over REALITY has additional client-compatibility and evidence gates. The general Xray rollout steps above do not override the HOLD decision in `PQ-REALITY-ADOPTION.md`.

## Build-from-source path

Set `vpn.build_xray_from_source: true` in group_vars to switch the
xray role from "download a prebuilt release asset" to "git clone the
pinned tag and run `go build` on the VPS".

Trade-offs:

  * slower first deploy (~2-5 minutes for `go build`)
  * requires Go on the VPS (`apt install golang-go`, installed by the
    role)
  * the schema's `xray.linux_*_sha256` becomes an integrity check
    on the produced binary, not just a verification of the upstream
    release asset — a bytewise-reproducible upstream change is
    caught at restart time when the pin is real (placeholder skips)
  * closes the "release tag silently re-cut with different bytes"
    risk, because the build inputs are the git tag + the Go toolchain
    version, both of which are independently pinned

When to flip it on: cohorts where supply-chain attestation is part of
the threat model (high-risk operators, audited deployments). Default
stays off; the prebuilt path is the v1 baseline.

## Revisit cadence

Re-read this page on every Xray-core minor bump and at the start of
each quarter. Stale rollout instructions are worse than no
instructions.
