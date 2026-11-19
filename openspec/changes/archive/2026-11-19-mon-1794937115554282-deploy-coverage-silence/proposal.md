# Change: Silence the external coverage alert during transport deploys

Task ID: `MON-1794937115554282`

## Why

A deploy or a credential rotation stops and restarts the transport services of the target node for about one minute. The node Kuma heartbeat requires every declared local service, so a heartbeat that runs in that window fails and `ObservabilityExternalCoverageUnavailable` fires as `critical` for the node. On 2026-11-17 a `device-lifecycle` rotation on one node produced this alert although the transaction succeeded and the new generation became ready 55 seconds later. Operators get a false critical notification for every planned transport restart, which trains them to ignore the alert that reports a real coverage loss.

The finite-silence gateway already gives a narrow, owner-bound, time-bounded silence, but only through a manual operator verb that is bound to the collector topology revision. No deploy path uses it.

## What Changes

- `make deploy` (deploy mode only, not dry-run) and the `rotate-credentials` goal of `device-lifecycle` create one finite maintenance silence on the collector's silence gateway before they mutate a node. The silence matches only `environment`, the node's `observability_node_id` and `component=observability-external-coverage`.
- After a successful mutation the controller creates a short tail silence that covers the alert's `for` and `keep_firing_for` interval, then deletes the main silence. After a failed or interrupted mutation it deletes the main silence without a tail, so a real outage still alerts.
- A silence failure prints one categorical warning and the deploy continues. Interruption leaves at most the finite silence, which Alertmanager expires itself.
- The silence is opt-in through explicit operator configuration. Without configuration the deploy behaves as before and prints nothing.

## Capabilities

### New Capabilities

- `operations/deployment-maintenance-silence`: automatic finite coverage silence for the exact node during transport mutation, its lifecycle, failure policy and configuration.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/deploy-controller.py`, `scripts/device_lifecycle_io.py`, a new shared helper beside them, and reuse of the gateway program in `scripts/observability-operator.py`.
- Makefile: the `deploy` recipe forwards the new optional configuration variables.
- Live systems: the controller reaches the collector host over SSH as root with the existing gateway owner token on that host; no new secret, role or template change. The owner named in the configuration must already exist in `observability_secrets.silence_gateway`.
- Documentation: `docs/how-to/deploy.md` and `docs/reference/observability-operations.md`.
