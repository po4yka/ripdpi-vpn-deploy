# Client-side known issues and version pins

The server stack is only one half of the story. These items are
client-side, but the operator distributing clients should know about
them because a vulnerable client undoes the server's protections.

## AmneziaWG Android split-tunnel localhost leak (issue #2457)

Status: **open, unresolved** as of 2026-05-09. Source:
`mobile-platform-enforcement/wiki/concepts/amneziawg-android-split-tunnel-localhost-vuln`.

Apps placed on AmneziaWG 2.0 Android's per-app split-tunnel exclusion
list can still reach `127.0.0.1` and probe the VPN tunnel interface
from there. A detection-capable app (banking app, marketplace, etc.)
that is excluded from the VPN to satisfy an IP-origin check can still
fingerprint that an AWG tunnel is active on the device.

Mitigations until upstream lands a fix:
- Use Android Work Profile (Shelter) — full sandbox separation makes
  the loopback probe path inaccessible.
- Use router-level VPN instead of per-device — no local tunnel
  interface on the phone.
- Do not rely on per-app exclusion to satisfy an IP-origin check on
  Android 2.0 AmneziaWG clients.

The desktop and iOS AmneziaWG clients are not affected.

## NaiveProxy padding leak in sing-box <=1.13.7

Status: **fixed**. Pin clients at sing-box >= 1.13.8 (2026-04-14) or
NaiveProxy-via-cronet-go with the analogous fix.

Older sing-box NaiveProxy implementations allocated padding buffers
from a shared pool without zeroing on reuse, leaking domain names and
request fragments from previous tunnel users into another user's
padding. The privacy and detection consequences are both serious —
patterned padding distinguishes sing-box NaiveProxy from genuine
Chromium traffic, and on a multi-tenant relay the leak crosses user
boundaries. Refs: sing-box PR #4001, issue #4002, cronet-go PR #7.

When emitting client configs via `make emit-singbox`, ensure the
target client binary is recent enough. The server bundle does not
ship clients, but the QUICKSTART and SUBSCRIPTION-PLANE docs should
point operators at the minimum versions.

## NaiveProxy v147 preamble injection (clients should run >= v147)

NaiveProxy v147.0.7727.49-3 (released 2026-05) and the follow-on
v148.0.7778.96-2 (2026-05-02) inject realistic Chrome HTTP/2 preambles
derived from the fronting Caddy site's root page. The server-side
`naive` role's Caddyfile already ships the compression headers a real
Chrome browser would trigger (`encode zstd gzip`, ERROR-only access
log) so the preambles look organic.

Operationally: the feature is on by default in v147+. Older clients
still work but lose the preamble cover.

## VLESS desktop client VPS-IP exposure (2026)

Refs: `transport-protocols/wiki/concepts/vless-client-desktop-ip-exposure-2026`.

The VPS exit IP is observable from a desktop client process by an
attacker with code-execution rights on the device (telemetry SDKs,
ad libraries, certain installer wrappers). This is a client-side
defect; nothing the server can do about it. Audit the client binary's
network behaviour before distributing to a high-risk cohort.

## VLESS Android SOCKS5 client exposure

Refs: `transport-protocols/wiki/concepts/vless-client-android-socks5-exposure`.

Some VLESS Android clients expose a local SOCKS5 listener that
non-VPN apps on the same device can reach. This is functional design
for per-app routing, but it lets a detection-capable app determine
that a proxy is running by probing the local port. Per-app routing
should be configured via packageNameRegex (see the wiki page) rather
than via app-side SOCKS5.

## VLESS+REALITY alt-port roll-over (xray_fallback_port)

The server stack ships a secondary VLESS+REALITY+Vision inbound on a
non-443 port by default. The Ansible variable is `xray_fallback_port`
(default 2053; set to 0 to disable). The default value matches one of
the published Cloudflare alternate HTTPS ports, so the listener looks
indistinguishable from any other HTTPS endpoint to a censor.

When `make emit-singbox CLIENT=name` runs, every `xray_fallback_port`
≠ 0 ≠ `xray_port` adds a second outbound to the emitted bundle. The
two outbounds share the same Reality identity (private key, server
names, short IDs); only the port differs. The selector + urltest
group treats them as peer endpoints, so a client whose port-443 path
gets policed by a TLS-handshake-count rule on the home ISP can roll
over to the alt-port automatically.

Operationally:

- The alt-port is itself a finite resource. Rotate `xray_fallback_port`
  before clients begin seeing the same policing pattern on it.
- A multi-cohort deploy (`xray.cohorts` non-empty in secrets) bypasses
  the default fallback and uses the operator-defined cohort ports
  instead.
- The firewall role already opens both ports; no manual nftables
  edits are needed when toggling the fallback on or off.

## v2rayN-class clients: prefer the sing-box bundle

When `make emit-singbox CLIENT=name` is available, prefer the sing-box
JSON output over manual VLESS URI strings. The bundle wires every
enabled transport into a single selector + urltest group, which
matters for the home-ISP TLS policing failure mode (commits in this
repo add a `xray_flow_mode: mux` toggle; selectors let the client
gracefully roll over to the working profile).
