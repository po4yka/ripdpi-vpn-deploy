# Fleet-wide transport signatures — 2026-11-15

> **Status:** Research · **Type:** research · **Tier:** — · **Reviewed:** 2026-11-15

This page records one measurement, verdict and next step for each network signature that the 2026-11-15 repository audit found to be the same on every node. It is not normative. No default changes in this page; a default changes only through its own spec-required task.

## Scope and evidence labels

Every statement about a signature carries one of three labels.

- **Measured here**: observed on 2026-11-15 on one workstation, with loopback sockets and local containers only. No packet left the computer.
- **Read from configuration**: taken from a template, its golden render or a default in this repository at commit `1d6a4833`, with file and line.
- **Upstream**: taken from the named upstream document and not checked here.

A loopback measurement shows the wire shape that a configuration produces. It does not show how a filter treats that shape. Where the open question is the reaction of a filter, the verdict is "measure on a filtered path" and the section names the measurement and the repository tool.

## Lab

| Item | Value |
|---|---|
| TLS server | nginx 1.30.6 with OpenSSL 3.5.8 in a local container, serving the golden render `tests/snapshot/golden/nginx-xhttp/templates/site.conf.j2` |
| Lab change to that render | one line: the `proxy_pass` address points to the container host so that the Xray lab server can receive the request |
| Comparison TLS server | a second `server` block in the same container with only the certificate set, so every TLS directive has the nginx built-in value |
| Certificate | self-signed ECDSA P-256 certificate for the fixture name `vpn.example.com` |
| TLS probe client | OpenSSL 4.1.0 `s_client`, `curl` 8.7.1 |
| Xray | 26.10.31, the version that `.github/actions/install-xray/action.yml:12` pins; the build installed on the workstation, no download |
| sing-box | 1.14.3 as installed, used for the WireGuard and Hysteria2 endpoints |
| Linux kernel for the TCP check | 6.8.0 in a local container |
| Capture | Python relays on loopback that log, per direction, the TLS record type and length or the UDP datagram length, time and first 8 bytes |

Limits of this lab:

- Packet capture on the loopback interface needs a privilege that the session did not have. The relays log record and datagram sizes, not IP packets, so segment sizes, TTL and TCP options are not measured.
- The fleet runs nginx from the distribution package. The lab nginx is a different build, so the comparison between the rendered profile and the built-in defaults is valid inside one build only.
- The fleet runs the upstream Hysteria server, which this repository builds from source. No binary with a committed checksum exists for the workstation, so sing-box served as both Hysteria2 ends. The client side matches the standard client artifact; the server side is a different implementation of the same protocol.
- The WireGuard endpoints are the sing-box userspace implementation, not the kernel module that `wg-quick` uses on a node.
- No local image holds the `nft` binary and the task forbids unpinned installs, so the firewall behaviour is read from the render and not measured.
- Captures, keys and lab configurations stay in a scratch directory outside the repository.

## Summary

Ranked by the strength of the local evidence and by how many sessions show the signature.

| Rank | Signature | Result | Verdict |
|---|---|---|---|
| 1 | XHTTP inbound without a Vision flow | Measured: each inner TLS handshake record appears in the outer TLS stream as one record of inner size plus a constant | Measure on a filtered path |
| 2 | Uniform nginx TLS profile | Measured: five responses differ from the same nginx build with built-in TLS values | Keep; two candidates listed |
| 3 | Hysteria without Salamander, fixed bandwidth | Measured: plain mode is valid QUIC version 1; the transfer rate follows the configured value, not the path | Keep Salamander off; measure the fixed rate on a filtered path |
| 4 | Plain WireGuard on tunnel hops | Measured: the documented 148, 92 and 32 byte messages, a 25.00 s keepalive and a new handshake every 125 s | Measure on a filtered path |
| 5 | Default public port set and silent drop | Read from configuration; not measured | Keep |
| 6 | Watchdog canary timer and client `urltest` interval | Read from configuration; not measured | Keep |
| 7 | `net.ipv4.tcp_fastopen = 3` | Measured: no change on the wire, because no listener requests Fast Open | Keep |

No signature has the verdict "change the default", so this task files no follow-up task. [Candidates](#candidates-and-missing-evidence) lists the changes that need more evidence and names that evidence.

## 1. XHTTP inbound without a Vision flow

**Read from configuration.** The REALITY inbound gives each client `"flow": "xtls-rprx-vision"` (`tests/snapshot/golden/xray/templates/config.json.j2:25`). The XHTTP inbound clients have no `flow` key and the inbound uses `"network": "xhttp"`, `"security": "none"` and `"mode": "auto"` behind nginx (`tests/snapshot/golden/xray/templates/config.json.j2:50-69`). nginx forwards the path with `proxy_buffering off` and `proxy_request_buffering off` (`tests/snapshot/golden/nginx-xhttp/templates/site.conf.j2:62-67`).

**Method.** One `curl` HTTPS request for a 31-byte page ran three ways through the logging relay: directly to nginx (the inner handshake), through an Xray XHTTP client and the rendered nginx site to an Xray server with the golden inbound settings, and through a loopback REALITY tunnel with the Vision flow. The relay sat between the client and the server and logged every outer TLS record.

**Measured here.** Inner handshake, direct to nginx, application and handshake record lengths in bytes:

| Step | Direction | Inner record lengths |
|---|---|---|
| ClientHello | client to server | 317 |
| ServerHello to Finished | server to client | 122, 1, 42, 422, 95 to 97, 53 |
| Finished and HTTP request | client to server | 1, 53, 101 |
| Session tickets and HTTP response | server to client | 74, 74, 565 |
| Close | client to server | 19 |

The same request through XHTTP, six runs in `packet-up` mode (the mode that `auto` selected over HTTP/2):

| Inner step | Inner bytes with record headers | Outer record length | Runs with that exact record |
|---|---|---|---|
| ClientHello | 322 | 374 | 6 of 6 |
| ServerHello to Finished | 765 to 767 | 793 to 795 | 6 of 6 |
| Finished and HTTP request | 169 | 195 | 5 of 6 |
| Session tickets and HTTP response | 728 | 754 | 5 of 6 |
| Close | 24 | 50 | 6 of 6 |

The tunnelled request names a port with one character less than the direct lab request, so its request record is 100 bytes and not 101. The outer record is the inner byte count plus 26 bytes (a 9-byte HTTP/2 DATA frame header and 17 bytes of TLS 1.3 record expansion), plus the 26-byte VLESS request header on the first upload record and the 2-byte VLESS response header on the first download record. In the two runs without an exact match, two inner writes shared one outer record. The records that carry HTTP/2 HEADERS frames changed from run to run (360 to 1251 bytes), so the XHTTP header padding is active; it does not pad the DATA frames. In `stream-up` mode the first upload record was also 374 bytes in 6 of 6 runs; the lab proxy path did not complete a `stream-up` transfer, so later records in that mode are not measured.

The same request through REALITY with the Vision flow, three runs: the records after the outer handshake were 936 to 1403 bytes and changed on every run. No record matched an inner size plus a constant.

**Verdict: measure on a filtered path.** The lab shows that the XHTTP path exposes the size and order of the inner TLS handshake and that the Vision path does not. The lab cannot show whether a flow classifier on a real path uses that pattern. Run the P1 direct cells of [the transport reachability matrix](../how-to/transport-reachability-matrix.md) beside the P0 cells from the same filtered vantage, and classify each failure by stage with [the regression baseline](../how-to/regression-baseline.md). The `flow` key is a VLESS setting for the raw transport (upstream: Xray VLESS documentation), so no existing default removes this signature from XHTTP; see the candidates.

## 2. Uniform nginx TLS profile

**Read from configuration.** Both public `server` blocks set `ssl_protocols TLSv1.3`, `ssl_ecdh_curve X25519`, `ssl_session_cache shared:vpn:10m`, `ssl_session_timeout 1d` and `ssl_session_tickets off` (`ansible/roles/nginx-xhttp/templates/site.conf.j2:37-43` and `:159-165`). The HSTS header is `max-age=31536000` only when the name has a public HTTPS listener on port 443 and `max-age=0` in all other cases (`ansible/roles/nginx-xhttp/templates/site.conf.j2:7`, `:45`). The default public port is 8443 (`ansible/group_vars/all.yml:213`), so the default render sends `max-age=0` (`tests/snapshot/golden/nginx-xhttp/templates/site.conf.j2:28`).

**Method.** `openssl s_client` and `curl` probed the rendered site and the comparison server in the same container.

**Measured here.**

| Probe | Rendered profile | Same nginx build, built-in TLS values |
|---|---|---|
| ClientHello that offers TLS 1.2 only | alert 70 `protocol_version` | TLS 1.2 handshake completes |
| First key share P-256, X25519 also offered | HelloRetryRequest, then X25519 | P-256, no retry |
| First key share X25519MLKEM768, X25519 also offered without a share | HelloRetryRequest, then X25519 | X25519MLKEM768, no retry |
| Key shares for X25519MLKEM768 and X25519 together | X25519, no retry | not run |
| X25519MLKEM768 only | alert 40 `handshake_failure` | X25519MLKEM768 |
| P-256 only | alert 40 `handshake_failure` | P-256 |
| NewSessionTicket messages after the handshake | 2, lifetime hint 86400 s, resumption accepted | 2, lifetime hint 300 s, resumption accepted |
| `Server` header | `nginx` | `nginx/1.30.6` |
| `Strict-Transport-Security` header | `max-age=0` | absent |

Two results correct the audit wording. First, `ssl_session_tickets off` does not stop TLS 1.3 tickets: with the shared session cache, nginx sends two stateful tickets and accepts resumption. The node does not differ from the comparison server in the ticket count, only in the lifetime hint. Second, the profile never selects the hybrid group and it forces a second ClientHello from every client whose first key share is not X25519.

**Verdict: keep, with these reasons.**

- `max-age=0` is a recorded requirement: `REQ-NPC-HSTS` in `openspec/specs/security/network-protocol-correctness/spec.md` says that a name served only on an alternate port must clear a cached HSTS policy. The header is a fleet-common token on every response of a default node, and a change must go through that requirement.
- `ssl_protocols TLSv1.3` and `ssl_ecdh_curve X25519` are deliberate; `ansible/roles/nginx-xhttp/CLAUDE.md` records them as a camouflage choice, and `REQ-TMD-REALITY-CONSISTENCY` requires that a REALITY target can negotiate X25519. The lab shows that the pin is observable against one nginx build. It does not show which behaviour is common among ordinary sites in the networks where nodes run, and that comparison needs probes to hosts that this task may not contact.

Both are candidates, not changes. The related identity work (one TLS identity for each address, behaviour of port 80) is in task `XRY-1794729068388916` and is not repeated here.

## 3. Hysteria without Salamander and with one bandwidth profile

**Read from configuration.** Salamander is off unless `hysteria.salamander_enabled` is true (`ansible/roles/hysteria/templates/config.yaml.j2:30-39`), and no profile in `ansible/group_vars/` sets it. The server always renders `bandwidth.up` and `bandwidth.down` with the defaults `100 mbps` and `200 mbps` (`ansible/roles/hysteria/templates/config.yaml.j2:47-49`); the default resource profile is `bandwidth-capped` (`ansible/roles/hysteria/defaults/main.yml:5`), and for that profile the client artifact carries the matching hints (`scripts/transport_semantics.py:454-461`).

**Threat-model correction.** The UDP row of [the threat model](../explanation/threat-model.md) said "Hysteria2 with Salamander obfuscation". The template is the truth: Salamander is opt-in and off by default. This change corrects that row.

**Method.** A sing-box Hysteria2 server and client ran on loopback through the UDP relay, first plain and then with Salamander. A second run without the relay downloaded a 60 MB file three times with the bandwidth hints and three times without them.

**Measured here.**

| Property | Plain | Salamander |
|---|---|---|
| First client datagram | 1250 bytes | 1258 bytes |
| Bytes 2 to 5 of the first datagram | `00 00 00 01`, QUIC version 1 | no fixed value |
| Datagrams with the QUIC fixed bit set | 16 of 16 | 4 of 14 |
| Datagram lengths after the first flight | QUIC short-header packets, for example 30, 35, 69 | each 8 bytes longer, for example 38, 43, 77 |

| Client setting | Download rate, three runs |
|---|---|
| Hints that match the server default (client download 100 Mbit/s) | 92.6, 95.0 and 95.2 Mbit/s |
| No hints (BBR) | 597, 610 and 650 Mbit/s |

Plain mode is a valid QUIC version 1 exchange on the wire. Salamander removes every QUIC field and adds 8 bytes to each datagram. With the default profile the sender holds the configured rate; on loopback the same path carried more than six times that rate when the hints were absent.

**Verdict: keep Salamander off by default; measure the fixed rate on a filtered path.** Plain mode keeps the HTTP/3 masquerade reachable for a prober, which Salamander removes, and the template comment already states the trade. Which of the two shapes a filter throttles is a path question: run the Hysteria cells of [the transport reachability matrix](../how-to/transport-reachability-matrix.md) with and without `hysteria.salamander_enabled` on a staging node. For the rate, run `scripts/probe-payload-throttle.sh` on a filtered path with the `bandwidth-capped` profile and with a `bbr-` resource profile, and compare the plateau and the loss. The fixed plateau is the same on every default node; the lab shows that it exists, not that a filter keys on it.

## 4. Plain WireGuard on the split-hop and cascade tunnels

**Read from configuration.** The split-hop responder listens on a fixed port, 51821 (`ansible/group_vars/all.yml:243`, `ansible/roles/split-hop-ingress/templates/split-hop-ingress.conf.j2:4`). The split-hop initiator sets `PersistentKeepalive` to 25 seconds (`ansible/roles/split-hop-egress/defaults/main.yml:52`, `ansible/roles/split-hop-egress/templates/split-hop-egress.conf.j2:30`). The cascade pair uses port 51831 and the same keepalive (`ansible/roles/cascade-ingress/defaults/main.yml:8-10`, `ansible/roles/cascade-egress/defaults/main.yml:6`). All four roles are opt-in and off by default (`ansible/group_vars/all.yml:69-93`). [Decision 0003](../decisions/0003-split-hop-relay-topology.md) chose plain WireGuard and deferred an AmneziaWG-shaped tunnel until the plain shape is itself classified.

**Method.** Two userspace WireGuard endpoints ran on loopback for 400 seconds with no payload traffic. The initiator had the 25-second keepalive and the responder had none, as in the roles. The UDP relay logged every datagram.

**Measured here.**

| Message | Direction | UDP payload | First 4 bytes |
|---|---|---|---|
| Handshake initiation | initiator to responder | 148 bytes | `01 00 00 00` |
| Handshake response | responder to initiator | 92 bytes | `02 00 00 00` |
| Keepalive | initiator to responder | 32 bytes | `04 00 00 00` |

Every keepalive interval was 25.00 to 25.01 seconds. A new handshake started 125.0 seconds after the previous one, three times in a row; that is the first keepalive after the 120-second rekey timer. The responder sent nothing except handshake responses. The sizes and type bytes equal the message layout in the WireGuard protocol description (upstream).

**Verdict: measure on a filtered path.** An idle tunnel is fully described by four constants: three sizes, one 4-byte prefix for each type, a 25-second period and a 125-second handshake cycle, on a fixed destination port. The tunnel runs between two operator hosts, so the question is whether the path between the hops classifies or throttles that shape. Follow [the split-hop pilot](../how-to/split-hop-pilot.md), record the latest-handshake age and the transfer counters of the tunnel interface over at least one day, and classify each failure by stage with [the regression baseline](../how-to/regression-baseline.md); the cascade leg has `scripts/cascade-leg-probe.py` for leg health. Decision 0003 already names the AmneziaWG-shaped variant as the next step when that evidence appears.

## 5. Default public port set and silent drop

**Read from configuration.** The input chain has `policy drop` and ends with `counter drop` (`tests/snapshot/golden/firewall/templates/nftables.conf.j2:38`, `:81`). The default render accepts TCP 443, 80 and 8443, UDP 443 and 51820, and SSH from the listed sources only (`tests/snapshot/golden/firewall/templates/nftables.conf.j2:67-79`). It accepts ICMP echo with a rate limit (`:43-44`, `:59`, `:63`).

**Not measured.** No local image holds `nft`. From the rules, a probe to any other port gets no answer, and a probe to an accepted port with a stopped service gets a TCP reset from the kernel.

**Verdict: keep.** A drop policy with no answer is the normal state of a host behind a cloud firewall, and the provider firewall in front of the node applies the same listener contract. The fleet-common part is the open set, not the drop. Port 8443 is a default that direct-only cohorts can move to 443 (`ansible/group_vars/all.yml:213`), and the AmneziaWG listen port is the subject of task `ANS-1794729221714172`. A port scan of a real node belongs to an authorized acceptance run, not to this task.

## 6. Watchdog canary timer and client `urltest` interval

**Read from configuration.** The watchdog timer starts 2 minutes after boot, repeats 5 minutes after each run and adds a random delay of up to 30 seconds (`tests/snapshot/golden/watchdog/templates/vpn-watchdog.timer.j2:5-7`, `ansible/roles/watchdog/defaults/main.yml:3`). The canary URL comes from the environment secrets (`ansible/roles/watchdog/templates/vpn-watchdog.env.j2:22`), so all nodes of one environment fetch the same operator-owned URL. The standard client artifact has one `urltest` group that tests every outbound against one fixed connectivity-check URL every 30 minutes with a 50 ms tolerance (`scripts/client_payload.py:366-367`).

**Not measured.** Neither period fits a short lab run, and the timer needs systemd.

**Verdict: keep.**

- The `urltest` interval is a recorded requirement: `REQ-TMD-CLIENT-CADENCE` in `openspec/specs/security/traffic-metadata-and-decoy-identity/spec.md` pins 30 minutes on purpose to bound client probing. The remaining signature is that one client opens a short flow on every transport of one node at the same moment, twice an hour. A change needs a new requirement and the paired client change that the spec names.
- The watchdog flow leaves the node toward an operator-owned host; it is not on the client path. Its period is 5 minutes plus up to 10 percent jitter. No evidence here shows that an observer of node egress uses it.

## 7. `net.ipv4.tcp_fastopen = 3`

**Read from configuration.** The baseline sysctl file sets `net.ipv4.tcp_fastopen = 3` (`ansible/roles/baseline/templates/sysctl-vpn.conf.j2:2`). No template in `ansible/` or `scripts/` requests Fast Open on a listener: there is no `fastopen=` on an nginx `listen` line and no `tcpFastOpen` in an Xray `sockopt`.

**Method.** In a container with kernel 6.8.0, a client sent data in the SYN three times to a listener without the `TCP_FASTOPEN` socket option and to a listener with it, for the sysctl values 3 and 1 (the kernel default). The kernel counters gave the result.

**Measured here.**

| Sysctl value | Listener | Cookie requests | Fast Open connections accepted |
|---|---|---|---|
| 3 | no `TCP_FASTOPEN` option | 3 | 0 |
| 3 | `TCP_FASTOPEN` option set | 1 | 2 |
| 1 | no `TCP_FASTOPEN` option | 3 | 0 |
| 1 | `TCP_FASTOPEN` option set | 3 | 0 |

With the value 3, a listener that does not set the socket option never grants a cookie. Its answers equal those of the kernel default.

**Verdict: keep.** The setting changes nothing on the wire for the rendered services, so the node cannot answer a Fast Open probe differently from a host with the kernel default. The risk in the audit finding appears only if a listener later sets the option: a REALITY node then grants a cookie and its target possibly does not. Measure the target again before any change that adds `fastopen=` or `tcpFastOpen`.

## Candidates and missing evidence

No candidate has enough evidence for a spec-required task today.

| Candidate change | Evidence that is missing |
|---|---|
| Pad or reshape XHTTP DATA records, or route P1 clients to the Vision path first | Filtered-path survival of P1 against P0 from the same vantage, and an Xray option that pads XHTTP data, which was not found in the rendered settings |
| Remove the `ssl_ecdh_curve X25519` pin so that nginx uses the library group list | Key-exchange behaviour of ordinary sites in the networks where nodes run, and a check that every REALITY self-steal target still negotiates X25519 |
| Send no HSTS header on an alternate-port-only name | A decision on `REQ-NPC-HSTS`, which requires the header to clear a cached policy |
| Use a `bbr-` resource profile as the Hysteria default | `scripts/probe-payload-throttle.sh` results for both profiles on a filtered path |
| Use an AmneziaWG-shaped tunnel between hops | Handshake age and loss of the plain tunnel across a filtered inter-hop path |
| Stagger the client `urltest` between outbounds | A change to `REQ-TMD-CLIENT-CADENCE` and the paired client change |

## Reproduce

All commands use loopback addresses. Replace the lab paths with a scratch directory outside the repository.

```bash
# TLS profile: protocol, groups, tickets, headers
openssl s_client -connect 127.0.0.1:8443 -servername vpn.example.com -tls1_2 </dev/null
openssl s_client -connect 127.0.0.1:8443 -servername vpn.example.com -groups P-256:X25519 -msg </dev/null
openssl s_client -connect 127.0.0.1:8443 -servername vpn.example.com -groups X25519MLKEM768 </dev/null
curl -sk --resolve vpn.example.com:8443:127.0.0.1 https://vpn.example.com:8443/ -D - -o /dev/null
```

```bash
# TCP Fast Open: run the check in a container network namespace with each value
docker run --rm -i --sysctl net.ipv4.tcp_fastopen=3 <local-image-with-python3> python3 - < tfo-check.py
```

The record and datagram logs come from two short Python relays: a TCP relay that parses the 5-byte TLS record header in each direction, and a UDP relay that logs the length, the time and the first 8 bytes of each datagram.
