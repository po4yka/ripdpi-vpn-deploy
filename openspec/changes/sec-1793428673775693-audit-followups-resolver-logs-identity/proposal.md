# Change: Close the remaining traffic-privacy audit findings

Task ID: `SEC-1793428673775693`

## Why

The follow-up audit items left open by `SEC-1793386547449444` still expose
recipient metadata or fleet identity. The egress normalizer and the Xray
frontend resolve recipient names through plaintext UDP/53 to public resolvers,
so the hosting network sees every destination name. The decoy and self-steal
nginx sites log client addresses and user agents of real visitors. The
borrowed REALITY target is validated once at deploy time but never watched, so
a site that drops h2 or X25519 later leaves the node answering a handshake the
real site cannot give. A WireGuard-shaped AmneziaWG instance (`S1 = S2 = 0`,
`H1..H4 = 1,2,3,4`) is deployable on production without the measurement that
the cohort reference requires. REALITY inbounds listen on IPv4 only while the
decoy listens dual-stack, and two deliberate decisions (no I1-I5 programs,
identical Hysteria bandwidth hints) are undocumented.

## What Changes

- The direct transport gateway hosts a loopback DNS forwarder on `127.0.0.2:53` (dokodemo-door inbound, `dns` outbound with `nonIPQuery: reject`, built-in DNS over `https+local://` to 1.1.1.1 and 8.8.8.8). The normalizer's sealed resolver and the Xray frontend's DNS point at it; kernel policy admits only the gateway's port-53 replies toward 127.0.0.1; the direct gateway unit alone gains `CAP_NET_BIND_SERVICE`. The DNS-Morph profile, which binds UDP/53 on every address, keeps the numeric upstream resolvers, and the WARP namespace keeps them for its vendor client.
- nginx-xhttp and reality-self-steal access logs use a `log_format` without `$remote_addr` or `$http_user_agent`; the status column stays in place for the watchdog.
- The watchdog receives `XRAY_REALITY_TARGET` and `XRAY_REALITY_SNI` and raises `reality_target_drift` when the target no longer completes a trusted TLS 1.3, X25519, h2 handshake; loopback targets are skipped.
- AmneziaWG enable imports `guard-wireguard-shape.yml`: a production host refuses a WireGuard-shaped instance unless `awg_wireguard_shaped_measurement` names the measurement record.
- REALITY inbounds listen on `::`.
- Documentation states the I1-I5 and per-node bandwidth-hint decisions and the new production variable.

## Capabilities

### New Capabilities

- `security/resolver-privacy-and-identity-drift`: encrypted recipient name resolution from the node, address-free decoy logs, watched REALITY target identity, measured WireGuard-shaped instances and dual-stack REALITY listeners.

### Modified Capabilities

- None.

## Impact

`scripts/transport_destination_policy.py`, `scripts/transport_egress_config.py`, `scripts/transport_egress_normalizer.py`, `scripts/transport_egress_kernel.py`; Ansible roles `transport-egress`, `warp-outbound`, `xray`, `nginx-xhttp`, `reality-self-steal`, `watchdog`, `amneziawg`; `ansible/group_vars/all.yml` (`awg_wireguard_shaped_measurement`); snapshot goldens, unit tests and reference documentation. No Terraform, schema, credential, client-contract or live-host change. The direct gateway unit changes capability set and the normalizer generation changes its resolver, so the next deploy republishes one egress generation.
