# SEC-1795086333272606: Ingest opt-in client field reports into bounded Prometheus metrics

## Objective

The subscription host accepts anonymous client field reports on one POST endpoint, validates and rate-limits them, and aggregates them into Prometheus metrics with bounded labels and alerts on failure rate by protocol and ASN.

## Ownership

One writer owns `ansible/roles/subscription-host/` ingest files, the new metric manifest entries and the alert rule additions. The alert rule template is a serialized lane shared with D3, D5 and D6.

## Execution

- [x] SEC-1795086358982402 Add the ingest process under ansible/roles/subscription-host/files/ with schema validation, cohort token check, minimum-attempt drop and bounded aggregation #feature !high @item:SEC-1795086333272606
- [x] SEC-1795086384171666 Add the nginx location with body size and limit_req settings and no client IP in the access log format in ansible/roles/subscription-host/templates/ #feature !high @item:SEC-1795086333272606
- [x] SEC-1795086408877793 Register the new metrics in contract/observability-metric-manifest.example.json and add the failure-rate alert with a promtool case in observability-alert-rules.yml.j2 and observability-alert-rules.test.yml.j2 #feature !high @item:SEC-1795086333272606
- [x] SEC-1795086432958533 Add unit tests in tests/unit/ for the status codes, label bounds, no-IP logging and attempts floor #feature !high @item:SEC-1795086333272606
- [x] SEC-1795086456490841 Run the security-review skill on the endpoint and record findings in verification.md #feature !high @item:SEC-1795086333272606
- [x] SEC-1795104397840245 Label field-report metrics by network source (MCC-MNC for sim, AS number for server_hint, unknown for none) with separate operator and ASN top-N rankings, and alerts per operator or per ASN #feature !high @item:SEC-1795086333272606
- [x] SEC-1795104413322531 Add the network-hint GET endpoint with cohort-token auth, nginx per-address limit, peer address from nginx only and refused client forwarding headers, a pinned offline IP-to-ASN dataset and its operator refresh script #feature !high @item:SEC-1795086333272606
- [x] SEC-1795104428184651 Rerun the security-review skill on the network-source and network-hint amendment and record the verdict in verification.md #feature !high @item:SEC-1795086333272606

## Verification

Local: `python3 -m pytest` for the new unit tests, `make snapshot-check`, promtool via `make validate`, `make molecule-test ROLE=subscription-host`, then `make check`. Remote CI on the pull request. Dry-run: role dry-run only after explicit authorization. Staging: endpoint exercised on a staging node (D7 owns the full chain). Security review recorded.
