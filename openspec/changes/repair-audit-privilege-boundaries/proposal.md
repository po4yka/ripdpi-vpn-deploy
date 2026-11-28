# Change: Repair audited privilege and input boundaries

Task ID: `SEC-1795869545417758`

## Why

The deployment audit identified excess privilege, privacy gaps, and incomplete validation in runtime roles, operator commands and CI.

## What Changes

- Isolate Realm from Hysteria configuration and restart it on TLS changes.
- Keep bearer routes and device names out of telemetry.
- Validate private file use, device input, subscription settings and provider identities.
- Select engine interoperability checks for the Prometheus fixture and exercise real probe collection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `audit-boundary-correctness` adds privilege, privacy, validation and verification requirements.

## Impact

Ansible, client bundles, secrets bootstrap, vpnd, Terraform and CI. AWG endpoint tags now identify the node. Bootstrap defaults to no enrolled devices.
