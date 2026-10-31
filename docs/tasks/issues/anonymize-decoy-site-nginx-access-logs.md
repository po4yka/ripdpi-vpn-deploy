---
id: SEC-1793428368283759
title: Anonymize decoy-site nginx access logs
kind: bug
status: done
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
closed_at: "2026-10-31T12:26:33Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Decoy vhost access logs carry no client identity (vpn_public, vpn_self_steal; formats merged via #432, layout contract and both-site nginx -t pinned by tests), monitoring keeps seven nginx rotations; integrated as 62f758d3 (#431); remote CI run 2105 green on 06a093cd; task MON-1793445381777509 tracks the blind 403 detectors."
---

## Goal

The public decoy vhosts of nginx-xhttp (primary and fallback) and the loopback reality-self-steal site write access logs without client address, remote user or user agent, so a seized node carries no visitor ledger for the decoy. The watchdog `nginx_403_spike` detector and the probing summary keep reading the status code from the same field, and monitoring retains seven daily nginx rotations instead of fourteen. Closes item 9 of the traffic-privacy audit that `SEC-1793386547449444` left out of scope.

## Acceptance criteria

- Rendered nginx-xhttp and reality-self-steal site templates declare role-named formats (`vpn_public`, `vpn_self_steal`) without `$remote_addr`, `$remote_user`, `$http_referer` or `$http_user_agent`, every enabled `access_log` names them, and both site files load into one `nginx -t`; transport, bearer and redirect surfaces stay `access_log off`.
- The format keeps `"$request" $status` adjacent with the status as the ninth field; a rendered-template test runs the watchdog detector's `awk` over rendered-format lines and counts the 403 responses.
- `logrotate-nginx.j2` renders `rotate 7` for `/var/log/nginx/*.log`.
- The nginx logrotate golden is refreshed and reviewed; the touched unit tests, `make snapshot-check` and `make check` pass; CI is green at the pull-request head.
