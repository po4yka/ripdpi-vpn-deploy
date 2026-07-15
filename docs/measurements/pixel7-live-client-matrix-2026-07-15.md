# Pixel 7 live-client VPN matrix — 2026-07-15

## Verdict

PASS with one bounded IPv6 coverage gap.

A physical, non-rooted Pixel 7 established real VPN tunnels against the
deployed three-cohort infrastructure and completed the transport, routing,
leak, security, and failover matrix below. The final runtime-failover replay
kept the Android foreground VPN service connected while switching from a
failed Hysteria2 relay to AmneziaWG, then carried TCP, DNS, and STUN traffic.

This report is intentionally redacted. It contains no server address, public
client address, SSID/BSSID, device serial, credential, key material, SNI,
profile UUID, or generated client configuration.

## Measurement metadata

| Field | Value |
|---|---|
| Measurement window | 2026-07-14 through 2026-07-15 |
| Client | Physical Pixel 7, arm64, Android API 37 |
| Device posture | Non-rooted; normal `VpnService` path |
| Network vantage | Residential Wi-Fi; operator and geography omitted |
| App variant | `githubSimpleDebug`, real arm64 JNI libraries |
| Infrastructure | Three logical cohorts: two TCP/Reality paths and one UDP/AWG path |
| App source head | `457a94174` |
| Deploy source head before this report | `281a063` |
| Push performed | No |

## Redacted observed data

Only aggregate verdicts are committed. Packet captures, logcat, Ansible
output, generated client assets, protobuf settings, and resolved addresses
remained ephemeral local artifacts.

### Transport matrix

| Transport/path | Physical-device exercise | Result |
|---|---|---|
| VLESS + Reality primary | Real TLS/Vision tunnel and HTTPS traffic | PASS |
| VLESS + Reality fallback | Primary unavailable; fallback cohort selected and carried traffic | PASS |
| VLESS over xHTTP | Real xHTTP session; first downstream response handled lazily | PASS |
| Hysteria2 IPv4 | TCP, SOCKS UDP DNS, and STUN through the live relay | PASS, 4/4 each in final healthy baseline |
| Hysteria2 IPv6 | IPv6 listener/tunnel path | PASS, 5/5 |
| AmneziaWG | Native tunnel, TCP, UDP DNS, STUN, and MapDNS | PASS |
| AmneziaWG after failover | Replacement session after live Hysteria2 outage | PASS: TCP 4/4, DNS 4/4, STUN 4/4 |

The first STUN endpoint used after failover received two outbound copies of
the request on the server (AWG ingress plus uplink egress) but returned no
reply. Two independent alternative STUN endpoints responded; a stable one was
then repeated 4/4. This isolates the initial 0/4 result to endpoint response
behavior rather than loss inside the AWG tunnel.

### Routing matrix

| Mode | Observation | Result |
|---|---|---|
| Direct baseline | Curated 20-domain cohort | PASS, 20/20 |
| AWG full tunnel | Same 20-domain cohort through the VPN | PASS, 20/20 |
| Full-tunnel raw UDP | DNS and STUN with WebRTC protection disabled | PASS |
| Split exclude | Excluded test UID stayed on the direct path; expected HTTP status observed | PASS |
| Split include | Included test UID used synthetic MapDNS plus the VPN path | PASS |
| Split include UDP | DNS and STUN through the included path | PASS |
| MapDNS cross-session | Synthetic mapping reused after a session boundary without flow collision | PASS |

### Leak and security matrix

| Check | Observation | Result |
|---|---|---|
| Plaintext DNS leak | Fresh name resolved while AWG was active; server capture saw zero AWG-interface UDP/53 packets | PASS |
| WebRTC protection | STUN blocked while raw UDP DNS and TCP/443 remained usable | PASS |
| IPv4 full-tunnel routing | Client traffic used the VPN egress | PASS |
| IPv6 leak posture | Underlying Wi-Fi had a global IPv6 address but no IPv6 default route; the IPv4-only VPN blocked IPv6 | PASS for blocking; differential leak test not available |
| Secret/log hygiene | No committed endpoint, public IP, device/network identifier, or credential | PASS |

The IPv6 limitation is material: this vantage could not prove a
direct-IPv6-works / VPN-IPv6-blocked differential because the underlying
network did not provide an IPv6 default route. The tested VPN posture was
fail-closed for the unconfigured family.

### Failover matrix

| Scenario | Evidence | Result |
|---|---|---|
| Cold-start selection | Both Reality cohorts stopped before connect; Hysteria2 selected and carried traffic | PASS |
| Healthy anti-flap | SOCKS-bound confirmation returned DNS 4/4, TCP 3/4, STUN 4/4; no switch occurred | PASS |
| Runtime outage detection | Hysteria2 server stopped; six independent SOCKS/TCP sessions failed | PASS, 6/6 failures observed |
| Debounced switch | Passive failure streak plus active SOCKS egress confirmation selected AWG | PASS |
| Android lifecycle | Old relay stopped, replacement VPN started, UI stayed `Connected`, foreground service remained present | PASS after fix |
| Post-switch traffic | AWG TCP 4/4, DNS 4/4, stable alternate STUN 4/4 | PASS |
| Recovery | Hysteria2 and both Reality services restored active after the test | PASS |

## Defects found and repaired

### Android/Rust client repository

| Commit | Repair |
|---|---|
| `b0ad8d0dc` | Preserve every seeded failover candidate. |
| `69af2e961` | Authenticate the tunnel's SOCKS DNS resolver. |
| `693438fde` | Keep generated routes when a relay is active. |
| `7c0e4e1ec` | Interoperate with live VLESS Reality servers. |
| `1c81bdea8` | Preserve raw bytes at the Vision splice. |
| `b9c11789b` | Preserve the relay selected by the initial race. |
| `818daae9e` | Defer xHTTP/VLESS response validation until downlink data. |
| `0baf8eb6d` | Wait for Android UDP readiness in Hysteria2. |
| `c00de5d2b` | Retain UDP flows during UID attribution. |
| `fb97d3663` | Interoperate with the live AmneziaWG peer. |
| `3b2af0b6f` | Align the VPN and AWG SOCKS endpoints. |
| `115663f86` | Preserve MapDNS flow identity. |
| `b6efe82d2` | Prevent stale MapDNS entries across sessions. |
| `2ac060c7b` | Enforce WebRTC protection inside the tunnel. |
| `f759c8baa` | Race Hysteria2 without unsupported obfuscation. |
| `5d7f4ad9f` | Preserve a newer Android service start when an older stop completes. |
| `353cfbdaa` | Use consecutive relay-session failures as a trigger and confirm the active SOCKS egress before switching. |
| `457a94174` | Update the chained-VLESS negative test for lazy response validation. |

The service lifecycle bug was reproduced on the production app graph before
the fix: the failover configuration advanced to AWG, but an older
`stopSelf()` fallback killed the replacement start and left the UI
disconnected. The regression test now pins the Android `stopSelfResult(false)`
contract: `false` means a newer start exists and must be preserved.

### Deployment repository

| Commit | Repair |
|---|---|
| `ec693af` | Keep the old Xray process active until refreshed geodata is ready. |
| `6fa3c3b` | Make the firewall the sole owner of AWG client masquerading. |
| `281a063` | Refresh repository governance counts discovered by the broad gate. |

The live AWG config no longer contains `PostUp`/`PostDown` NAT hooks. After an
AWG restart and firewall reload, the live `inet nat postrouting` chain
contained exactly one AWG masquerade rule.

## Validation evidence

### Client repository

- `./gradlew :app:assembleGithubSimpleDebug --no-daemon` — `BUILD SUCCESSFUL`
  with the real arm64 native build path enabled.
- `./gradlew -Pripdpi.skipNativeBuild=true staticAnalysis testDebugUnitTest --no-daemon`
  — `BUILD SUCCESSFUL` in 6m 13s; 822 tasks, 153 executed.
- Targeted `FailoverCoordinatorTest` and `ServiceStopSelfTest` — PASS.
- `:app:ktlintCheck :core:service:ktlintCheck` — PASS.
- `cargo nextest run -p ripdpi-relay-core --locked` — 128/128 PASS.
- Commit hooks — architecture delta 0, native contracts 0 violations,
  rustfmt PASS, clippy with warnings denied PASS, secret scan PASS.

### Deployment repository

- `make test-unit snapshot-check` — 594 passed, 1 documented skip; 72/72
  rendered templates match goldens.
- `pytest -q tests/unit/test_firewall_egress_policy.py` — 9/9 PASS.
- Live remote checks — both Reality services active, Hysteria2 active,
  AmneziaWG active, AWG config has zero NAT hooks, firewall has one AWG
  masquerade rule.

## Residual risks and non-claims

- No carrier/geographic diversity, cellular handover, throughput benchmark,
  or long-duration soak was performed in this run.
- IPv6 leak behavior should be repeated on a vantage with a working underlying
  IPv6 default route.
- A non-responsive STUN endpoint is not treated as proof that UDP is broken;
  packet counters plus two responding alternatives and a stable 4/4 replay
  were used instead.
- No push, release publication, production credential rotation, or destructive
  infrastructure action was performed.

## Redaction checklist

- [x] No client or server public IP.
- [x] No server hostname, SNI, or port mapping.
- [x] No SSID, BSSID, device serial, carrier, geography, or operator label.
- [x] No private/public key, UUID, password, token, or full profile identifier.
- [x] No generated client JSON, protobuf payload, packet payload, or raw log.
- [x] Only aggregate counters and repository commit identifiers are retained.
