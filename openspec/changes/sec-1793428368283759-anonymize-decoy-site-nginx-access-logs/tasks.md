# SEC-1793428368283759: Anonymize decoy-site nginx access logs

## Objective

The nginx-xhttp primary and fallback vhosts and the reality-self-steal vhost log ordinary requests without client address, remote user or user agent; the watchdog `nginx_403_spike` detector and the probing summary still read the status code unchanged; monitoring keeps seven nginx log rotations.

## Ownership

Primary: this repository. `ansible/roles/nginx-xhttp/templates/site.conf.j2`, `ansible/roles/reality-self-steal/templates/site.conf.j2`, `ansible/roles/monitoring/templates/logrotate-nginx.j2`, the matching role `CLAUDE.md` notes, `tests/unit/test_public_site_contract.py`, `tests/unit/test_nginx_xhttp_bearer_logs.py`, `tests/unit/test_watchdog_templates.py`, `tests/unit/test_monitoring_logrotate.py` and the snapshot goldens of both site templates. The watchdog script and `scripts/probing-summary-remote.py` are read, not edited.

## Execution

- [x] SEC-1793428548231362 Render role-named anonymous access-log formats for the decoy vhosts with the status field in the combined position, covered by rendered template, bearer-surface and watchdog detector tests #bug @item:SEC-1793428368283759
- [x] SEC-1793428549224587 Keep seven nginx log rotations, refresh snapshot goldens and role notes, and run the local gates #bug @item:SEC-1793428368283759

## Verification

Local: `python3 -m pytest` on the four touched test files, `make snapshot-update` with the golden diff reviewed, `make snapshot-check`, then `make check -j 4` once because the change spans two roles, monitoring and shared tests. Remote CI: the pull request's full run at the exact head. Dry-run, staging, live and client gates are not authorized by this change; no host is touched. Artifact: the two refreshed site goldens reviewed in the diff.
