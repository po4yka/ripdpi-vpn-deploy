# Change: Deliver correct field analytics of network blocking, client connections and VPN health

Task ID: `EPC-1795085241910080`

## Why

Server monitoring is rich (vmagent to Prometheus, about 40 alert rules, Kuma, watchdog, sentinel protocol-liveness, cascade-leg-probe, probe-matrix, xray-stats-exporter), but `docs/reference/protocol-liveness.md` states that client-path health is unknown. The app sends nothing to the server, and the only client contract is `contract/ripdpi-bundle.schema.json` v2. The operator cannot tell "server healthy, network blocks it for ASN X" from "server down". The owner decided on opt-in, anonymous, aggregated client field reports.

Priority rationale (2026-11-26): almost all external evidence about blocking is single-vantage, and `docs/explanation/threat-model.md` states that CI measures only the unfiltered half. Opt-in client reports aggregated by client ASN and server ASN, with no IP addresses, are the only source that closes both gaps. Deliver D2, then D3, then D5 ahead of other monitoring work. The external evidence is single-source and unverified.

## What Changes

- Define the client field-report contract and ripdpi-bundle v3 (child D1). BREAKING: bundle v3 replaces v2; v2 is rejected, with no compatibility shim.
- Ingest field reports into bounded Prometheus metrics (D2).
- Make per-protocol authenticated probes continuous and add aggregate peer exporters (D3).
- Generate bundle v3 with endpoint health and field-report configuration (D4).
- Detect network blocks from sentinel versus client divergence (D5).
- Enforce retention and prove Telegram alert delivery (D6).
- Accept the whole chain end to end with a real client (D7).
- Counterpart RIPDPI work (tracked in the RIPDPI repository): R1 remove embedded secrets from app assets, R2 vendor contracts and the failure-stage taxonomy, R3 opt-in field-report client, R4 bundle v3 health in failover.

## Capabilities

### New Capabilities

- `operations/field-analytics-program`: ordering, dependency and acceptance rules for the program.

### Modified Capabilities

- None. Each child change owns its own capability delta.

## Impact

- Contracts: `contract/`, `scripts/validate-bundle.py`, `scripts/emit-bundle.sh`, `docs/reference/ripdpi-bundle.md`.
- Layers: Ansible roles `observability_control_plane`, `subscription-host`, `liveness-sentinel`; scripts; docs.
- Cross-repository: `po4yka/RIPDPI` R1-R4.
