# iOS client research for the deployed VPN fleet

**Research date:** 2026-07-13

**Evidence basis:** conclusions retained from the dated first-party review.
External citations and storefront geography are intentionally omitted; unstable
product facts must be revalidated before changing the supported-client policy.
No client secrets, UUIDs, REALITY keys, short IDs, Hysteria credentials,
AmneziaWG keys, or private subscription URLs are recorded here.

## Local client contract

The deployed fleet exposes four independent client paths. Its current release
and verification boundary are recorded in
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md); this client comparison does not
by itself prove path reachability.

| Profile | Public client surface | Required client capability |
|---|---|---|
| P0 primary | VLESS + REALITY + XTLS-Vision over TCP/443 | VLESS, REALITY, `xtls-rprx-vision` |
| P0 alternate | The same VLESS + REALITY + XTLS-Vision identity over TCP/2053 | The same capability plus selector-driven port failover |
| P1 HTTPS | VLESS + XHTTP behind nginx over TCP/443 | XHTTP transport and the emitted TLS settings |
| P2 QUIC | Hysteria2 over UDP/443 | Hysteria2, including the emitted TLS/obfuscation settings |
| P2 device VPN | AmneziaWG on its separate UDP listener | Native AmneziaWG parameters and a separately delivered per-device private key |

The repository-native `make emit-singbox CLIENT=<name>` path produces an official sing-box profile with `selector` and `urltest` outbounds for P0 REALITY and P2 Hysteria2. P0 TCP/443 and TCP/2053 are peers in those groups, so the client can move away from a policed port without changing the REALITY identity. P1 XHTTP is excluded because official sing-box has no XHTTP transport; it needs a client-specific Xray conversion. AmneziaWG remains a separate device-VPN artifact because its private key and obfuscation parameters do not belong in the generic proxy subscription. See [QUICKSTART.md](QUICKSTART.md) and [CLIENT-NOTES.md](CLIENT-NOTES.md) for the local generator contract.

## Decision

There are two valid recommendations, depending on whether one application or zero-conversion import is more important.

1. **Shadowrocket is the best single-app client by protocol coverage.** Its reviewed release history covers VLESS Vision, REALITY, XHTTP, Hysteria2, and AmneziaWG. The repository does not currently emit a Shadowrocket-native profile, however, so adopting it as the supported single-app path requires a new repo-native exporter with tests and snapshots. Manual conversion of secret-bearing profiles is not an acceptable durable operator workflow.
2. **Hiddify is the best drop-in client for the standard repository output.** Hiddify accepts sing-box profiles and can consume the P0/P2 selector-plus-urltest JSON directly. P1 still needs a separate, tested Xray-family conversion; importing the RIPDPI bundle is not supported. Use the official Amnezia client separately for AmneziaWG.

For immediate deployment, prefer **Hiddify + the official Amnezia client**. Treat **Shadowrocket** as the target single-app experience after a repository-owned exporter exists and its output is exercised against all four live paths.

## Evidence matrix

Legend: **yes** means explicitly supported in a first-party source; **partial** means the source confirms a related feature but not the complete local contract; **unknown** means no first-party confirmation was found; **no** means the feature is absent or an official project response declines it.

| Client | REALITY + Vision | XHTTP | Hysteria2 | AmneziaWG | Import and automation | Source transparency | Fit for this fleet |
|---|---:|---:|---:|---:|---|---|---|
| Shadowrocket | yes | yes | yes | yes | Own configurations and subscriptions; system tunnel; VPN on-demand appears in reviewed version history | Closed implementation; no official source repository identified | Best protocol-complete single app, but needs a repo-native exporter |
| Hiddify Proxy & VPN | yes | yes | yes | partial | Sing-box, V2ray/Xray, Clash, deep-link subscriptions; TUN mode and automatic subscription updates | Open source | Direct import for standard P0/P2 JSON; P1 needs conversion; pair with official Amnezia for AWG |
| Happ - Proxy Utility | yes | yes | yes | no | URI, QR, standard/encrypted subscriptions, raw Xray JSON, and TUN settings | Public repository exposes a README but not the iOS implementation | Strong Xray/Hysteria alternative, but not a single-app AWG solution |
| Karing | yes | yes | yes | no | Clash, V2ray, Sing-box, Stash and other subscriptions; TUN and automatic reconnect | Open source | Viable open-source proxy client; AWG requires another app |
| Stash | yes for TCP-REALITY | no first-party XHTTP support found | yes | no first-party support found | Scheduled configuration updates, StashTun, and VPN On Demand | Closed implementation | Excellent rule engine, but not complete for the local transport set |
| Streisand | yes | unknown | yes | unknown; only WireGuard is listed | Rule-based system VPN; generic subscription and on-demand contracts are not documented clearly | Closed implementation | Insufficient first-party evidence for XHTTP and AWG |
| AmneziaVPN | yes | no first-party support found | no first-party support found | yes | Native Amnezia configuration sharing/import and system VPN | Open source | Correct dedicated AWG client and an optional REALITY client, not the main multi-transport selector |
| FoXray, legacy App Store ID 6448898396 | unknown | unknown | historical claims are not enough for a current recommendation | unknown | unknown | No current official implementation source identified | Do not select; current availability is unverified |

## Repository evidence record

### Shadowrocket

The reviewed Shadowrocket release history records XHTTP connection management,
a Hysteria2 stream-closure fix, AmneziaWG magic-header processing, VLESS Vision,
TUN shortcuts, and a VPN on-demand fix.

The protocol evidence is strong, but the app does not publish a source repository or a stable documented native profile schema that this repository already emits. A Shadowrocket recommendation therefore creates implementation work here: add a secret-safe exporter, fixtures for P0/P1/P2 and AWG, schema/snapshot tests, and an import-and-connect acceptance run on iOS.

### Hiddify

The Hiddify App Store page explicitly lists XHTTP, VLESS with XTLS REALITY and Vision, Hysteria2, profile links, and iOS VPN-service routing. The official Hiddify repository states that the client is based on Sing-box, supports iOS, TUN mode, Sing-box/V2ray/Clash subscription formats, remote profiles, and automatic subscription updates. Its public source and release history make protocol and parser behavior auditable.

The official history includes an ambiguous `add amnezia` entry but does not establish that the current iOS build consumes this fleet's complete AmneziaWG configuration. Do not collapse AWG into the Hiddify recommendation without a physical import and handshake test. Keep AWG in the official Amnezia client.

### Happ

Happ's official link and parameter documentation confirms VLESS, Hysteria2, URI and QR import, standard subscriptions, JSON arrays, and direct pass-through of raw Xray JSON. Its application-management documentation includes a REALITY URI with `xtls-rprx-vision`, XHTTP-specific settings, and TUN selection parameters. The App Store page confirms active Xray-core and Hysteria2 maintenance.

The official issue tracker still contains an open request to add AmneziaWG support, so Happ is not a protocol-complete single-app choice. The published iOS repository contains only a README and is not implementation-level source transparency.

### Karing

The Karing App Store page documents Clash, V2ray, Stash and Sing-box subscriptions, configuration synchronization, and import/export. In the official tracker, the maintainer explains how to configure XHTTP, and the official releases record subsequent XHTTP improvements and iOS tunnel/reconnection work. The project publishes its implementation in the KaringX organization.

The maintainer closed the reviewed AmneziaWG feature request with `no plan`,
so Karing cannot replace the dedicated AWG client.

### Stash

The official Stash protocol documentation documents Hysteria2 and VLESS with REALITY options and Vision flow. The iOS 3.4.0 release notes add VLESS-TCP-REALITY and describe the rebuilt StashTun. The first-party on-demand documentation and service-provider subscription documentation confirm VPN On Demand and scheduled profile refresh.

No first-party Stash documentation found in this research establishes XHTTP or AmneziaWG support. Stash is therefore not complete for this fleet even though its iOS automation and rule engine are strong.

### Streisand

The Streisand App Store page explicitly lists VLESS with REALITY, Hysteria2, TUIC, and WireGuard. It does not name XHTTP, Vision flow, or AmneziaWG, and no official implementation repository or detailed profile schema was identified. Treat the missing capabilities as unknown rather than assuming that a bundled core exposes them.

### AmneziaVPN

The Amnezia protocol documentation explicitly supports AmneziaWG and XRay VLESS REALITY. The official client repository publishes the desktop and mobile implementation, and the release history records current iOS Xray fixes and split-tunneling work. The App Store page describes the app as a free open-source multi-protocol client.

AmneziaVPN does not document XHTTP or Hysteria2 as supported client profiles, so it is the dedicated AWG companion in the recommended two-app mode, not the selector client.

### FoXray and the `Itchy` name

The legacy FoXray identifier returned no result in the reviewed lookup checks.
A newer listing used a different identifier and described a generic server
service rather than the legacy Xray configuration client. It is not evidence
that the legacy client remains available.

No first-party Apple or project source identified a proxy/VPN client named `Itchy` or `iTachy`. Apple's exact-name search surfaces the unrelated Itchy for Scratch. The intended name may have been Hiddify, but that must not be silently assumed in operator documentation.

## Required follow-up for a supported Shadowrocket path

1. Define a Shadowrocket-native export contract owned by this repository; do not make a third-party converter part of the secrets path.
2. Emit P0 TCP/443 and TCP/2053, P1 XHTTP/TCP/443, P2 Hysteria2/UDP/443, and the per-device AWG profile without reusing credentials across devices.
3. Preserve automatic selection semantics equivalent to the current sing-box `selector` plus `urltest`, or document an explicit limitation if Shadowrocket cannot represent the same health-selection policy.
4. Add fixtures, schema validation, snapshots, and secret scanning to the existing generator test surface.
5. Run physical iOS import and data-plane tests through every profile before changing the recommended client in operator-facing documentation.
