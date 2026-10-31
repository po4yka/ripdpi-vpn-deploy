# MON-1793445381777509: Point the nginx 403 detectors at the decoy vhost logs

## Objective

The watchdog `nginx_403_spike` class and the probing summary count HTTP 403 responses from the decoy vhost access logs that nginx-xhttp and reality-self-steal actually write, instead of the stock `http`-level log that receives none of them.

## Ownership

Primary: this repository. `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2`, `ansible/roles/watchdog/CLAUDE.md`, `scripts/probing-summary-remote.py`, `tests/unit/test_watchdog_templates.py`, a new aggregator unit test, and the watchdog script golden. The nginx site templates and log formats are read, not edited.

## Execution

- [ ] MON-1793445429481835 Count nginx 403 responses from the decoy vhost access logs in the watchdog, tolerate absent files, and cover the rendered pipeline with a test over temporary log files #bug @item:MON-1793445381777509
- [ ] MON-1793445430745409 Read the same vhost logs in the probing summary aggregator with a unit test, update the role note and run the local gates #bug @item:MON-1793445381777509

## Verification

Local: `python3 -m pytest` on the touched test files, `make snapshot-update` with the golden diff reviewed, `make snapshot-check`, `make molecule-test ROLE=watchdog`, then `make check -j 4` once because the change spans a role and a shared script. Remote CI: the pull request's full run at the exact head. Dry-run, staging, live and client gates are not authorized by this change. Artifact: the refreshed watchdog golden reviewed in the diff.
