# MON-1795086175387484: Export continuous per-protocol authenticated probe and aggregate peer metrics

## Objective

Sentinel and probe-matrix authenticated probes for VLESS+REALITY, XHTTP, Hysteria2 and AmneziaWG run continuously and export per-protocol Prometheus metrics, and aggregate (not per-user) exporters exist for AmneziaWG and Hysteria2.

## Ownership

One writer owns the probe scripts, the two exporter files and their units, and the manifest entries. Serialized shared lane: `observability-alert-rules.yml.j2` and the metric manifest with D2, D5 and D6.

## Execution

- [x] MON-1795086204601885 Audit which of the four protocols already have continuous authenticated probe metrics in scripts/protocol-liveness.py, scripts/monitor-protocol-liveness.py and scripts/probe-matrix-driver.py and record the gaps in design.md #feature !high @item:MON-1795086175387484
- [x] MON-1795086235920434 Implement the missing continuous probe metrics with the protocol, node and vantage labels and stale-as-unknown handling #feature !high @item:MON-1795086175387484
- [x] MON-1795086265502933 Add the AmneziaWG aggregate handshake exporter under ansible/roles/amneziawg/ with a timer unit and no per-peer output #feature !high @item:MON-1795086175387484
- [x] MON-1795086286466850 Add the Hysteria2 aggregate traffic exporter under ansible/roles/hysteria/ using the loopback traffic API #feature !high @item:MON-1795086175387484
- [x] MON-1795086307543709 Register all new metrics in contract/observability-metric-manifest.example.json and add tests in tests/unit/ for stale, auth failure, and aggregate-only output #feature !high @item:MON-1795086175387484

## Verification

Local: focused `python3 -m pytest` of the new tests, `make molecule-test ROLE=amneziawg` and `ROLE=hysteria`, `make snapshot-check`, then `make check`. Remote CI. Dry-run only if rendered deployment input changes and after authorization. Staging: probes and exporters on a staging node. Client: not applicable (server-side signal).
