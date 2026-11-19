# MON-1795086847564764: Enforce observability retention and prove Telegram alert delivery

## Objective

Retention is documented and enforced for Prometheus, the vmagent queue, logs and field reports, and Telegram alert delivery is proven by a receipt.

## Ownership

One writer owns the retention docs, the retention test, retention flags in observability templates and the receipt schema entry. Does not edit `observability-alert-rules.yml.j2`.

## Execution

- [x] MON-1795086873036849 Add the retention table to docs/reference/observability-operations.md covering Prometheus, vmagent queue, logs, journal and field-report data #feature @item:MON-1795086847564764
- [x] MON-1795086901615679 Add a unit test in tests/unit/ that reads the rendered templates and fails on missing or unbounded retention values #feature @item:MON-1795086847564764
- [x] MON-1795086931324175 Set any missing retention flags in the observability_control_plane and observability_agent templates and refresh snapshots #feature @item:MON-1795086847564764
- [x] MON-1795086959007354 Add the delivery receipt record to contract/observability-evidence.schema.json and the drill in scripts/observability-operator.py without token or chat id #feature @item:MON-1795086847564764
- [ ] MON-1795086987482765 Record the authorized staging Telegram delivery receipt in verification.md #feature @item:MON-1795086847564764

## Verification

Local: the new retention unit test, `make snapshot-check`, `make docs-check`, then `make check`. Remote CI. Staging: delivery drill after explicit authorization. Live: not applicable.
