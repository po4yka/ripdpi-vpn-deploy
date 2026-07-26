# Android client research for the deployed VPN fleet

**Research date:** 2026-07-13

**Last refreshed:** 2026-07-26

**Evidence basis:** conclusions retained from the dated first-party review and
local sibling-project inspection. External citations are intentionally omitted;
unstable product facts must be revalidated before changing the supported-client
policy. No client secrets, UUIDs, REALITY keys, short IDs, Hysteria credentials,
AmneziaWG keys, or private subscription URLs are recorded here.

## Local client contract

The deployed fleet exposes four client paths and one repository-native aggregate profile:

| Profile | Public client surface | Required Android capability |
|---|---|---|
| P0 primary and alternate | VLESS + REALITY + XTLS-Vision over TCP/443 and TCP/2053 | VLESS, REALITY, `xtls-rprx-vision`, and selector-driven port failover |
| P1 HTTPS | VLESS + XHTTP behind nginx | XHTTP transport with the emitted TLS settings |
| P2 QUIC | Hysteria2 over UDP/443 | Hysteria2 plus emitted TLS and Salamander metadata |
| P2 device VPN | AmneziaWG on its separate UDP listener | Native AmneziaWG parameters and a separately delivered per-device private key |

`make emit-bundle CLIENT=<name>` emits standard sing-box JSON with `selector` and `urltest` outbounds, plus the top-level `ripdpi` extension containing AmneziaWG, Hysteria2, topology, and expiry metadata. The AWG private key remains separate and device-local. A generic sing-box client can consume the standard portion, but only a client implementing the repository contract can preserve the whole bundle without conversion.

## Decision

**RIPDPI is the best Android client for this configuration by architecture and feature fit.** It is the only evaluated client that understands the repository's `ripdpi-bundle` contract, preserves selector/url-test failover, imports the AWG metadata while keeping the per-device private key separate, and exposes one Android `VpnService` for all paths. Its current source also declares Always-on VPN support and implements Android per-app allow/deny routing.

**Do not make the public v0.1.3 APK the production default yet.** The official v0.1.3 release already includes standalone AmneziaWG, REALITY/Vision, XHTTP, Hysteria2, selector/url-test subscriptions, protected sockets, encrypted secrets, checksums, SBOMs, and provenance. However, the hardened RIPDPI `main` line is now hundreds of commits ahead of v0.1.3 and contains later Android lifecycle, fail-closed, root-helper, privacy, REALITY, and UDP-startup fixes. A physical non-rooted Pixel 7 has since passed standalone AWG interoperability, full-tunnel TCP, UDP DNS, STUN, MapDNS, and live Hysteria2-to-AWG failover. The remaining release gates are a signed candidate plus network-path diversity, cellular handover, long-duration soak, and IPv6 differential leak testing on an underlying path with a working IPv6 default route.

**For installation today without building an unreleased client, use two applications:** import the standard sing-box portion into **sing-box for Android (SFA)** or **Hiddify**, and import the separately generated AWG profile into the official **AmneziaWG** client. SFA is the closest representation of the emitted standard JSON; Hiddify has the friendlier mass-market UI and automatic profile management. Neither understands the `ripdpi` extension, so both lose the one-bundle AWG lifecycle and need a second app.

Hiddify requires a specific P1 acceptance test before it can be the preferred generic client. The project emitter currently creates an XHTTP transport without an explicit `mode`, while the official Hiddify issue tracker records that v4.1.1's sing-box backend resolves `auto` incorrectly and can break bidirectional uploads. P0 REALITY and P2 Hysteria2 remain valid fallback paths, but P1 must not be assumed healthy from import success alone.

## Ranking

| Rank | Client | Best use here | Main limitation |
|---:|---|---|---|
| 1 | RIPDPI, next hardened release | One-app production target with exact bundle semantics, AWG, automatic failover, per-app routing, Always-on, and lockdown | Current public v0.1.3 substantially predates the hardened main line; signed release and remaining handover, soak, and IPv6 differential gates are required |
| 2 | SFA + official AmneziaWG | Most literal ready-now consumption of standard sing-box JSON plus a dedicated AWG tunnel | SFA describes itself as experimental; no `ripdpi` extension or unified AWG lifecycle |
| 3 | Hiddify + official AmneziaWG | Best ready-now usability and subscription management | Known XHTTP `auto` regression requires P1 data-plane testing; no `ripdpi` extension |
| 4 | Happ + official AmneziaWG | Strong Xray-oriented UI and explicit REALITY/XHTTP/Hysteria2 support | No native AWG or repository-bundle support; less faithful to sing-box selector semantics |
| 5 | Karing + official AmneziaWG | Open-source sing-box/Clash alternative | Maintainer has declined native AmneziaWG; use a second app |
| 6 | v2rayNG + official AmneziaWG | Focused Xray client for individual VLESS links | Does not preserve the aggregate sing-box selector/url-test and `ripdpi` metadata |
| 7 | NekoBox | No recommended role | Official project warns against the Google Play build and documents that routing rules in sing-box configs are ignored |

## Repository evidence record

### RIPDPI

The official RIPDPI v0.1.3 release documents standalone AmneziaWG, REALITY/Vision, XHTTP, Hysteria2, selector/url-test subscription failover, per-socket `VpnService.protect()`, encrypted secrets, and signed release artifacts with checksums, SBOMs, and provenance. The official repository contains the parser and deployment integration used for the sibling bundle contract.

The locally inspected source declares `android.net.VpnService.SUPPORTS_ALWAYS_ON=true`, implements per-app routing through `VpnService.Builder.addAllowedApplication` and `addDisallowedApplication`, parses the `ripdpi` extension, and contains the native standalone AWG runtime. The repository-owned [Pixel 7 live-client matrix](measurements/pixel7-live-client-matrix-2026-07-15.md) records physical AWG and failover PASS. Its bounded IPv6 differential, network-handover, and soak gaps, together with the post-v0.1.3 commit distance, remain release-readiness evidence rather than claims about third-party products.

### Android platform behavior

The official Android VPN guide states that Android 7.0 and later can keep a VPN always on, Android can block connections outside the VPN, and VPN applications must preserve configuration when the system starts them. The official `VpnService.Builder` reference confirms that an app can use either an allowed-application set or a disallowed-application set, but not both simultaneously. These OS controls make RIPDPI's single-`VpnService` design materially better than switching between two VPN apps: Android permits only one active VPN service at a time.

Enable **Always-on VPN** and **Block connections without VPN** only after verifying boot reconnect, network changes, and every required profile on the physical device. Per-app exclusions intentionally bypass the VPN and therefore conflict with a strict no-leak posture.

### sing-box for Android

The official sing-box for Android repository describes SFA as an experimental Android client for sing-box. Its principal advantage here is format fidelity: the deploy repository already emits a valid sing-box configuration with selector and URL-test groups. It does not implement the project-specific `ripdpi` object or its separate-key AWG workflow, so it remains a two-app solution.

### Hiddify

The official Hiddify repository describes an open-source sing-box-based client with Android support, TUN mode, automatic node selection, remote profiles, automatic subscription updates, and Sing-box, V2ray, and Clash imports. The Google Play listing confirms current Android distribution and support for VLESS/Reality/Vision and Hysteria2.

The official XHTTP `auto` regression report documents bidirectional upload failures on Hiddify v4.1.1 when the sing-box backend falls through to `packet-up`; the recorded workaround is to use VLESS TCP REALITY or Hysteria2. Because this fleet emits XHTTP without an explicit mode, validate P1 with an upload and download test rather than a TCP handshake alone.

### AmneziaWG

The official AmneziaWG Google Play listing provides the dedicated Android client and reports no data collection or sharing in its Play data-safety disclosure. It is the correct ready-now companion for the repository's generated AWG configuration, but it cannot be active simultaneously with another Android VPN client; switching to AWG replaces the active proxy VPN session.

The repository's existing client notes record a loopback/tunnel-fingerprint concern around AmneziaWG per-app exclusions. Treat per-app exclusion as a compatibility feature, not as a privacy boundary; use a separate Android Work Profile or router-level deployment where an application must never observe the VPN interface.

### Happ, Karing, v2rayNG, and NekoBox

Happ's official link and parameter documentation and application-management documentation cover VLESS/REALITY/Vision, XHTTP, Hysteria2, subscriptions, QR, and TUN controls. It remains a good manual Xray-family client, but it does not consume the repository extension or provide a verified native AWG path.

The official Karing repository provides an open-source sing-box/Clash client and current XHTTP work, while the maintainer closed the official AmneziaWG request with no implementation plan. The official v2rayNG repository is a maintained Xray-based Android client, but its link-oriented model is not the canonical representation of this repository's aggregate sing-box bundle.

The official NekoBox repository warns that the Google Play version has been controlled by a third party since May 2024 and is not open source. The same README says sing-box routing and diversion rules are ignored during import. Those two constraints disqualify it for this fleet.

## Production acceptance gate for RIPDPI

The physical transport, AWG, routing, leak, and failover baseline is complete in the [Pixel 7 live-client matrix](measurements/pixel7-live-client-matrix-2026-07-15.md). The remaining release gates are:

1. Cut a signed candidate from the hardened current RIPDPI line; do not relabel v0.1.3 as equivalent to current `main`.
2. Build the release artifacts through the existing reproducible pipeline and verify signature, checksum, SBOM, and provenance before sideloading.
3. Import a freshly emitted per-device bundle through the subscription or deep-link path and supply the AWG private key only through the device-local prompt.
4. Repeat the physical matrix across distinct network paths, including cellular handover and a long-duration soak; keep sustained P1 upload/download and both UDP-capable and UDP-constrained behavior in scope.
5. Repeat IPv6 differential leak testing on an underlying path with a working IPv6 default route, and verify subscription refresh and expiry, boot reconnect, Always-on VPN, lockdown, and per-app policy with the signed candidate.
6. After those checks pass, publish the candidate as the supported Android client and keep SFA or Hiddify plus official AmneziaWG as the documented recovery path.
