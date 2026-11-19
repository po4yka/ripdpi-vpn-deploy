# MON-1795086646495369: Detect network blocks from sentinel and client-report divergence

## Objective

An alert says a protocol is blocked in a network (ASN) when the sentinel reports healthy but client failures spike for that ASN, and it outputs a rotation hint for the fleet-rotate PLAN; the operator still decides.

## Ownership

One writer owns the alert rule additions, the PLAN hint in `scripts/fleet-rotate.sh`, and the runbook section. Serialized lane for the alert template after D2 and D3.

## Execution

- [x] MON-1795086667788936 Add the blocked-in-network alert rule with action and runbook annotations to observability-alert-rules.yml.j2 #feature @item:MON-1795086646495369
- [x] MON-1795086687652889 Add promtool cases for divergence, server-down and low-sample in observability-alert-rules.test.yml.j2 #feature @item:MON-1795086646495369
- [x] MON-1795086713751110 Add the advisory rotation hint to scripts/fleet-rotate.sh PLAN mode with a test that no rotation starts #feature @item:MON-1795086646495369
- [x] MON-1795086734829714 Document the alert, thresholds and operator decision flow in docs/reference/observability-operations.md with the anchored runbook section #feature @item:MON-1795086646495369

## Verification

Local: promtool via `make validate`, `make snapshot-check`, the fleet-rotate unit tests, `make docs-check`, then `make check`. Remote CI. Staging: the alert is fired during D7. Client: provided by D7 with RIPDPI R3.
