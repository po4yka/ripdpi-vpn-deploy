# Android client research for the deployed VPN fleet

**Research snapshot:** 2026-08-08

**Scope:** Android clients for the P0/P1/P2 fleet recorded in
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md). This is a compatibility and
operational-readiness assessment, not evidence that every client has passed the
live acceptance matrix on the intended handset and network paths.

**Evidence policy:** this file retains only repository-owned compatibility
decisions and acceptance criteria. No external source reference, endpoint,
UUID, key, short ID, credential, client identifier, or private subscription URL
is recorded here.

## Current fleet contract

The deployment status is the source of truth for live convergence. This file
describes the current repository emitters and client contract; it does not turn
server-side verification into Android data-plane evidence.

| Profile | Deployed client surface | Android requirement |
|---|---|---|
| P0 primary and alternate | VLESS + REALITY + XTLS-Vision on TCP/443 and TCP/2053 | REALITY, `xtls-rprx-vision`, both ports, and failover between them |
| P1 HTTPS | VLESS + XHTTP behind nginx | XHTTP with the emitted TLS/path settings; the current emitter does not set an explicit XHTTP mode |
| P2 QUIC | Hysteria2 on UDP/443 | Hysteria2, UDP forwarding, emitted TLS metadata, and optional Salamander metadata |
| P2 device VPN | AmneziaWG on a separate UDP listener | Native AWG parameters and a separately delivered per-device private key |

`make emit-bundle CLIENT=<name>` produces the canonical
[RIPDPI bundle](RIPDPI-BUNDLE.md): standard sing-box JSON with concrete
outbounds plus `selector` and `urltest`, extended by the versioned `ripdpi`
object for AWG, Hysteria2 extras, topology, and expiry. The AWG private key is
not in the distributable bundle. Plain sing-box consumers must use the plain
subscription artifact; Xray-family consumers need link or Xray-config
conversion. Importing individual paths is not equivalent to preserving the
bundle's ordered selector and automatic failover policy.

Re-emit a fresh per-device bundle or client-specific profiles after every
credential, endpoint, cohort, or deployment change. A previously generated
artifact is not proof of the current rollout.

## Decision

### Production target

**RIPDPI `v0.1.4` is the primary production candidate and the best architectural
fit.** It is the only evaluated signed Android release that implements the
complete repository contract: P0/P1/P2 parsing, the `ripdpi` extension,
selector/url-test groups, AWG key separation, one `VpnService`, Android
Always-on support, and per-app allow/deny routing.

The release is tied by its receipt to source
`ac063853776a325772080a2b1b18de21ba4a33d3`, declares `versionName 0.1.4` and
`versionCode 12`, and publishes checksums plus Android/Rust SBOMs. Prefer the
ABI-specific signed APK and verify it against the release checksum before
installation. The inspected local `main` at `2044a11da331afed47bcefb907a538fca1493c53`
is 83 commits ahead of the tag and is not an authenticated replacement for the
release artifact. The target handset still needs the physical acceptance matrix
below before the rollout can be called device-proven.

### Ready-now third-party candidate

**INCY is the strongest ready-now one-app candidate on documented protocol
coverage, pending a physical-device acceptance run.** Its Android client can
import VLESS REALITY/Vision, XHTTP, Hysteria2, and native AmneziaWG `.conf` or
`amneziawg://`/`awg://` profiles. That covers all four live paths in one app,
but through separate or mixed Xray-oriented entries. INCY does not document the
sing-box `ripdpi-bundle` extension, and its Xray balancer/import model does not
preserve this repository's selector/url-test semantics. This is one-app manual
access, not proven cross-engine automatic failover.

Pin acceptance evidence to the exact APK manifest, signature, and digest.
Source-audit and privacy posture remain acceptance inputs rather than inferred
properties of a successful profile import.

### Recovery choices

**Hiddify plus the official AmneziaWG client** is a P0/P2 recovery path, not a
current P1 recommendation. Keep P1 out of this path until an exact APK proves
that its chosen import surface preserves the emitted XHTTP mode and passes
sustained upload and download.

**SFA plus the official AmneziaWG client** is the most literal P0/P2 recovery
path, not a complete fleet client. The repository now validates the emitted
standard P0/P2 document with a real SHA-256-pinned upstream `sing-box 1.13.16`
`check`. That proves parser compatibility of the generated JSON, not SFA UI,
import, Android runtime, or data-plane behavior. P1 XHTTP remains outside the
plain sing-box artifact. Neither two-app solution implements the `ripdpi`
extension or a unified AWG lifecycle.

**Happ plus the official AmneziaWG client** is a strong manual Xray-family
fallback. It covers the required Xray-family transports but does not establish
native AWG, raw bundle semantics, continuous ordered failover, or the required
Always-on/lockdown posture. Use it only after the same physical acceptance and
privacy review.

## Ranking for this fleet

| Rank | Client | Recommended role | Blocking limitation |
|---:|---|---|---|
| 1 | RIPDPI `v0.1.4` | Signed exact-contract production candidate | The intended handset and network paths still require the physical acceptance matrix; untagged `main` is not the release artifact |
| 2 | INCY `3.4.8` APK | Best third-party one-app candidate for manual P0/P1/P2/AWG access | No `ripdpi`/selector contract, no live fleet acceptance, and incomplete source-audit evidence |
| 3 | SFA + official AmneziaWG `2.0.1` | Standard P0 REALITY, P2 Hysteria2, and AWG recovery | P1 is absent from the standard artifact; two apps and no unified AWG lifecycle |
| 4 | Happ `4.0.1` + official AmneziaWG `2.0.1` | Manual Xray-oriented P0/P1/P2 recovery | Two apps; no proven bundle semantics, continuous failover, or documented Always-on posture |
| 5 | Hiddify `v4.1.1` + official AmneziaWG `2.0.1` | Manual P0/P2 recovery | Two apps; unresolved XHTTP import/runtime evidence excludes P1; no repository extension |
| 6 | Karing + official AmneziaWG | sing-box/Clash alternative | Native AWG is not accepted; still a two-app path |
| 7 | v2rayNG + official AmneziaWG | Individual Xray/VLESS links | Link-oriented import does not represent the canonical aggregate bundle |
| 8 | NekoBox | No recommended role | Routing and distribution provenance are not accepted for this fleet |

The ranking separates signed artifact availability, architecture fit, and live
proof. It does not promote the untagged RIPDPI `main` checkout over `v0.1.4`, or
promote documented third-party compatibility to fleet acceptance.

## Configuration workflow

Do not reuse a profile from another phone. For a new device, create one named
client with `scripts/new-client.sh <device>` and converge the updated encrypted
secrets before distributing any profile. The command prints the AWG private key
once; handle that terminal output as a secret and do not put it in a shared
subscription, ticket, screenshot, or tracked file.

For an existing, converged client, the repository-native outputs are:

```bash
make emit-bundle CLIENT=<device>   # RIPDPI only
make emit-singbox CLIENT=<device>  # standard sing-box P0/P2 document
make emit-awg CLIENT=<device>      # AWG template; insert the device key locally
```

Use a local ignored file with mode `0600` only for the short transfer window,
then delete the transfer copy after the app has imported it. The current
repository has no INCY, Happ, Hiddify, or v2rayNG exporter; those clients need a
deliberate client-specific conversion and therefore cannot be configured by
feeding them `emit-bundle` unchanged.

### INCY

1. Import P0 as two VLESS entries sharing that device's identity and REALITY
   parameters: raw TCP, `xtls-rprx-vision`, uTLS `chrome`, with the primary and
   alternate ports kept as separately named profiles.
2. Add P1 as a separate VLESS XHTTP entry with the emitted TLS server name,
   host, and private path. Record the effective XHTTP mode during acceptance;
   import success alone is insufficient.
3. Import P2 Hysteria2 with the emitted authentication, TLS name, and only the
   Salamander or port-hopping fields that are present in the current artifact.
4. Import the AWG `.conf` locally after inserting the per-device private key.
   Do not publish the resulting mixed profile as a remote subscription.
5. Keep the four paths separately selectable until a physical test proves the
   intended INCY balancer behavior. Do not label this setup automatic
   P0-to-P1-to-P2-to-AWG failover.

### Happ and v2rayNG

Create separate Xray-family profiles for P0 primary, P0 alternate, P1 XHTTP,
and P2 Hysteria2. Happ's `lowestdelay` option is suitable for a launch-time
choice, not for reproducing the repository's ordered failover. Keep AWG in the
official AmneziaWG application and expect manual VPN switching. For Happ, use a
proxy-level latency test rather than TCP-connect latency, then verify sustained
P1 upload and download. v2rayNG is preferable when a small, auditable set of
individual Xray entries is more important than a unified UI.

### Hiddify, SFA, and Karing

- Hiddify should receive only P0/P2 until an exact APK and import method prove
  that XHTTP mode survives conversion. Do not infer P1 health from successful
  import or latency. AWG remains a separate official-client profile.
- SFA should receive the repository's standard P0/P2 sing-box artifact. Its
  pinned CLI check is a format gate only; repeat REALITY and Hysteria2 data-plane
  tests in SFA on the physical device. AWG remains a separate official-client
  profile.
- Karing is an experimental fallback until raw-profile preservation and XHTTP
  behavior pass the same physical matrix. It also needs the separate AWG app.

### Android system settings

Use Android VPN mode, not a local proxy mode. Grant any foreground-service or
notification permission required for reliable background operation, exempt the
chosen primary client from vendor battery killing, and leave only that client
configured as Always-on. Enable **Block connections without VPN** only after
boot, handover, reconnect, and leak checks pass. A dedicated AWG fallback cannot
take over while another app's lockdown remains active.

## RIPDPI posture at the snapshot

The official `v0.1.4` release is an immutable exact-SHA candidate with
ABI-specific and universal APKs, checksums, Android/Rust SBOMs, and a release
receipt. Its tagged source documents standalone AWG, REALITY/Vision, XHTTP,
Hysteria2, selector/url-test subscription import, per-socket
`VpnService.protect()`, encrypted secrets, and cross-transport failover. The
tagged source at `ac063853776a325772080a2b1b18de21ba4a33d3`:

- parses the `ripdpi.amneziawg`, Hysteria2-extra, topology, and expiry fields;
- promotes sing-box `selector` and `urltest` entries into a persisted failover
  group rather than treating them as ordinary nodes;
- declares `android.net.VpnService.SUPPORTS_ALWAYS_ON=true`;
- applies either `addAllowedApplication` or `addDisallowedApplication` to the
  Android VPN builder, never both;
- was published with receipt-bound source provenance, signed builds, checksums,
  Android/Rust SBOMs, and update metadata.

The repo-owned [Pixel 7 live-client matrix](measurements/pixel7-live-client-matrix-2026-07-15.md)
proves that an earlier hardened source snapshot passed live REALITY primary and
fallback, XHTTP, Hysteria2, AWG, routing, leak, and Hysteria2-to-AWG failover
checks on a physical non-rooted device. It does **not** prove `v0.1.4` on the
intended handset, nor the current 83-commit-ahead local `main`. The remaining
acceptance gaps are exact-release installation on the target device,
network-path diversity, cellular handover, long-duration soak, and
**IPv6 differential** testing on an underlay with a working IPv6 default route.

## Android platform constraints

Android permits one active VPN service per user or work profile; starting a
second VPN app stops the first. Always-on VPN is available from Android 7.0 and
can block connections outside the VPN. Android per-app policy supports either
an allow set or a disallow set, not both on the same VPN interface.

Therefore:

- a one-app client is materially safer for automatic failover than switching
  between a proxy VPN and a dedicated AWG app;
- enable **Always-on VPN** and **Block connections without VPN** only after boot
  reconnect and every required path pass on the physical device;
- an excluded app intentionally uses the underlying network, so per-app bypass
  conflicts with strict no-leak lockdown;
- documentation or import success alone cannot establish Always-on, lockdown,
  handover, or leak behavior.

## Required physical acceptance matrix

Run this matrix with freshly emitted, per-device material and record only
redacted results:

1. Verify the APK provenance, signature, manifest version, and exact digest.
2. Import P0 primary and alternate; exercise bidirectional traffic on both TCP
   ports and force failover in each direction.
3. Exercise P1 XHTTP with sustained download and upload, not only connect or
   latency checks; record the effective XHTTP mode.
4. Exercise P2 Hysteria2 with TCP, UDP DNS, and a stable UDP echo/STUN target on
   both UDP-capable and UDP-constrained networks.
5. Import the per-device AWG configuration without placing the private key in a
   shared subscription; verify TCP, UDP DNS, MTU-sensitive traffic, reconnect,
   and server-side handshake counters.
6. Force runtime loss of each active path and distinguish manual selection,
   launch-time fastest-node selection, and continuous automatic failover.
7. Verify Always-on boot start, lockdown, app/process death, screen-off behavior,
   per-app routing, DNS/WebRTC leakage, cellular/Wi-Fi handover, IPv4/IPv6
   differential behavior, and a long-duration soak.
8. Re-run the matrix after subscription refresh and expiry handling.
