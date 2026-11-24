# Change: Qualify storage-mediated fallback before admission

Task ID: `XRY-1795014272195404`

## Why

XDRIVE in XTLS/Xray-core v26.11.9 supplies a storage-mediated transport. Upstream calls it public testing, requires matching client/server revisions and VLESS Multiplex plus Encryption, and warns of changing interfaces. Dedicated account credentials, quota costs, cleanup and latency are admission risks. This is distinct from merely upgrading the Xray release pin.

## What Changes

- Implement a local qualification harness and a bounded admission decision, not a production transport.
- Record confidentiality, reachability, lifecycle and client-contract gaps explicitly.
- No breaking changes or baseline profile mutation.

## Capabilities

### New Capabilities

- `storage-fallback-qualification`: reproducible go/no-go evidence before optional fallback integration.

### Modified Capabilities

- None.

## Impact

Only local fixtures and research evidence are planned. Later runtime, secrets and client bundle work needs a separate approved integration specification. Existing Terraform, cloud-init, Ansible, SOPS, vpnd and baseline transport defaults remain unchanged.
