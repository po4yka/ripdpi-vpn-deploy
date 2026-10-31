## Context

`ansible/roles/nginx-xhttp/templates/site.conf.j2` and `ansible/roles/reality-self-steal/templates/site.conf.j2` end their public server blocks with a bare `access_log <path>;`, which selects nginx's default `combined` format (`$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"`). Both files are installed under `/etc/nginx/sites-enabled/`, inside the `http` context, so a file-level `log_format` is legal there (the nginx-xhttp template already declares a `limit_req_zone` at that level). The XHTTP locations, the Snell evaluation location, the alias redirect server and the plain-HTTP redirect servers are already `access_log off`. The watchdog's `nginx_403_spike` detector tails `/var/log/nginx/access.log` and counts `awk '$9==403'`; `scripts/probing-summary-remote.py` parses the same file with a `combined` regular expression; the native XHTTP endpoint test matches `"POST /auth HTTP/…" 404` in `vpn-xhttp.access.log`. `ansible/roles/monitoring/templates/logrotate-nginx.j2` keeps 14 daily rotations; the Xray policy keeps 7. The self-steal vhost listens on loopback, so its `$remote_addr` is always the Xray hop, but its user-agent column is the prober's.

## Goals / Non-Goals

- Goal: no client address, remote user or user agent in any decoy access log; status-code consumers unchanged; shorter retention.
- Goal: both site templates render a syntactically valid configuration on a node that runs both roles.
- Non-goal: changing which file the watchdog and the probing summary read. Both read the `http`-level default `access.log`, which the role-managed vhosts never write to because each declares its own `access_log`; that pre-existing gap is a separate detector task, not a format question.
- Non-goal: removing `$http_referer`, `$time_local`, the request line or the status (the remaining consumers need them), touching `error_log`, or changing the subscription-host categorical log, which already carries no identity.

## Decisions

- Keep the `combined` column layout and replace the removed fields with literal `-`: `- - - [$time_local] "$request" $status $body_bytes_sent "$http_referer" "-"`. Rationale: `$status` stays field 9 for the watchdog, the probing-summary regular expression (`^\S+ \S+ \S+ \[…\] "\S+ \S+ \S+" status`) still matches, the native endpoint test's `"$request" $status` match still holds, and any `combined`-aware tool reads the file. Rejected: a shorter layout (`[$time_local] "$request" $status …`) that would move the status to field 6 and require coordinated edits in the watchdog, the probing summary and the native test for no privacy gain.
- One format name per role: `vpn_xhttp_anonymous` in nginx-xhttp and `reality_self_steal_anonymous` in reality-self-steal. nginx refuses a duplicate `log_format` name across included files, and the two roles converge independently, so neither may own a shared snippet. The declaration sits at the top of each file so it precedes the `access_log` directives that reference it (nginx resolves format names at parse time).
- Retention drops to `rotate 7`, matching the Xray policy and the probing summary's seven-day window. Rejected: keeping 14 (the audit's concern is the corpus a seized node carries; the anonymous lines are still a timing ledger of probes).
- The watchdog script is not edited. A rendered test runs its `awk` program over lines synthesized from the rendered nginx-xhttp format, so a future layout change in either template fails the test instead of silently blinding the detector.
- `scripts/check-templates-render.py` strips `access_log` lines before `nginx -t` but leaves `log_format`, so the syntax check covers the new directive without a runner change.

## Contracts and ownership

- Ansible: `roles/nginx-xhttp/templates/site.conf.j2`, `roles/reality-self-steal/templates/site.conf.j2`, `roles/monitoring/templates/logrotate-nginx.j2`; role notes in each `CLAUDE.md` (nginx-xhttp pitfall on access logging, monitoring retention note).
- Tests: `tests/unit/test_public_site_contract.py` (format content for both templates), `tests/unit/test_nginx_xhttp_bearer_logs.py` (no enabled access log without the named format), `tests/unit/test_watchdog_templates.py` (detector reads the rendered format), `tests/unit/test_monitoring_logrotate.py` (retention), snapshot goldens under `tests/snapshot/golden/` for both site templates.
- Unchanged contracts: `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2`, `scripts/probing-summary-remote.py`, secrets schema, group_vars toggles, listener contract, client bundle.

## Risks / Trade-offs

- A malformed request line with a different token count already defeats positional parsing in `combined`; the anonymous layout neither improves nor worsens that.
- Losing the address column removes the only per-visitor key the decoy log had → accepted; abuse response for the public vhosts is nftables rate limiting and the status-code detectors, neither of which reads the address from this log.
- Seven rotations shorten the window a post-incident review can inspect → accepted; the probing summary already aggregates within seven days.

## Migration Plan

Forward: the next `deploy` renders the new site files through the existing compensated nginx transaction (validate, publish, reload) and the logrotate policy through the monitoring role; existing log files keep their names and the next lines use the anonymous layout; lines already written are rotated out within seven days. Rollback: revert the commit and redeploy; the same transactions restore the previous files. No provider, schema or client migration. Gates: targeted pytest files, `make snapshot-update` reviewed in the diff, `make snapshot-check`, `make check -j 4` once because the change spans two roles, monitoring and shared tests; remote CI at the pull-request head; no dry-run, staging, live or client gate is authorized by this change.
