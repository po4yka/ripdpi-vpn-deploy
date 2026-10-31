---
id: MON-1793445381777509
title: Point the nginx 403 detectors at the decoy vhost logs
kind: bug
status: backlog
area: monitoring
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: mon-1793445381777509-point-the-nginx-403-detectors-at-the-decoy-vhost-logs
created: 2026-10-31
updated: 2026-10-31
related_tasks:
  - SEC-1793428368283759
---

## Goal

The watchdog `nginx_403_spike` class and `scripts/probing-summary-remote.py` count HTTP 403 responses from the access logs the decoy vhosts write (`vpn-xhttp.access.log`, `vpn-xhttp-fallback.access.log`, `reality-self-steal.access.log`). Today both read nginx's stock `/var/log/nginx/access.log`, which the role-managed vhosts never write to because each declares its own `access_log`, so a probe burst against the decoy is never counted. Follow-up recorded by `SEC-1793428368283759`.

## Acceptance criteria

- The rendered watchdog pipeline, run over temporary files, counts 403 lines across the three vhost logs, reports 0 for lines in the stock log, tolerates an absent file, and keeps the `nginx_403_spike` name and threshold.
- The aggregator counts 403/444 lines across the same files in a unit test over a temporary directory.
- Watchdog golden refreshed and reviewed; `make molecule-test ROLE=watchdog`, the touched unit tests and `make check` pass; CI is green at the pull-request head.
