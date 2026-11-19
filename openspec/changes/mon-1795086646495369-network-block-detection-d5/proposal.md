# Change: Detect network blocks from sentinel and client-report divergence

Task ID: `MON-1795086646495369`

## Why

A server that looks healthy to the sentinel can be unreachable from one network. Sentinel (D3) plus client reports (D2) together show this. Part of epic `EPC-1795085241910080`; blocked by D2 (`SEC-1795086333272606`) and D3 (`MON-1795086175387484`).

## What Changes

- New alert rule joining sentinel probe success with client failure ratio by protocol and ASN.
- A rotation-hint output that `scripts/fleet-rotate.sh` PLAN can show; rotation is never started automatically.
- Overlap note: `fleet-health-rotation` (existing spec) owns rotation decisions; this change only adds an input hint and does not change rotation semantics. `MON-1794126016474351` (Telegram alert messages, doing) owns message format; new alerts here follow its action and runbook annotation rules.
- Counterpart RIPDPI work: R3 supplies the failure-stage data this alert reads; R4 handles failover while the operator decides.

## Capabilities

### New Capabilities

- `operations/network-block-detection`: divergence alert and rotation hint.

### Modified Capabilities

- None; rotation semantics in `fleet-health-rotation` are unchanged.

## Impact

- Ansible: `ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2` and test template, runbook anchor in `docs/reference/observability-operations.md`.
- Scripts: `scripts/fleet-rotate.sh` PLAN output.
