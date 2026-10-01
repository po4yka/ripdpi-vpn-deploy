# Change: Deliver resource-bounded monitoring on existing VPN infrastructure

Task ID: `MON-1790835036464962`

## Why

Dedicated collector, deadman, and canary VPS nodes cost disproportionately much for a small VPN fleet. Reuse existing paid capacity while retaining useful metrics, the existing primary Telegram route, and an independently hosted missing-heartbeat alarm. A capacity failure must not silently turn into a new paid subscription or degraded VPN service.

## What Changes

- Co-host one private collector on an eligible existing VPN node, with measured resource and VPN-performance admission gates.
- Keep Prometheus, Alertmanager, and the credential-isolated primary relay; shorten retention and bound ingestion for the actual small fleet.
- Use managed Healthchecks heartbeats for each node and the primary alert pipeline, subject to explicit external-service consent and verified free-account capacity.
- BREAKING: replace dedicated-host observability topology with composable VPN/collector capabilities and a typed managed-watchdog configuration. Remove mandatory dedicated deadman and sentinel hosts from this topology; retain the separate client-path verification contract.
- BREAKING: use private-network mTLS ingestion without public DNS or public TLS ingress. Historical dedicated-staging evidence does not accept the new deployment.
- Distinguish local health, pipeline delivery, and authenticated external client-path evidence in every status surface. Missing evidence remains unknown, never healthy.

## Capabilities

### New Capabilities

- `operations/resource-bounded-observability`: bounded co-hosted metrics, independent managed heartbeats, safe migration, and evidence-based acceptance without dedicated VPS spending.

### Modified Capabilities

- None. The earlier dedicated-staging proposal remains historical, uncompleted work; this change defines the replacement intent rather than retroactively accepting it.

## Impact

- Ansible observability roles, shared nginx ownership, private PKI, SOPS schema and coverage, observability inventory/contract, Make/operator workflows, tests, snapshots, and runbooks.
- No new Terraform server, volume, DNS record, public firewall opening, paid service, or account is authorized by this proposal. Existing infrastructure lifecycle controls remain intact.
- Managed-watchdog consent, host admission, credentials, live deployment, and cutover remain explicit execution gates. Planning completion is not feature completion.
