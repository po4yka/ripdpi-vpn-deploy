---
id: SEC-1793428368283759
title: Anonymize decoy-site nginx access logs
kind: bug
status: review
area: security
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793428368283759-anonymize-decoy-site-nginx-access-logs
created: 2026-10-31
updated: 2026-10-31
related_tasks: [SEC-1793386547449444]
status_detail: Implementation and local gates complete; pull request pending
---

## Goal

The public decoy vhosts of nginx-xhttp (primary and fallback) and the loopback reality-self-steal site write access logs without client address, remote user or user agent, so a seized node carries no visitor ledger for the decoy. The watchdog `nginx_403_spike` detector and the probing summary keep reading the status code from the same field, and monitoring retains seven daily nginx rotations instead of fourteen. Closes item 9 of the traffic-privacy audit that `SEC-1793386547449444` left out of scope.

## Acceptance criteria

- Rendered nginx-xhttp and reality-self-steal site templates declare a role-named `log_format` without `$remote_addr`, `$remote_user`, `$http_user_agent` or any forwarded-address variable, and every enabled `access_log` names it; transport, bearer and redirect surfaces stay `access_log off`.
- The format keeps `"$request" $status` adjacent with the status as the ninth field; a rendered-template test runs the watchdog detector's `awk` over rendered-format lines and counts the 403 responses.
- `logrotate-nginx.j2` renders `rotate 7` for `/var/log/nginx/*.log`.
- Snapshot goldens for both site templates are refreshed and reviewed; the touched unit tests, `make snapshot-check` and `make check` pass; CI is green at the pull-request head.
