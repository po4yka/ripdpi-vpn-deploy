# Network protocol audit remediation
> **Status:** Archived · **Type:** archive · **Tier:** — · **Reviewed:** 2026-10-21


Task: `SEC-1792307003680932`. Source base: PR #328, `a14c339c`.

This ledger covers the confirmed network audit findings. Source, local tests,
hosted CI, deployment, browser behavior, and physical-device acceptance are
separate evidence categories. No deployment is part of this repair.

| Finding | Repair boundary | Regression evidence |
|---|---|---|
| Hysteria hopping intercepts forwarded UDP | Integrated through PR #334, owned by `SEC-1792306834441683`; public-ingress and local-destination guards remain active | Native transit UDP regression in that source change |
| UpCloud return range excludes client NAT ports | Export the enabled provider range through inventory and remap forwarded AWG/split-hop TCP/UDP into it; retain SSH CIDR and guest stateful checks | `test_provider_nat_source_ports.py`, `test_provider_nat_native.py`, provider Terraform and inventory tests |
| Full-device checker accepts capture exclusions | Refuse partial capture selectors and malformed capture authority | `test_check_killswitch.py` |
| Wildcard SAN accepts another DNS suffix | Already integrated in PR #328; retain native complete-label hostname verification | `test_check_certs_key_match.py` |
| Certificate preflight accepts unusable trust or dates | Retain PR #328 date checks; validate trusted chain and server-auth purpose independently from SAN matching | `test_check_certs_key_match.py` |
| Disabled Naive requires certificate material | Resolve the effective selected profile; inspect only enabled TLS authorities | Certificate, controller and backup-configuration tests |
| DNS-Morph disable leaves the upstream resolver selected | Retain original managed stub authority; stop the bridge before restart and restore | `test_resolver_roundtrip.py`, `test_runtime_audit_regressions.py` |
| Unicode name mapping selects another DNS identity | Require lossless Unicode codec round-trip or explicit ASCII A-label | `test_transport_destination_boundary.py` |
| Cascade relay closes both directions on the first FIN | Drain bounded independent directions and enforce idle time | `test_cascade_classifier_proxy.py` |
| Alternate-port HSTS upgrades the hostname to an unrelated port 443 identity | Retain HSTS only for a compatible same-host public HTTPS/443 site; otherwise clear it | `test_public_site_contract.py` |
| Normalizer drops empty UDP payloads | Treat empty datagrams as data and retain all association guards | `test_transport_destination_boundary.py` |
| Native SOCKS readiness assumes a complete TCP reply in one read | Correction ef911bd4 accumulates the exact two-byte SOCKS5 reply within the existing deadline; PR #338 integrates it as bc849f60, accepted by complete main CI 39216524425 | `test_native_socks_readiness.py`, strict failed-case projection in `test_four_transport_runner.py` |
| Sentinel installer omits the provenance inputs its caller requires | Return the exact public input map; require the full correction identity in both standalone readers | `test_real_vps_awg_nat_provisioning.py`, `test_protocol_liveness_sentinel.py`, `test_real_vps_awg_nat_lane.py` |
| AWG emits a computed zero UDP checksum as 0000 | Correct both userspace completion paths; bind the source correction to build identity and immutable binaries | Exact-source admission, native build provenance, corrected isolated packet proof and integrated real AAAA regression; actual main bc849f60 passes all 45 canonical cases and complete CI 39216524425 |

The task verification document records observed results and exact integrated
source evidence. A listed test is not a claim that it ran successfully.

## Resolver migration and recovery

New managed stub migrations retain the exact original systemd stub target in
`/etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path`. An owned pending marker
precedes the disabling configuration. A retry after interrupted publication
applies the restart before clearing that marker. Routine repeated convergence
does not restart resolved without a pending change.

The site baseline keeps a working upstream resolver while retirement runs.
After the bridge releases port 53, the retiring role restarts resolved and
restores only the retained managed symlink. A replaced resolver, invalid record,
or unsafe record refuses without overwriting custom resolver authority.

Older deployments did not retain the original symlink. An upstream symlink
alone cannot distinguish a prior managed migration from an operator-owned
resolver. Such hosts retain their existing resolver and need explicit local
reconciliation during a separately authorized rollout. Do not invent an origin
record or force a stub before the bridge has stopped.

## Deliberate protocol choices

- AWG is dual-stack; split-hop remains IPv4-only and rejects unsupported IPv6.
- DNS UDP and TCP are required for resolver fallback. Client HTTPS DNS is DoH;
  ordinary server-side UDP/TCP DNS is not DoT.
- TLS 1.3 and X25519 remain the direct nginx fingerprint profile. HTTP/1.1 on
  the loopback upstream does not remove HTTP/2 from the public listener.
- The kernel TFO switch does not prove application socket opt-in. Linux TCP
  BBR, actual queue discipline, and Hysteria QUIC congestion are distinct.
- Version bumps, new crypto groups, and optional protocol promotion are outside
  this repair. PQE HOLD and per-device credential authority remain unchanged.

## Requested protocol coverage

| Topics | Source contract and evidence boundary |
|---|---|
| IPv4/IPv6, TCP/UDP, nftables/NAT | AWG is dual-stack; split-hop supports IPv4. Provider return-port NAT has real namespace packet regressions for both transports. |
| ICMP, ND and MTU | Firewall rules retain required ICMP errors and link-scoped ND admission. Complete path MTU discovery and fragmentation acceptance remain unverified. |
| DNS UDP/TCP, DoH and DoT | Server resolver traffic uses UDP/TCP DNS. Client HTTPS DNS is DoH. These settings do not establish a DoT listener or client. |
| IDNA | Lossless Unicode mapping and explicit A-label cases pass on Python 3.12.13 and 3.12.15. |
| SNTP | The baseline installs and starts systemd-timesyncd; strict egress permits UDP/123. Service enablement does not prove clock synchronization or NTS. |
| TLS, X25519, SNI/ALPN and HTTP/1/2 | The direct nginx profile keeps TLS 1.3 and X25519; public HTTP/2 and loopback HTTP/1.1 have distinct roles. SNI and protocol settings are source contracts, not a live VPS handshake observation. |
| SOCKS5 and TUN | Capture authority, TCP half-close, authenticated empty UDP and fragmented SOCKS readiness replies have regressions. Physical Android kill-switch acceptance remains separate. |
| TFO and BBR | Kernel controls and optional availability do not prove socket TFO opt-in, the active qdisc or TCP congestion control. Hysteria QUIC congestion is independent. |
| HSTS and CSP | HSTS follows the same-host HTTPS/443 topology. CSP render contracts remain active. Browser cache state and enforcement remain unverified. |

Source contracts are in the baseline tasks and sysctl template, firewall and
nginx templates, and client payload builder. Their regressions include
`test_firewall_egress_policy.py`, `test_firewall_native.py`,
`test_public_site_contract.py`, `test_baseline_vps_packages.py` and
`test_baseline_sysctl_recovery.py`. A source contract does not establish live
negotiation or effective kernel state.

## Validation transport correction

The complete local gate also confirmed a checkout-discovery deadlock: Python
and Git both blocked writing pipe data beyond the command timeout. Metadata
input now uses a private temporary file. The correction keeps exact path bytes,
empty-input EOF, command deadlines and all content-filter refusals.
`test_workspace_status.py` covers large real Git input, non-UTF-8 names, clean
and process filter refusal, and a real blocked-query deadline.

## AWG UDP checksum diagnostic

An isolated Linux packet experiment confirms a defect in the pinned AWG Go
runtime before NAT. For both baseline and current firewall policies, three
IPv6 UDP requests whose completed checksum equals zero are lost; three
adjacent-port controls pass. Server TUN captures show 0000 with no pending
checksum offload. The required UDP wire value is ffff. Each lost request adds
one upstream checksum error. These observations do not establish the exact
cause of the earlier CI failure, whose source port was not captured.

The repair preserves offloads, TCP checksum behavior, packet guards and
authentication. Production and native acceptance builds must use the same
strictly admitted source correction. An unchanged upstream commit must not
allow reuse of an uncorrected binary or overwrite its immutable release path.
Source, build and corrected packet acceptance remain separate checks.

The source inventory covers five builders: the server role, the native semantics
script, the native acceptance preparation module, the source-candidate container
builder and the offline sentinel installer. They all use the same correction.
The offline installer binds it into its existing toolchain ID before selection.
Its pinned vendor workspace remains part of the existing offline build contract;
only that owned staging workspace is removed before strict source verification.

Old sentinel manifests with only five input fields cannot qualify as corrected.
A separately authorized sentinel convergence builds and selects a new immutable
toolchain. Until that convergence, updated readers refuse the old qualification.
Keep the previous directory for rollback; do not add identity fields to old
manifests by hand. Both standalone readers resolve the exact trusted installed
helper and compare the complete correction identity. No runtime or arm64
candidate promotion follows from this source correction.

The corrected isolated experiment passes both exact public pins. Each has
eight expected failing Go leaves before correction and 28 passing leaves
after correction, with no skips. Each published corrected binary receives
six UDP6 replies under each of the two recorded NAT policies, for 24 replies
in total. Complete pre-NAT TUN checksums are ffff/fffe and all checksum error
deltas stay zero. This uses a DNS-shaped echo payload. The native CI case
separately requires actual AAAA answers; production and physical clients
remain outside this isolated acceptance.

## Remaining independent evidence

Strict split-hop reverse-path filtering and Android per-package DNS attribution
were conditional audit risks, not demonstrated outages. They need exact
baseline-plus-topology and Android engine tests before a repair is selected.
The source tests do not establish physical-client kill-switch behavior, complete
PMTUD/fragmentation coverage, browser HSTS cache state, or live provider routes.

## Source merge and acceptance

PR #333 is merged as `f4e094c7a69b3b066d4c1562c20fe2a429376929`. Final source CI 39146510843 passed. Actual main CI 39150921761 failed in IPv6 hopping readiness
and was not accepted. The checksum and lifecycle cases pass; the readiness
failure occurs before the packet driver and its underlying cause is unproved. The verification record
retains the exact local, native and source scopes. This source merge does
not authorize or establish deployment, sentinel convergence, live provider
routes, browser state or physical-client acceptance.

Corrective PR #331 candidate e415ec41 passes both SOCKS hopping families but
fails DHCPv6 readiness before multicast sending in CI 39156237467. The route
lookup exits nonzero; its precise cause remains unknown. The candidate is not
accepted. At that checkpoint, whole source acceptance remained open.

The next diagnostic candidate 1a3a627e repeats that same failure in CI
39196976196. Its fixed error categories do not identify the command error;
neither diagnostic run establishes a packet or firewall failure. The exact
cause remains unproved; this candidate was not accepted.

Candidate 86ffdad7 fails its early DHCPv6 preflight in CI 39202116288. The
verified `ip` reports `RTNETLINK answers: Message too long` before multicast
sending. The full core has not run. This does not establish a data-plane MTU
or firewall defect. This candidate was not accepted.

Corrective candidate 899c6308 replaces the multicast input route query with
socket binding and exact group-membership checks before receiver readiness.
The input query can enter multicast forwarding, although this fixture needs
local delivery. The focused suite passes 374 cases. One earlier local null
result remains unexplained; a later bounded comparison receives multicast
in both fresh default-route and explicit-route arms. No route workaround is
added. CI 39205012239 fails the early positive multicast packet assertion
after receiver readiness; the full core suites remain empty. This candidate
is not accepted. PR #331 keeps its separate DHCPv6 work. PR #338 publishes
the existing SOCKS readiness correction alone. Its final source 69ba5de4
passes the complete local make check, all 45 canonical native cases, hosted
CI 39210543551 and all companion workflows. The protected merge bc849f60
has the exact tested tree 254121d7. Its own CI 39216524425 attempt 1 completes
successfully with all 92 jobs successful, including native runtime integration
and the required-check aggregate. All nine required checks and all five
workflows succeed. Its three canonical artifacts pass all 45 cases on exact
source bc849f60 with matching engine identity and successful cleanup.
Source acceptance is complete on bc849f60; the earlier main failure stays
failed and its cause remains unproved. PR #331 remains separate and unaccepted.
This acceptance does not establish deployment, live routes, browser state or
physical-client behavior. All packet assertions remain required.
