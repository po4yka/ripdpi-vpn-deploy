# Change: Deploy a split-hop egress node that publishes no client listener

Task ID: `SCR-1794283047368821`

## Why

The split-hop pilot and the family egress change (`ANS-1794231660855533`) need a Node B that runs only the `split-hop-egress` role. Current `main` cannot deploy that node. `make deploy` requires an SSH promotion proof for every host, and the proof validator refuses an empty set of transport profiles, because the proof is an external sentinel that probes client transports. A node without client transports therefore has no path through the canonical deployment controller. The provider roots also refuse an empty public listener set; only the UpCloud observer purpose is exempt. Staging and live acceptance of the family egress change are blocked until this is fixed.

## What Changes

- The deployment controller accepts a schema-1 `no-public-listener` promotion kind. It admits the kind only for an explicit egress-only host: its own inventory row records an empty provider listener contract, no group-wide inventory variable, operator override or deployed secret sets that contract, and its effective `vpn` enables `split-hop-egress` and sets the four client transport toggles explicitly to false. Any other host is refused before the first SSH contact.
- The SSH baseline transaction binds that kind to the exact target identity and skips only the external sentinel proof. The fresh pinned status RPC and SFTP session on every management transport, confirm, rollback and failure receipts are unchanged.
- The UpCloud provider root accepts `node_purpose = "split-hop-egress"`. That purpose requires an empty public listener set, no legacy listeners and no Hysteria.
- The pilot runbook, the protocol liveness reference and the UpCloud README describe the Node B inputs.

## Capabilities

### New Capabilities

- `split-hop-egress-deployment`: deployment admission and SSH promotion for a node that publishes no client listener.

### Modified Capabilities

- None.

## Impact

- Terraform: UpCloud provider root variables, firewall preconditions and tests.
- Deployment controller (`scripts/deploy-controller.py`) and SSH baseline controller (`scripts/sshd-baseline-controller.py`), with a new shared module `scripts/no_listener_promotion.py`.
- Operator contract: the exact-alias `DEPLOY_PROMOTION_CONFIG_FILE` mapping gains one document kind. Existing kinds are unchanged.
- No change to Ansible roles, the sentinel proof or the secrets schema.
