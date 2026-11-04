# SEC-1793770690402026: Add daily security checks and systemd reports

## Objective

Run daily dependency and pinned-image scans with owner notifications, and
retain private systemd isolation diagnostics in the explicit audit.

## Ownership

One writer owns .github/workflows/daily-security.yml, image-scan.yml,
scripts/notify-security-scan.cjs, tests/unit/test_daily_security_checks.py,
tests/unit/test_audit_improvement_host_contracts.py, security_audit/tasks/systemd.yml,
the role CLAUDE.md, .github/SECURITY.md and docs/reference/testing.md.
Task, specification and generated-board changes are serialized through taskctl.

## Execution

- [x] SEC-1793771107840507 Implement daily scans, change notifications and private systemd security reports with regression coverage #feature !high @item:SEC-1793770690402026

## Verification

Run focused pytest regressions, actionlint, zizmor, ansible-lint and make check.
Run one independent source review before the local commit. Hosted execution,
GitHub delivery, host audit deployment and live acceptance are outside this scope.
