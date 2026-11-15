## Context

`cloud_promotion_scope._sentinel` resolves the sentinel's resolved SSH settings, checks its pinned host key and runs a fixed guest probe that returns the hostname, host key digest and cloud-init marker. Until now it accepted only the state-derived public IPv4 as transport. `protocol-liveness` and the sentinel installer already accept any paired `ssh_transport_host` and `ssh_host_key_alias`, so the scope check was the only place that tied the route to the public address.

## Goals / Non-Goals

- Goal: production deploys can prove the sentinel over the existing Tailnet management path when the operator's public source is not admitted.
- Goal: the reached sentinel stays bound to the Terraform-state resource.
- Non-goal: changing the probe vantage; probes still leave from the sentinel's public address.
- Non-goal: re-admitting rotating operator addresses in the provider firewall.

## Decisions

- Bind the Tailnet route through the pin file. The known-hosts entry `alias,public-address ssh-ed25519 <key>` already records that the inventory alias and the state address share one host key, so equal key sets for both lookups prove the same server. Rejected: trusting the Tailnet address alone, which a reassigned or foreign Tailnet node could answer.
- Recognize Tailnet only by Tailscale's address ranges. Rejected: accepting any non-public address, which would also admit loopback or LAN routes.
- Use the inventory alias as host key alias on the Tailnet route, as fleet inspection does for its Tailnet contexts.

## Contracts and ownership

- `scripts/cloud_promotion_scope.py` (`_sentinel`) and `tests/unit/test_cloud_promotion_scope.py`.
- Operator configuration only: the private liveness record and the sentinel pin file. No schema change; `contract/protocol-liveness.schema.json` already allows both fields.

## Risks / Trade-offs

- A pin file without the alias on the public-address line refuses the Tailnet route → the operator adds the alias to the existing pinned line; the key itself does not change.
- Tailscale could change its address ranges → the refusal is fail-closed; update the constant.

## Migration Plan

No migration. Existing public-route records keep working unchanged. To use the Tailnet route, set the sentinel's Tailnet address and inventory alias in the private liveness record and the SSH alias. Rollback is restoring the public-address record. Gates: unit tests, PR CI, then a production `prepare`, dry-run and deploy for the exact node with the Tailnet route.
