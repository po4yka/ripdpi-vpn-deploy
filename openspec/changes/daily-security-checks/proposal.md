# Change: Add daily security scans and systemd isolation reports

Task ID: `SEC-1793770690402026`

## Why

New advisories can affect unchanged dependencies and pinned images between CI
runs. The host audit also lacks a systemd isolation assessment.

## What Changes

- Scan locked repository dependencies and existing pinned images each day.
- Notify the repository owner through a GitHub issue when findings or scan
  failures change, and close the issue after a complete clean run.
- Collect a private, non-blocking `systemd-analyze security` report during the
  existing explicit host audit.
- No breaking changes. Cloudflare, SSH and live infrastructure are outside scope.

## Capabilities

### New Capabilities

- `ci/daily-security-checks`: scheduled scans and change-based notifications.

### Modified Capabilities

- `operations/ansible-role-audit-improvements`: systemd isolation report collection.

## Impact

- GitHub Actions, the existing image scan workflow, and the Ansible audit role.
- Reuse pinned tooling; add no production dependency or credential requirement.
- Local source delivery only; no push, deployment or real notification drill.
