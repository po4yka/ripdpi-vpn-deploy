## Context

`ObservabilityExternalCoverageUnavailable` fires when the node heartbeat reports failure for one minute, and keeps firing for `recovery_stability` (3 minutes) after recovery. The node heartbeat runs every minute and refuses while any declared local service is inactive. A transport transaction stops `xray` and the private gateways for about one minute, so most deploys and rotations raise the alert. See proposal.md.

The finite-silence gateway runs on the collector at `127.0.0.1:19094`. It admits a request with `environment`, at least `node` or `policy`, optional stable labels including `component`, and a finite end within `max_ttl_seconds`. A named owner can delete only its own silences. The owner token lives only on the collector, under the fixed root-owned path that `_gateway_program` reads over root SSH. The manual verbs `make observability-silence-create/-delete` bind the collector inventory topology to the current clean source revision. A deploy of a new commit does not match that revision, so the deploy cannot reuse the manual verbs unchanged.

## Goals / Non-Goals

- Goal: no critical coverage notification for a planned transport restart of the node under change.
- Goal: real outages, failed deploys and every other alert for the node still notify.
- Goal: a silence failure never blocks or fails a deploy.
- Non-goal: silencing for `make dry-run`, `verify`, `observability-*` lifecycle verbs, blue-green or bootstrap.
- Non-goal: changing the alert rule, the heartbeat producer or the gateway.
- Non-goal: a new secret, owner provisioning or role change.

## Decisions

- Matchers are `environment`, `node` and `component=observability-external-coverage`. The `kind` label is not admitted by the gateway. For an ordinary node the node label limits the silence to its own coverage rule; for the collector node it also covers the `pipeline` and `delivery` coverage rules, which carry the collector's node id. A collector deploy therefore hides fleet pipeline and delivery coverage for its window; this is accepted because the site deploy leaves the observability components running and the window is bounded. Rejected: `environment` + `node` only, which would also hide transport, certificate and evidence alerts during the window.
- The silence wraps each node's mutating playbook: `site.yml` in deploy mode inside the per-host loop of `deploy-controller.py`, and the `rotate-credentials` goal in `device_lifecycle_io.runtime`. `verify` and check goals are outside the window. Rejected: one silence for the whole multi-host run, which would hide real loss on nodes that already converged.
- Main silence end: start + 7500 seconds, the per-host site timeout plus the create round trip. A gateway whose maximum TTL is lower refuses, and the deploy continues with a warning. Rejected: computing the end from the gateway policy, which the controller cannot read without new authority.
- On success the controller creates a 5-minute tail silence before it deletes the main one. 5 minutes covers the next heartbeat (1 minute), the alert `for` (1 minute) and `keep_firing_for` (3 minutes). Deleting first would release an already suppressed firing alert to Telegram. On failure or interruption the main silence is deleted with no tail, so a broken transport alerts after the normal detection time.
- Failure policy is warn-and-continue (operator decision). Every warning is one categorical line `deploy: warning: maintenance silence <category>`; no exception text, token or request reaches output.
- Configuration is three explicit settings, all or none: `DEPLOY_SILENCE_OWNER` (gateway owner slug), `DEPLOY_SILENCE_COLLECTOR` (collector inventory alias), `DEPLOY_SILENCE_ENVIRONMENT` (gateway environment label). `DEPLOY_SILENCE_INVENTORY` defaults to `ansible/inventory/generated.ini`. None set: disabled and silent. Some set: one configuration warning.
- Gateway access reuses `observability-operator.py`: exact-host selection in the control-plane section, the capability and topology binding of `_require_inventory_scope` with the collector's own inventory `env` and without source revision binding, `_gateway_program`, `_silence_program` and `_remote` report validation. A new public `maintenance_silence()` function in the operator exposes exactly create and delete. Create also requires the silenced node to be in the collector's topology, so a silence for a node the collector does not monitor is refused instead of matching nothing. Environment admission compares the collector with its own inventory `env`; the label in `DEPLOY_SILENCE_ENVIRONMENT` is enforced only by the gateway policy. Rejected: invoking the manual verb as a subprocess, which refuses on any new commit; a second gateway client, which would duplicate token handling.

## Contracts and ownership

- `scripts/observability-operator.py`: new `maintenance_silence(inventory, collector, known_hosts, owner, *, request=None, silence_id=None) -> str`.
- `scripts/deployment_silence.py` (new): `coverage_silence(node_id)` context manager, request rendering, configuration parsing and categorical warnings.
- `scripts/deploy-controller.py`: deploy mode wraps each host's `site.yml` call.
- `scripts/device_lifecycle_io.py`: wraps the `rotate-credentials` goal only.
- `Makefile`: the `deploy` recipe exports the four optional settings as literal values, also from `.fleet.mk`. `device-lifecycle` does not parse `.fleet.mk`; it reads the settings and `DEPLOY_KNOWN_HOSTS` from its inherited environment.
- Docs: `docs/how-to/deploy.md` (operator configuration), `docs/reference/observability-operations.md` (finite maintenance silences section).
- No secret schema, role, template, Terraform or vpnd change.

## Risks / Trade-offs

- A real outage that starts during a successful deploy's window is hidden up to the tail end → bounded to the deploy time plus 5 minutes and limited to the coverage component; transport, certificate and evidence alerts still fire.
- Controller death, or an interrupt during the create call, leaves the silence up to its end of about 2 hours → Alertmanager enforces the finite end; the warning policy forbids indefinite silences.
- Each create and delete adds one root SSH round trip to the collector (45 s bound) → only when configured.
- The collector admission check runs without source binding → the exact alias, collector capability, environment admission and topology node binding still apply; the silence carries no deploy or source authority.

## Migration Plan

Forward: merge, then the operator adds the three settings to the local fleet configuration with an owner that already exists in `observability_secrets.silence_gateway`. No host change is needed. Rollback: remove the settings (immediate) or revert the commit. Gates: unit tests for the context manager and both wiring points, `make docs-check`, `make check` (shared scripts), then one live deploy or rotation on a node with Telegram mode where the gateway audit shows create, tail and delete and no coverage notification arrives.
