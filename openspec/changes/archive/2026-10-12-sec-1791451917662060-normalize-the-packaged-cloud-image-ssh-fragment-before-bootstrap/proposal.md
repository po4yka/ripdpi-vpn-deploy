# Change: Normalize the packaged cloud image SSH fragment

Task ID: `SEC-1791451917662060`

## Why

A fresh supported Ubuntu image supplies `60-cloudimg-settings.conf` containing
exactly `PasswordAuthentication no`. Bootstrap refuses this standard fragment
as unsupported membership, so SSH hardening and the completion marker never
publish. This blocks deployment on the new node.

## What Changes

- Consume only the exact packaged password-disabled fragment into the canonical
  first-boot ownership layout, with filesystem checks and rollback.
- Unknown fragments and noncanonical packaged content continue to refuse before
  writes. No authentication or marker gate is weakened.
- No public interface or secret contract changes.

## Capabilities

### New Capabilities

- `security/cloud-image-ssh-bootstrap`: normalize the known image fragment while
  preserving strict first-boot SSH policy and transactional failure behavior.

### Modified Capabilities

- None.

## Impact

- Provider-neutral cloud-init helper and its regression coverage.
- New-node bootstrap only; no provider or runtime policy changes.
