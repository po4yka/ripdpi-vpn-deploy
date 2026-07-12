# REALITY target selection — 2026-07-12

## Decision

The best production target for the P0 UpCloud node is an operator-owned self-steal endpoint named `edge.chinallmodel.com`: publish an A record to the P0 address, keep Xray on public TCP/443, terminate a real TLS 1.3 + HTTP/2 site on a private local listener such as `127.0.0.1:8443`, set `xray.target` to that local listener, and use only `edge.chinallmodel.com` in `xray.server_names`. Do not publish AAAA until the IPv6 listener and provider/host firewall path have been tested.

This is a recommendation, not an already-deployed fact. The current `chinallmodel.com:443` target on Scaleway remains active and healthy. Promotion of `edge.chinallmodel.com` requires its DNS record, certificate, local TLS listener, Xray config change, unfiltered validation, authenticated REALITY round trip, and filtered-vantage SNI survival result.

## Why this is the strongest design

The protocol target criteria captured during this research require TLS 1.3, H2, and non-broken redirect behavior, with additional preference for a target close to the proxy IP, OCSP stapling, and an uncommon target. Current implementation guidance also treats a certificate from the same ASN as best practice and warns that unauthenticated traffic is forwarded to `target`, so a third-party target can turn the server into an abusable forwarder. An operator-owned local target on P0 satisfies the same-ASN condition by construction, removes the lifecycle and abuse dependency on a third party, and can still serve an ordinary site to scanners.

The captured configuration contract permits a target in VLESS fallback `dest` form and requires `serverNames` values accepted by that target, normally certificate SANs. Verified self-steal examples confirm that `target` may be an IP or another listener while `serverNames` carries the certificate hostname.

The known local-target CCS report captured during research is specifically an XHTTP+REALITY case. This project's P0 is RAW/TCP + Vision, while XHTTP remains a separate P1 listener, so that report does not invalidate the proposed P0 self-steal design. It is still a regression case to test before promotion.

## Current target verification

`chinallmodel.com:443` passed the repository's complete nine-step validator on 2026-07-12 with zero hard failures and zero warnings: TLS 1.3, `TLS_AES_256_GCM_SHA384`, ALPN `h2`, valid public Let's Encrypt chain, SAN coverage for both apex and `www`, HTTPS 200, Chrome-like client compatibility, and healthy bare/`www` SNI variants. The certificate is valid from 2026-07-12 through 2026-10-10. `xray tls ping` from P0 also passed with and without SNI; the chain is 3417 bytes and currently negotiates classical X25519 rather than X25519MLKEM768.

Direct P0-to-target measurements were stable across three requests: TCP connect 18 ms, TLS complete 41–42 ms, total 59–61 ms, HTTP 200. The P0 address is announced by AS202053, while the current target address `151.115.37.181` is announced by AS12876. Both are European cloud networks and the measured latency is low, but the cross-ASN shape loses the same-ASN best-practice advantage.

The current target is therefore an acceptable temporary production target and is materially better than switching immediately to an unowned popular domain. It is not the optimum final target.

## Candidate comparison

| Candidate | Repository validator | P0 observation | Decision |
|---|---:|---|---|
| `edge.chinallmodel.com` self-steal | Not yet deployable/testable | Same P0 IP and AS202053 by design | Best final target after implementation and two-vantage validation |
| Current `chinallmodel.com` on Scaleway | 0 failures, 0 warnings | HTTP 200; TLS 41–42 ms; AS12876 target | Keep until self-steal promotion |
| `dl.google.com` | 0 failures, 0 warnings | TLS 25–27 ms; HTTP 302; AS15169; X25519MLKEM768 | Best external emergency fallback, not primary: popular third-party lifecycle and ASN mismatch |
| `www.nvidia.com` | 0 failures, 1 warning | HTTP 307; AS20940 | Reject: bare-name SAN hygiene warning and third-party CDN |
| `www.kernel.org` | 0 failures, 1 warning | HTTP 200; AS54113 | Reject: bare-name SAN hygiene warning and third-party CDN |
| `www.mozilla.org` | 0 failures, 1 warning | HTTP 200; AS54113 | Reject: bare-name SAN hygiene warning and third-party CDN |
| `download.docker.com` | 0 failures, 1 warning | HTTP 200; AS16509 | Reject: variant warning and third-party CDN |
| `releases.ubuntu.com` | 1 failure, 2 warnings | ALPN selected HTTP/1.1 | Reject: mandatory H2 requirement fails |

The research identified `dl.google.com` as an example with favorable post-ServerHello behavior and the strongest external fallback in this sample. The captured measurement dataset contained 408 Russian measurements across 79 probe ASNs from 2026-07-05 through 2026-07-12: 14 anomalies, 2 failures, and no confirmed blocks. This supports current ordinary HTTPS reachability but does not prove that a REALITY flow with that SNI survives every filtered path; anomalies can be false positives and must be examined over time.

No OONI measurements exist yet for `chinallmodel.com`, which is expected for a new low-profile domain. Absence of measurements is not evidence of either reachability or blocking.

## Same-prefix scan

The pinned RealiTLScanner v0.2.1 was run locally, never on the VPS, against the complete P0 prefix `87.58.144.0/22`. The scanner's captured operating guidance recommends local execution because cloud execution may flag the VPS.

The scan found only unsuitable same-ASN alternatives: a target returning HTTP 444 and failing the Chrome-like request, an invalid Kubernetes ingress certificate, a hostname whose normal DNS path terminates in a Russian ASN, and a target that subsequently failed the TLS handshake. None is safer or more operationally sound than the owned target. The scan therefore supports creating a controlled same-ASN endpoint instead of borrowing an arbitrary neighboring tenant certificate.

The scan also exposed a local wrapper defect: the macOS install path requests `github.com/XTLS/RealiTLScanner@v0.2.1`, while that release declares the lowercase module path `github.com/xtls/RealiTLScanner`. The research used the same pinned release through the correct lowercase module path; the wrapper itself was not modified in this research change.

## Promotion gates for `edge.chinallmodel.com`

1. Replace the current wildcard-derived `edge.chinallmodel.com CNAME chinallmodel.com` behavior with an explicit A record to the P0 UpCloud IPv4 address. Leave AAAA absent until equivalent IPv6 behavior is proven.
2. Issue a public certificate whose SAN includes exactly `edge.chinallmodel.com`; store it under the existing local SOPS boundary.
3. Run an nginx or equivalent TLS listener only on a private loopback port, with TLS 1.3, ALPN h2, the real static landing content, bounded request handling, and no admin or health surface.
4. Set `xray.target` to the private listener and `xray.server_names` to `edge.chinallmodel.com`; keep public Xray on TCP/443.
5. Validate the target directly and through the public P0 address, including `xray tls ping`, certificate SAN, ordinary browser behavior, invalid-REALITY fallback behavior, config test, authenticated REALITY round trip, and restart/rollback behavior.
6. Run the repository's unfiltered checks and then `scripts/probe-sni-survival.sh` from an actual filtered Russian network. A local or Georgian observation cannot establish TSPU survival.
7. Establish the filtered target-monitor baseline only after the SNI survives, then keep daily monitoring active.

## Confidence and limitation

Confidence is high that the self-steal design is the best target architecture for this fleet and that the current Scaleway target is technically correct as a temporary target. Confidence is intentionally not assigned to Russian-path survival for either hostname: that property is path-specific, no OONI data exists for the owned domain, and this research did not have a filtered Russian vantage. Production promotion must remain blocked on the filtered-vantage SNI test rather than treating TLS hygiene or web research as a substitute.
