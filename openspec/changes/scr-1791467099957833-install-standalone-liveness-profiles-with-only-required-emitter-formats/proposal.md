# Change: Emit only the client formats required by a sentinel

Task ID: `SCR-1791467099957833`

## Why

Standalone P1 onboarding fails because it requests an official sing-box profile even though XHTTP requires Xray. The canonical emitter correctly refuses a host with no supported sing-box transport; the installer must select its inputs from the actual required profiles.

## What Changes

- Request sing-box only for REALITY or Hysteria2, and RIPDPI only for XHTTP.
- AWG-only onboarding does not request either JSON format.
- Preserve failure propagation, native parser checks, exact target identity and generation receipts.
- No public schema or CLI changes.

## Capabilities

### New Capabilities

- `sentinel-format-selection`: required profiles select canonical emitter inputs.

### Modified Capabilities

- None.

## Impact

- Operator sentinel installation, focused orchestration tests and onboarding documentation.
- No provider, cloud-init, runtime server configuration or secret-schema changes.
