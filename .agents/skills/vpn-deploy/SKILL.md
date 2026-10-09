---
name: vpn-deploy
description: Deploy reviewed runtime changes to exact existing VPN nodes through the canonical dry-run and deployment transaction. Use after provisioning and management enrollment; fresh-node setup uses vpn-bootstrap, evidence-only checks use vpn-acceptance.
---

# Deploy exact VPN nodes

Use [the ordinary re-deploy recipe](../../../docs/RUNBOOK-deploy.md#ordinary-re-deploy-recipe) as the command and input contract.

## Freeze scope and inputs

1. Run root workspace discovery and resolve the selected task/change, clean immutable source, deployable digest, exact inventory aliases, provider/environment and changed layer. Preserve prior authorization within its resource, action, cost and time bounds; inspect current identities and capabilities at action time. `ENV` selects a Terraform workspace, not Ansible host scope.
2. Check the existing recovery generation, confirmed Tailnet identity, completed SSH ownership migration and fresh dual-path contexts. Route missing first-enrollment state to `vpn-bootstrap` within existing authority. Ordinary deploy validates installed state; it cannot invent enrollment or repair missing receipts.
3. Prepare the selected private runtime secrets and all three exact-alias mappings: `DEPLOY_SSH_CONTEXTS_FILE`, `DEPLOY_PROMOTION_CONFIG_FILE`, and `DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE`. Use fresh baseline-failure output sinks. Clear enrollment credentials. Keep plaintext, keys, state and token-bearing output out of the transcript; preserve unique device identities.
4. For first disposable staging onboarding, use [the intent workflow](../../../docs/PROTOCOL-LIVENESS.md#first-onboarding-during-a-disposable-staging-deployment) prepared by `vpn-bootstrap`. An ordinary successful `dry-run` neither validates that onboarding capability nor supplies the required protocol proof.

## Execute the transaction

Use the runbook's fail-fast shell grouping and EXIT plaintext-cleanup trap for any copyable or executed multi-command sequence.

1. Run the affected local gates and the runbook's `make decrypt` / `make validate` preflight, then `make dry-run ANSIBLE_LIMIT='<exact-alias>' ANSIBLE_TAGS=`. Review all changes before mutation. The explicit empty tags retain the full graph; tagged deploy has no matching tagged dry-run contract.
2. A failed preflight or unexpected change stops `deploy`. Diagnose and fix the source or required input, rerun the relevant checks, and obtain a new decision only if the solution exceeds authority. Do not convert an incomplete preflight into a pass by filtering roles or weakening recovery/security gates.
3. After successful review, run `make deploy ANSIBLE_LIMIT='<exact-alias>' ANSIBLE_TAGS=`, then `make verify ANSIBLE_LIMIT='<exact-alias>'` and the applicable source-parity check. The controller owns readiness snapshots, serial exact-node writes, runtime transactions and promotion proofs. Let a failed or interrupted transaction reconcile its existing generation; retain diagnostic/authority artifacts rather than deleting them for a retry.
4. Route live acceptance to `vpn-acceptance`. Finish `make clean` for the configured plaintext even when preflight or deployment fails. Disposable provider/executor/identity retirement follows `vpn-cleanup`; plaintext cleanup alone does not finish that lifecycle.

If Terraform changes are included, use [the Terraform procedure](../../../docs/RUNBOOK-deploy.md#re-deploy-after-a-terraform-change-instance-type-zone-firewall) and review its saved plan before apply. Replacement follows the authorized recreation path. For same-node disposable firewall changes, retain acceptance on both sides and reissue the registered cleanup manifest through its canonical verb before further guest writes or destruction.

If monitoring changes are included, read [current observability operations](../../../docs/OBSERVABILITY-OPERATIONS.md#current-contract-and-task-history) first. Use the selected component's exact-host lifecycle and resource admission; the retired dedicated-host bootstrap and old receipts do not authorize the co-hosted rollout.

## Completion

Report the exact source revision/digest and targets, observed preflight/deploy/verify/parity results, acceptance outcome and cleanup residuals. A diagnostic baseline-failure receipt proves that failure path only. Local CI, guest verification and protocol/client acceptance remain separate claims; unchanged runtime digests do not refresh old live evidence. Documentation-only changes use documentation/CI gates without redeploying runtime merely to advance a source SHA.
