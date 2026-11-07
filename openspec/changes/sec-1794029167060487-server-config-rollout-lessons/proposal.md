# Change: Harden server configuration from rollout lessons

Task ID: `SEC-1794029167060487`

## Why

The production rollouts of the medium and remaining audit fixes exposed gaps that only showed on real nodes:
- The agent's self-steal certificate expiry series depended on a hand-set profile flag, and nothing alerted when it was missing.
- The observer's Kuma Telegram egress and private ingress rules existed only as out-of-repo rules on top of the Tailnet bootstrap foundation, which a re-run would erase.
- Operator tooling discarded Ansible output, reported a bare `BlockingIOError` for a busy node lock, and failed opaquely without the generated inventory.
- `AGENTS.md` contradicted the restored read deny on the operator kit.

## What Changes

- The agent enables the self-steal certificate series from the installed certificate on the host, and an alert fires when a node with self-steal reports no expiry series.
- The Tailnet bootstrap foundation renders the observer's private ingress and, in Telegram mode, the Kuma container egress.
- The observability operator records the failing task name without output; node locks refuse with a typed busy category; a missing generated inventory refuses with a typed category.
- Documentation records the kit access paths, the SOPS list-value limit and the Kuma push-token rule.

## Capabilities

### New Capabilities

- `security/rollout-hardening`: host-derived certificate monitoring, owned observer egress, and typed operator refusals.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/observability_agent/`, `ansible/roles/observability_control_plane/` alert rules.
- Scripts: `scripts/tailnet_firewall.py` and its callers, `scripts/observability-operator.py`, the deploy controller and maintenance entry points.
- Docs: `AGENTS.md`, `docs/reference/secrets.md`, `docs/reference/observability-operations.md`.
