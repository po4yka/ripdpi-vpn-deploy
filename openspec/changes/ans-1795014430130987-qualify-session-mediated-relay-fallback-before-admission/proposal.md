# Change: Qualify session-mediated relay fallback before admission

Task ID: `ANS-1795014430130987`

## Why

The MIT-licensed kulikov0/whitelist-bypass project implements headless Pion DataChannel and VP8 relay paths through third-party session services. Existing baseline protocols do not provide this session-mediated model. A service claiming allowlist reachability does not establish end-to-end payload reliability, confidentiality or durable availability.

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
