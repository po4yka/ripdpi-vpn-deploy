## Purpose

The nginx status-code detectors on a node read the access logs the decoy vhosts write, so a 403 burst against the public site is counted instead of silently missed.

## ADDED Requirements

### Requirement: REQ-NGX403-VHOST-SOURCE — The watchdog counts 403 responses from the decoy vhost logs

The rendered watchdog script MUST count HTTP 403 responses across `/var/log/nginx/vpn-xhttp.access.log`, `/var/log/nginx/vpn-xhttp-fallback.access.log` and `/var/log/nginx/reality-self-steal.access.log` (each bounded to its recent tail), MUST treat an absent or unreadable file as zero lines, MUST keep the `nginx_403_spike` class name and its threshold, and MUST skip the detector when `ENABLE_NGINX_XHTTP` is `false`.

#### Scenario: Burst in the fallback log only

- **WHEN** the pipeline from the rendered script runs with 60 `vpn_public` lines carrying status 403 in the fallback log and an empty primary log
- **THEN** it reports 60 and the `nginx_403_spike` class is set.

#### Scenario: Self-steal log absent

- **WHEN** the reality-self-steal log does not exist
- **THEN** the detector still counts the nginx-xhttp logs and exits without an error.

#### Scenario: Stock log ignored

- **WHEN** only `/var/log/nginx/access.log` contains 403 lines
- **THEN** the detector reports 0.

### Requirement: REQ-NGX403-SUMMARY-SOURCE — The probing summary reads the same vhost logs

`scripts/probing-summary-remote.py` MUST aggregate nginx 403 and 444 responses from the same three vhost logs, MUST skip files that do not exist, and MUST keep parsing the `vpn_public` layout (request line followed by the status).

#### Scenario: Aggregation across files

- **WHEN** the aggregator runs against a directory with a primary log holding two 403 lines inside the window and a self-steal log holding one 444 line
- **THEN** the nginx count is 3 and the hourly table attributes each line to its hour.

#### Scenario: Rollback

- **WHEN** the change is reverted and the watchdog role redeploys
- **THEN** the previous script is restored by the role's ordinary template task; no state migration is needed.
