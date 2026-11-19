---
task_id: TST-1795087041877687
change: tst-1795087041877687-field-analytics-e2e-d7
commit_sha: null
local: passed
local_evidence: The harness and runbook only; the run itself is not done. `tests/unit/test_field_analytics_acceptance.py` (27 tests: rendered DROP, RST and source-limited rules, refusals before any SSH contact, plan-only default, apply and unblock against stub terraform and ssh, and the ingest, alert and bundle evidence checks), docs index, docs reference, agent instructions and governance tests exit 0 (50 passed); shellcheck of `scripts/field-analytics-block.sh` exit 0; `make docs-check` exit 0. Logs are in the session run directory runs-secfix-d7 (d7-*.log). The nftables rule text was not loaded by a real `nft` on this machine.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No deploy controller or rendered input change.
staging: required
staging_evidence: Not run; no staging node, collector or device access is authorized in this session. Owner commands are in docs/how-to/field-analytics-acceptance.md, starting with `ENV=<staging env> PROVIDER=<provider> L4=tcp PORT=<port> MODE=drop scripts/field-analytics-block.sh plan`.
live: not_applicable
live_evidence: Production is out of scope.
client: required
client_evidence: Not run; needs the RIPDPI build with R2 to R4 and an authorized device. Owner commands are in docs/how-to/field-analytics-acceptance.md.
artifact: not_applicable
artifact_evidence: The evidence is in the verification file; no release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-E2E-CLASSIFY | TST-1795087099844740 | DROP and RST client report buckets | planned |
| REQ-E2E-INGEST | TST-1795087099844740 | staging Prometheus query output | planned |
| REQ-E2E-ALERT | TST-1795087099844740 | Alertmanager active alert | planned |
| REQ-E2E-BUNDLE | TST-1795087099844740 | generated bundle validated as v3 | planned |
| REQ-E2E-FAILOVER | TST-1795087151868733 | client logs and traffic observation before and after unblock | planned |

## Harness (local)

`TST-1795087071905692` delivers `docs/how-to/field-analytics-acceptance.md`, `scripts/field-analytics-block.sh` and `scripts/field-analytics-evidence.py`. The block script keeps the rule in its own `inet ripdpi_acceptance` table, prints a plan unless `APPLY=1`, refuses a production environment, the SSH port, RST over UDP and a malformed source, and `unblock` deletes the whole table and fails if it remains. The evidence checker turns the saved Prometheus query, alert export and bundle into PASS or FAIL lines.

## Owner run (not done)

Run on the staging node and the device with the build under test, then record each line below with its UTC time:

1. `ENV=<staging env> PROVIDER=<provider> L4=tcp PORT=<protocol port> MODE=drop APPLY=1 scripts/field-analytics-block.sh block` (add `SOURCE=<client address>` to limit it).
2. Client failure stage from the device report.
3. `python3 scripts/field-analytics-evidence.py ingest "$RUN/drop-ingest.json" --protocol <protocol> --stage <stage>` and the address search counts.
4. `python3 scripts/field-analytics-evidence.py alert "$RUN/drop-alerts.json" --protocol <protocol> --asn <client ASN>`.
5. `python3 scripts/field-analytics-evidence.py bundle "$RUN/drop-bundle.json" --server-ref <server_ref> --at <capture instant>` and the client failover time.
6. Repeat 1 to 5 with `MODE=rst` (expect `tcp_reset`).
7. `ENV=<staging env> PROVIDER=<provider> APPLY=1 scripts/field-analytics-block.sh unblock`, then `scripts/field-analytics-block.sh show`, sentinel recovery, alert resolution, fresh bundle health and the client back on the original endpoint.
