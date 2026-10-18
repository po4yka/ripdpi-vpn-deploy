# Network protocol audit remediation

Task: `SEC-1792307003680932`. Source base: PR #328, `a14c339c`.

This ledger covers the confirmed network audit findings. Source, local tests,
hosted CI, deployment, browser behavior, and physical-device acceptance are
separate evidence categories. No deployment is part of this repair.

| Finding | Repair boundary | Regression evidence |
|---|---|---|
| Hysteria hopping intercepts forwarded UDP | Separately owned by `SEC-1792306834441683`; require its integrated public-ingress and local-destination guard | Native transit UDP regression in that source change |
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
| Sentinel installer omits the provenance inputs its caller requires | Return the exact public input map; require the full correction identity in both standalone readers | `test_real_vps_awg_nat_provisioning.py`, `test_protocol_liveness_sentinel.py`, `test_real_vps_awg_nat_lane.py` |
| AWG emits a computed zero UDP checksum as 0000 | Correct both userspace completion paths; bind the source correction to build identity and immutable binaries | Exact-source admission, native build provenance and deterministic IPv6 packet regression; repair acceptance remains pending |

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

The repair must preserve offloads, TCP checksum behavior, packet guards and
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

## Remaining independent evidence

Strict split-hop reverse-path filtering and Android per-package DNS attribution
were conditional audit risks, not demonstrated outages. They need exact
baseline-plus-topology and Android engine tests before a repair is selected.
The source tests do not establish physical-client kill-switch behavior, complete
PMTUD/fragmentation coverage, browser HSTS cache state, or live provider routes.
