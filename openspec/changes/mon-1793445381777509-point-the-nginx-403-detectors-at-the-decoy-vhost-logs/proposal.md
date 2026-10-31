# Change: Point the nginx 403 detectors at the decoy vhost logs

Task ID: `MON-1793445381777509`

## Why

The watchdog's `nginx_403_spike` class and the daily probing summary count HTTP 403 responses from `/var/log/nginx/access.log`, nginx's stock `http`-level log. Every role-managed vhost (nginx-xhttp primary and fallback, reality-self-steal) declares its own `access_log`, and the roles remove the distribution's default site, so the stock log never receives a decoy request. Both detectors have therefore been blind to the decoy since the vhost logs were introduced; `SEC-1793428368283759` pinned the `vpn_public` status column these consumers rely on and recorded this gap as a follow-up.

## What Changes

- The watchdog counts 403 responses across the decoy vhost logs (`vpn-xhttp.access.log`, `vpn-xhttp-fallback.access.log`, `reality-self-steal.access.log`) instead of the stock log, keeps tolerating absent files, and keeps honouring `ENABLE_NGINX_XHTTP`.
- `scripts/probing-summary-remote.py` reads the same vhost logs for its nginx 403/444 counts.
- No BREAKING change: no variable, secret, listener, log format or operator input changes; the alert class name and threshold stay the same.

## Capabilities

### New Capabilities

- `monitoring/nginx-status-detectors`: the nginx status-code detectors read the logs the decoy vhosts actually write.

### Modified Capabilities

- None.

## Impact

Ansible role `watchdog` (`templates/vpn-watchdog.sh.j2`, role note), `scripts/probing-summary-remote.py`, their rendered and unit tests, the watchdog script golden. No Terraform, secrets, schema, listener or client change. Operators see the `nginx_403_spike` class fire for the first time on real probe bursts after the next deployment.
