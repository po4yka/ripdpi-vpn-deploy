## Context

`ansible/roles/watchdog/templates/vpn-watchdog.sh.j2` sets `nginx_access="/var/log/nginx/access.log"` and counts `awk '$9==403'` over its last 2000 lines; `scripts/probing-summary-remote.py` hard-codes `NGINX_ACCESS` to the same path and parses the `combined` layout. nginx writes a request to the `http`-level log only when the matching `server` block declares no `access_log` of its own; every role-managed public vhost does, and nginx-xhttp and reality-self-steal both remove `/etc/nginx/sites-enabled/default`. The vhost logs use the `vpn_public` and `vpn_self_steal` formats, whose status column position is pinned by `tests/unit/test_watchdog_templates.py`.

## Goals / Non-Goals

- Goal: both detectors count the decoy's 403 responses from the files that receive them, with unchanged class name, threshold and format assumptions.
- Non-goal: changing the log formats, adding a second `access_log` target to the vhosts, new alert classes, or changing the 7-day aggregation window.

## Decisions

- Read the three vhost logs directly in both consumers. Rejected: adding `access_log /var/log/nginx/access.log vpn_public;` to each vhost so the stock log receives a copy; it doubles disk writes for every request and makes the stock log a second retention surface for the same lines.
- The watchdog keeps one `tail -n 2000` per file and sums the `awk` counts, so the bound per file is unchanged; the path list is rendered from the template, not discovered with a glob, so an unrelated log cannot be counted.
- `probing-summary-remote.py` takes the log paths from a module-level tuple so a unit test can point it at a temporary directory through monkeypatching; no CLI flag is added.

## Contracts and ownership

- Ansible: `roles/watchdog/templates/vpn-watchdog.sh.j2`, `roles/watchdog/CLAUDE.md`; golden `tests/snapshot/golden/watchdog/templates/vpn-watchdog.sh.j2`.
- Scripts: `scripts/probing-summary-remote.py`.
- Tests: `tests/unit/test_watchdog_templates.py` (extend the detector test to run the rendered pipeline over temporary files), a new unit test for the aggregator next to the existing script tests.
- Unchanged: nginx-xhttp and reality-self-steal templates, logrotate, secrets, group_vars.

## Risks / Trade-offs

- The class may start firing on nodes that see scanner bursts today → the threshold (50 per 2000-line tail) is unchanged and was chosen for exactly that signal; the operator sees it through the existing alert path.
- Three tails instead of one add negligible work per watchdog tick.

## Migration Plan

Forward: the next `deploy` renders the watchdog script through the role's template task; the aggregator is copied by `scripts/probing-summary.sh` on each run. Rollback: revert the commit and redeploy. No provider, schema or client migration. Gates: `pytest` on the touched test files, `make snapshot-update` reviewed, `make snapshot-check`, `make molecule-test ROLE=watchdog` for the rendered script, `make check -j 4` once; remote CI at the pull-request head; no dry-run, staging, live or client gate is authorized.
