# Threat model

> **Status:** Current · **Type:** explanation · **Tier:** CORE · **Reviewed:** 2026-10-21

This page explains what the stack is built to survive and why each layer
exists. It uses behavioural terms only; the repository does not name
countries, carriers or enforcement bodies (see [the style guide](../STYLE.md)).

## The adversary

The target path is a filtered network with an in-path policy enforcement
point that does deep packet inspection. Observed behaviour, in the order the
design responds to it:

| Behaviour | What it looks like | Design answer |
|---|---|---|
| SNI inspection and allowlisting | TLS to an unknown name is reset or stalled; traffic to large allowlisted names passes | P0 borrows a real allowlisted TLS identity with REALITY; the owned self-steal variant serves a genuine site on loopback |
| TLS-in-TLS and protocol fingerprinting | Tunnels inside TLS are classified by packet-length and timing shape | XTLS-Vision padding and Mux policy on P0; browser-shaped XHTTP behind a real nginx on P1 |
| Active probing | After a suspicious flow, the enforcement point connects to the server itself and checks what it serves | REALITY answers probes as the borrowed site; nginx serves a decoy site; honeypot and probing summaries record attempts |
| UDP throttling and QUIC degradation | UDP/443 is rate-limited or dropped after a volume threshold | P2 Hysteria2 with Salamander obfuscation and optional port hopping; AmneziaWG cohorts with tuned junk packets and header shapes |
| Payload-size throttling | Flows stall once a single response body crosses a size near 16 KiB | A probe measures the threshold per path; P1 and P2 give the client alternatives |
| Concurrent-TLS policing on home access | Roughly a dozen concurrent TLS sessions to one endpoint trigger a penalty | Mux and cohort choices keep the connection count low; a probe exists for the rule |
| ASN-tier blocking | Whole hosting ASNs are freeze-listed; some allowlisted domestic ASNs ride through | Provider notes rank ASNs; a fail-closed attestation gate guards the hosting-jurisdiction exception |
| CDN PoP peering | A CDN's in-country PoPs sit behind the same enforcement point | Decision 0001: the CDN is not the baseline; P1 is direct nginx |
| Per-IP dual-role flow classification | One IP that both receives client flows and originates upstream flows is scored as a relay | Decision 0003: the split-hop pilot separates ingress and egress hosts |
| IP reputation burn | An address is listed once and stays listed | Nodes are disposable: recreate from git plus secrets, never repair in place |

## What the design protects

- **The device, not the node.** Every device has its own UUID, REALITY
  shortId and AmneziaWG peer key. Losing a device revokes one identity; it
  never links other devices together.
- **The secrets, not the server.** The only state that cannot be recreated
  is the encrypted secrets file and the age key. The Shamir split exists
  because losing that key means rotating everything.
- **The operator's machine.** Plaintext secrets exist only in a private
  runtime directory for the duration of one command and are shredded on
  every exit path a shell can catch.

## What the design does not claim

- It does not hide that a VPN exists. It makes each flow look like the
  traffic class it imitates and keeps enough independent paths that a
  client can fail over.
- It does not defend against an adversary with access to the server or the
  operator machine. Compromise is handled by recreation and rotation, not
  by hardening a compromised host.
- It does not prove field survival from the repository. Reachability from
  the filtered side is measured by an operator from a filtered vantage; CI
  measures only the unfiltered half.

## Where the evidence lives

- Transport-level liveness and rotation: [protocol liveness](../reference/protocol-liveness.md).
- Two-vantage reachability: [transport reachability matrix](../how-to/transport-reachability-matrix.md).
- Provider and ASN exposure: [provider notes](../reference/provider-notes.md) and
  [the ASN exposure denylist design](asn-exposure-denylist.md).
- Why the baseline is direct: [decision 0001](../decisions/0001-cdn-not-filtered-path-baseline.md).
- What is research and what is baseline: [decision 0002](../decisions/0002-role-and-doc-tiering.md).
