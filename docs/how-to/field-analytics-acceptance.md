# Field analytics staging acceptance

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL

## Purpose and scope

This runbook proves the whole field analytics chain on one staging node with one client device: a protocol blocked by DROP and then by RST, the client's failure-stage classification, the subscription-host ingest, the `FieldReportNetworkBlocked` alert, a degraded endpoint in a regenerated bundle, and client failover and recovery. It is the procedure for task `TST-1795087041877687`; record each result in that change's `verification.md`.

The run touches real infrastructure. It needs operator authority for the staging node, the collector and the device, and it follows the [acceptance scope and completion](deploy.md#acceptance-scope-and-completion) rules: record each claim as observed, failed or unverified, with its source revision, target, time and artifact. Production is out of scope; the block script refuses a production environment.

## Prerequisites

- A staging node deployed from the revision under test, with `subscription_field_report.enabled: true` on its subscription host, the collector relay listing that host in `observability_control_plane.field_report.source_nodes`, and the protocol-liveness adapter publishing `vpn_protocol_probe_success` for the node.
- A RIPDPI build that contains the field-report client and bundle v3 failover work (RIPDPI R2, R3 and R4). Record its version.
- One reusable device: a Pixel, or an emulator listed by `emulator -list-avds` and `adb devices`. Reuse an existing instance; create one only when none meets the API level, and give it a stable name.
- The client's public address seen by the staging node, if you want the block to affect only that device (`SOURCE`).
- A run directory for the artifacts, for example `runs/field-analytics-$(date -u +%Y%m%dT%H%M%SZ)` outside the repository.

The thresholds that the alert needs (attempts, distinct reports, hold) are in [the observability reference](../reference/observability-operations.md#field-report-alerts-and-the-network-block-decision). Lower them in the staging collector configuration for the run, or let the device produce enough reports; record which you chose.

## Choose the blocked endpoint

Pick one TCP protocol, because the RST case needs TCP: P0 REALITY on TCP/443 or P1 XHTTP on its configured port. Read the port from the staging inventory or the rendered public listener manifest, and the endpoint id (`server_ref`) from the bundle's `ripdpi.endpoints` keys.

```bash
export ENV=<staging env> PROVIDER=<provider> L4=tcp PORT=<protocol port>
# Optional: omit SOURCE to block every client.
export SOURCE=<client public address>
```

## Run the DROP case

1. Preview the rule. Nothing is contacted:

   ```bash
   MODE=drop scripts/field-analytics-block.sh plan
   ```

2. Apply it and note the time it prints:

   ```bash
   MODE=drop APPLY=1 scripts/field-analytics-block.sh block
   scripts/field-analytics-block.sh show
   ```

   The rule lives in its own `inet ripdpi_acceptance` table, whose input hook runs before the managed firewall table. It never edits the managed ruleset.

3. On the device, connect with the blocked protocol until the client records failures. Export or read its field report and record the failure stage: for DROP expect `tcp_connect`, `tls_handshake` or `idle_timeout`, as the taxonomy defines for that protocol. Force the client's report flush if the build has one; otherwise wait for its reporting window and record the wait.

4. On the collector, save the ingest evidence and check it. The Prometheus API is loopback-only, so query it over SSH:

   ```bash
   ssh <admin>@<collector> "curl -fsS 'http://127.0.0.1:9090/api/v1/query' --data-urlencode 'query=sum by (node, environment, protocol, failure_stage, asn) (vpn_field_report_failures_total)'" > "$RUN/drop-ingest.json"
   python3 scripts/field-analytics-evidence.py ingest "$RUN/drop-ingest.json" --protocol <protocol> --stage <expected stage>
   ```

   The check fails if a series carries a label outside the contract or an IP address. Also search the subscription host's nginx and ingest logs for the device address and record that it is absent:

   ```bash
   ssh <admin>@<subscription host> "sudo grep -rc '<client public address>' /var/log/nginx /var/lib/vpn-field-report; sudo journalctl -u vpn-field-report.service --no-pager | grep -c '<client public address>'"
   ```

5. When the alert hold has passed, save the alert list and check it:

   ```bash
   ssh <admin>@<collector> "curl -fsS http://127.0.0.1:9090/api/v1/alerts" > "$RUN/drop-alerts.json"
   python3 scripts/field-analytics-evidence.py alert "$RUN/drop-alerts.json" --protocol <protocol> --asn <client ASN>
   ```

   If Telegram delivery is authorized for staging, record the delivered message separately; a firing rule is not a delivery receipt.

6. Regenerate the staging bundle after the sentinel marks the endpoint failing, or inject the quorum input as the D4 generator documents, then check it at the time you captured it:

   ```bash
   python3 scripts/field-analytics-evidence.py bundle "$RUN/drop-bundle.json" --server-ref <server_ref> --at <capture instant>
   ```

7. Load that bundle on the device and record that traffic moves to another healthy endpoint, with the time it took.

## Run the RST case

Repeat steps 1 to 7 with `MODE=rst`. `block` replaces the DROP rule, because each run rewrites the whole private table. Expect the client to report `tcp_reset`. Save the artifacts as `rst-*.json`.

## Remove the block and confirm recovery

```bash
APPLY=1 scripts/field-analytics-block.sh unblock
# show prints "no acceptance block" once the table is gone.
scripts/field-analytics-block.sh show
```

`unblock` deletes the whole `inet ripdpi_acceptance` table and fails if it is still present. Then record that the sentinel probe returns to 1, the alert resolves, a fresh bundle shows the endpoint healthy or its old health expires, and the client returns to the original endpoint. Record the final node state (`show` output) and the device state in `verification.md`. Both block scripts append a best-effort audit record.

## Record the evidence

For each case record, in order and with UTC times: the block command output, the client failure stage, the ingest check line, the address search counts, the alert check line, the bundle check line, and the failover observation. Name the source revision, the deployable digest on the node, the app and bundle versions and the device. A failed or skipped observation stays failed or unverified; do not rerun a case only to replace a failure.
