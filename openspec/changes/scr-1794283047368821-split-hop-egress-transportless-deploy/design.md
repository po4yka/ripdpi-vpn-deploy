## Context

The SSH baseline transaction changes sshd on a node and promotes the change only after fresh management checks and an external sentinel proof that the node's client transports still work (`scripts/sshd-promotion-proof.py`). The proof validator requires a non-empty transport profile set. A split-hop egress Node B has no client transport, so `make deploy` cannot converge it. See `proposal.md`.

## Goals / Non-Goals

- Goal: converge a split-hop egress node through the canonical `make deploy` path.
- Goal: no host that publishes, or may publish, a client listener can skip the sentinel proof.
- Non-goal: a new probe that proves Node B's tunnel or NAT from outside. Node B starts the tunnel to Node A, which may not exist yet when B is first deployed; topology acceptance stays in the pilot runbook.
- Non-goal: listener-free purposes for the Vultr, Hetzner and Scaleway roots.

## Decisions

- **A typed promotion kind, not an empty profile list.** `no-public-listener` is a separate schema-1 document with exactly `schema_version`, `kind` and `target_identity`. Rejected: allowing `required_profiles: []` in the sentinel proof. That would make "no proof" a reachable state of the general proof for any node.
- **Admission is derived from canonical inputs, never declared by the operator.** The controller admits the kind only when the host's own inventory row records the provider listener contract as `[]`, no shadowing source (group-wide `[vpn:vars]`, operator override, deployed secrets) sets that key, and the effective `vpn` (Ansible replace semantics, same resolver as the Tailnet toggle) enables `split-hop-egress` and sets the four client transport toggles explicitly to false. Explicit false is required because `site.yml` runs Hysteria and AmneziaWG when their toggles are absent, while the runtime listener manifest treats absent toggles as off; an empty manifest alone could therefore hide a running UDP listener.
- **The baseline controller skips only the sentinel proof.** `prepare_promotion` returns the parsed document for this kind; `_execute_validated` binds it to the exact target before prepare and skips the post-apply proof call. Fresh status RPC and SFTP on every management transport, the final status, confirm, rollback and failure receipts are unchanged. Rejected: a stub proof that returns a synthetic receipt, which would present missing evidence as a pass.
- **UpCloud `node_purpose = "split-hop-egress"`.** It reuses the observer precedent: an empty listener set is accepted only for a non-VPN purpose, and that purpose must disable legacy listeners and Hysteria. UpCloud is the only root with a guarded disposable staging cleanup for all four profiles, so the pilot pair can run there.

## Contracts and ownership

- `scripts/no_listener_promotion.py` owns the kind, its validator and the admission predicate; both controllers import it.
- `scripts/deploy-controller.py` owns admission (`listener_free_hosts`, `effective_vpn`) and skips `--validate-config` for this kind.
- `scripts/sshd-baseline-controller.py` owns the transaction branch.
- `terraform/providers/upcloud` owns the `split-hop-egress` purpose.
- The operator `DEPLOY_PROMOTION_CONFIG_FILE` mapping gains one document kind; the sentinel proof schema is unchanged.

## Risks / Trade-offs

- A listener-free node's SSH change is promoted on management evidence only → acceptable because it has no client data plane to break; the runtime listener preflight still runs before the SSH transaction and refuses a runtime listener that the empty provider contract does not declare.
- A future client transport toggle outside the four checked toggles → the runtime listener manifest and the provider contract still have to agree, and the provider root refuses listeners for this purpose.
- Only the deployment controller checks admission; the baseline controller trusts its controller-written promotion path → the path is a controller-owned Ansible variable that the extra-vars allowlist cannot set.

## Migration Plan

Additive: existing promotion kinds, nodes and tfvars are unchanged. Rollback is a revert of this change; a Node B already deployed with the kind keeps running and is then managed only by destroying it, as the pilot tear-down already requires.
