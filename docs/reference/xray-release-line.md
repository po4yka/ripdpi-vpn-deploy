# Xray-core release-line tracker

> **Status:** Current · **Type:** reference · **Tier:** CORE · **Reviewed:** 2026-10-23

Pinned version: see `secrets/prod.secrets.example.yaml` →
`xray.version`. The repo policy is: stay on the GitHub-tagged Latest
build, never on a Pre-release in production.

This file tracks notable behavioural changes per release so an
operator deciding when to bump the pin can see the surface they're
crossing.

## v25.9.5 — PQE history correction reviewed 2026-10-17

- Upstream announced VLESS Encryption (PQE) in this release. The tagged
  `v26.3.27` source also contains its `mlkem768x25519plus` parser and
  handshake. The later Pre-release entries are not its introduction.
- This corrects release history only. The repository retains classical
  server/client artifacts and the HOLD policy in `../decisions/0006-pq-reality-adoption.md`.

## v26.2.6 — 2026-02-06

- **XHTTP CDN bypass options** — new headers that make XHTTP look
  more like organic browser traffic, useful for CDN-fronted XHTTP.
- **Finalmask UDP expansion** — Finalmask now covers WireGuard UDP,
  Shadowsocks AEAD/2022 UDP. Variants `XDNS`, `XICMP`, `header-*`,
  `mkcp-*` added.
- **Dynamic Chrome User-Agent** — Xray-core HTTP requests now use a
  dynamic Chrome UA by default, replacing the static `Go-http-client`
  string. No config change required.

## v26.3.27 — 2026-03-27 (repository pin)

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
  Encryption (PQE), which operates inside VLESS. This stable release already
  supports `mlkem768x25519plus` server decryption and client encryption. The repository retains HOLD.
- **REALITY ML-DSA-65** — `mldsa65Seed` and `mldsa65Verify` are separate
  certificate signature settings in this stable engine. They are not exposed
  by this repository's server or client contract.

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
  layer with its own server/client settings, already supported by v26.3.27.
  It is not the uTLS
  `X25519MLKEM768` ClientHello key share noted under v26.3.27. Adoption
  remains on HOLD under `../decisions/0006-pq-reality-adoption.md`.

## v26.5.9 — Pre-release as of 2026-05-09

- Continues the existing VLESS Encryption (PQE) release line. It does
  not change this repository's HOLD decision.

## v26.6.1, v26.6.22, v26.6.27 — Pre-release as of 2026-07-10

- These tags remain marked Pre-release upstream. v26.6.27 updates the
  cryptographic dependency that supplies ML-KEM. These entries do not
  establish a repository-supported client transition or PQE adoption.
- Production remains pinned to the GitHub-tagged Latest release. See
  `../decisions/0006-pq-reality-adoption.md` for the separate STAGING and PRODUCTION
  eligibility gates.

## v26.7.11 — Pre-release as of 2026-07-26

- The tag remains marked Pre-release and its release entry carries no
  repository-adopted migration guidance.
- It does not satisfy the stable-release or supported-client gates for VLESS
  Encryption over REALITY for those prerelease artifacts. Stable engine support
  in v26.3.27 does not replace the missing client-delivery and acceptance evidence.
- Production therefore remains pinned to v26.3.27. Any evaluation belongs to
  an isolated staging cohort and still passes the guards below.

## v26.7.28 through v26.10.17 — Pre-release as of 2026-10-17

- At the October 17 review, upstream Latest remained v26.3.27. Newer tags were Pre-release.
- The server pin and enforced PQE HOLD remain unchanged. The HOLD is based on
  the unsupported client-delivery contract and missing promotion evidence.

## v26.10.21 — 2026-10-21 (upstream Latest reviewed 2026-10-23)

- Upstream marked this security release Latest on October 22. It is no longer
  classified as a prerelease. Local pin parity uses the separate repository-pin
  heading above and does not establish release qualification.
- The release removes three roots from the newer bundled trust store and uses
  Go 1.27.3 to reject compromised intermediate public keys. The compiler fix is
  GO-2026-6809 / CVE-2026-111943. Fixed supported compiler versions are Go 1.27.3
  and Go 1.26.10; the denylist protects verification when system trust has not
  yet been updated.
- The retained v26.3.27 source has no bundled fallback-root dependency. The
  Android client rebuild uses Go 1.27.3 while retaining its reviewed source and
  protection patches. Metadata and each packaged ABI must identify that compiler.
- Availability does not promote a server pin. Qualify the actual candidate
  binary against rendered configurations and preserve the 48-hour staging,
  rollback, and explicit production authorization gates below. The removed
  ECH field and Freedom finalRules guard still apply. PQE remains on HOLD.

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
    message: Keep VLESS Encryption over REALITY on HOLD; see docs/decisions/0006-pq-reality-adoption.md.
```

## Production rollout policy

1. Bump `xray.version` in the secrets schema and SOPS files only when
   the target tag is GitHub-tagged Latest, not Pre-release. Production
   deploys refuse any version outside `xray_runtime_production_versions`
   (`ansible/roles/xray-runtime/defaults/main.yml`) before download. Upstream
   prereleases carry plain tags, so this reviewed list, not the tag shape,
   is the machine gate. Add a version only after its staging soak, and keep
   the repository pin in it (`scripts/check-xray-version-pin.py` checks this).
2. Run `make ci-fast` — it executes `check-xray-breaking-changes.py`,
   which derives version-aware config migrations from this release line.
3. Run on a staging cohort for ≥48 hours before fleet rollout.
4. Capture `xray test -config` output in the deploy log; refuse to
   restart xray on a host where the new config fails parse.
5. Keep the previous release under `/opt/xray/releases/<version>-archive`
   (or `<version>-source-<full-commit>`) for single-flag rollback of
   `xray.service` (`make rollback-xray ANSIBLE_LIMIT=<alias>
   ROLLBACK_XRAY_VERSION=vX.Y.Z`, one node per run); private gateways keep
   the pinned release, see
   [../how-to/rollback.md](../how-to/rollback.md#level-2--binary-rollback).

VLESS Encryption over REALITY has additional client-compatibility and evidence gates. The general Xray rollout steps above do not override the HOLD decision in `../decisions/0006-pq-reality-adoption.md`.

## Build-from-source path

Set `vpn.build_xray_from_source: true` in group_vars to switch the
xray role from "download a prebuilt release asset" to "git clone the
pinned commit and run `go build` on the VPS". Before enabling it, replace
the generated `xray.source_commit`, `xray.source_linux_amd64_sha256`, and
`xray.source_linux_arm64_sha256` placeholders with the exact reviewed commit
and the expected native digest for each supported architecture. The release
`xray.version` remains the installation identity.

Trade-offs:

  * slower first deploy (~2-5 minutes for `go build`)
  * requires Go on the VPS (`apt install golang-go`, installed by the
    role)
  * `xray.source_linux_{amd64,arm64}_sha256` are the mandatory integrity checks
    on the native produced binaries; `xray.linux_*_sha256` continues to pin
    prebuilt archives
  * closes the "release tag silently re-cut with different bytes" risk by
    pinning the exact Git commit and verifying the resulting binary; the build
    currently uses the distribution Go package and does not claim an
    independently pinned toolchain

When to flip it on: cohorts where supply-chain attestation is part of
the threat model (high-risk operators, audited deployments). Default
stays off; the prebuilt path is the v1 baseline.

## Revisit cadence

Re-read this page on every Xray-core minor bump and at the start of
each quarter. Stale rollout instructions are worse than no
instructions.

## Local XHTTP qualification

The optional bounded-pool delivery profile is restricted to the existing
v26.3.27 native Xray engine and its typed parser fields. It introduces no pin
upgrade or prerelease eligibility. Native mode and resource comparisons run in
`make test-xhttp-delivery-matrix`; external rollout and PQE HOLD remain separate.
See [delivery profiles](xhttp-delivery-profiles.md).
