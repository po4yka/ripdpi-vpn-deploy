# Change: Repair critical Ansible role security and availability paths

Task ID: `SEC-1791545689674403`

## Why

Critical role paths permit privileged log-file repair through runtime-owned
entries, recreate missing revocation authority, expose bearer material, fail
profile-scoped backups, stop Xray during log rotation, and allow watchdog
notification stalls or credential disclosure. Retained dead-man code accepts
unbounded TLS handshakes and does not bind replay state to an authority generation.
Current source already repairs the baseline DNS-stub and collector ingress
rotation findings; those behaviors require verification rather than duplication.

## What Changes

- Keep Xray logs usable without privileged runtime pathname repair or unsupported signals.
- Refuse missing revocation state and redact share-bundle operations.
- Back up only effective service inputs while rejecting missing required configuration.
- Bound retained receiver TLS work and authenticate generation-bound replay transitions.
- Deliver watchdog notifications through private systemd credentials with finite deadlines.
- Verify existing resolver and isolated collector CRL activation repairs.

## Capabilities

### New Capabilities

- `security/ansible-role-p1-safety`: critical role authority, availability and failure-boundary guarantees.

### Modified Capabilities

- None; this delta specifies audited safety behavior across existing roles.

## Impact

- Ansible runtime roles and their Python/shell/systemd templates, regression tests and snapshots.
- Notification secrets keep their existing input schema; generated delivery changes to systemd credentials.
- Retained dead-man state changes to an explicit generation-bound contract without legacy inference.
- No provider, Terraform, production deployment, credential issuance or retired monitoring activation.
