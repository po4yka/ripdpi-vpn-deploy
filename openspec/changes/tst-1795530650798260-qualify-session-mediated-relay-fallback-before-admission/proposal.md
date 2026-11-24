# Change: Qualify session-mediated relay fallback before admission

Task ID: `TST-1795530650798260`

## Why

The MIT-licensed kulikov0/whitelist-bypass project implements headless Pion DataChannel and VP8 relay paths through third-party session services. The P3 tier of [the architecture map](../../../docs/reference/architecture.md) already names manual WebRTC relays as an operator reachability fallback, but the repository ships no automated, tested or documented session-mediated path. This task qualifies that automated path; it does not replace the manual P3 fallback. A service claiming allowlist reachability does not establish end-to-end payload reliability, confidentiality or durable availability.

## What Changes

- Implement a local qualification harness and a bounded admission decision, not a production transport.
- Record confidentiality, reachability, lifecycle and client-contract gaps explicitly.
- No breaking changes or baseline profile mutation.

## Capabilities

### New Capabilities

- `session-relay-qualification`: reproducible go/no-go evidence before optional fallback integration.

### Modified Capabilities

- None.

## Impact

Only local fixtures and research evidence are planned. Later runtime, secrets and client bundle work needs a separate approved integration specification. Existing Terraform, cloud-init, Ansible, SOPS, vpnd and baseline transport defaults remain unchanged.
