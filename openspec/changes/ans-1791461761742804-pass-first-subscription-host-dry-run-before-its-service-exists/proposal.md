# Change: Pass first subscription host dry-run before its service exists

Task ID: `ANS-1791461761742804`

## Why

A real first P1 dry-run fails when enabling vpn-bootstrap.service: check mode plans its template without installing it. Deployment requires this dry-run.

## What Changes

- Read systemd load state in check mode.
- Defer absent service activation only after a planned template change.
- Preserve loaded-service validation and real deployment activation.
- No breaking public contract or new credential capability.

## Capabilities

### New Capabilities

- `subscription-check-mode`: safe first dry-run of the subscription service.

### Modified Capabilities

- None.

## Impact

- Ansible subscription-host tasks and focused tests. No Terraform, secrets or protocol changes.
