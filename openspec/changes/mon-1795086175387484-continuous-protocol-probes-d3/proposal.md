# Change: Export continuous per-protocol authenticated probe and aggregate peer metrics

Task ID: `MON-1795086175387484`

## Why

Sentinel `protocol-liveness` and `probe-matrix` produce results, but the per-protocol authenticated probe is not a continuous metric for all four protocols, and AmneziaWG and Hysteria2 have no aggregate server-side usage signal comparable to `xray-stats-exporter`. Part of epic `EPC-1795085241910080`. Needed by D4 (bundle health) and D5 (block detection).

## What Changes

- Make authenticated probes for VLESS+REALITY, XHTTP, Hysteria2 and AmneziaWG continuous metrics, reusing `scripts/protocol-liveness.py`, `scripts/monitor-protocol-liveness.py`, `scripts/probe-matrix-driver.py` and `scripts/cascade-leg-probe.py`.
- Add aggregate-only exporters for AmneziaWG (fresh handshake count) and Hysteria2 (traffic API), modelled on `ansible/roles/monitoring/files/xray-stats-exporter.py`.
- Counterpart RIPDPI work: none directly; R4 consumes the resulting health through bundle v3 (D4).
- Overlap note: `topology-authenticated-probes` (`MON-1791618056169855`, done) and the `payload-verified-probes` spec already cover authenticated transport health. This change extends them to continuous per-protocol metrics only and does not redefine the probe protocol.

## Capabilities

### New Capabilities

- `operations/continuous-protocol-probes`: continuous probe metrics and aggregate peer exporters.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/protocol-liveness.py`, `scripts/monitor-protocol-liveness.py`, `scripts/probe-matrix-driver.py`.
- Ansible: `ansible/roles/liveness-sentinel/`, `ansible/roles/monitoring/`, `ansible/roles/amneziawg/`, `ansible/roles/hysteria/`, `ansible/roles/observability_control_plane/templates/observability-protocol-liveness-adapter.*.j2`.
- Contracts: `contract/observability-metric-manifest.example.json`, `contract/protocol-liveness.schema.json`.
