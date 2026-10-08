---
name: vpn-bootstrap
description: Provision or recreate a VPN node and establish its first recovery, Tailnet and SSH ownership state before deployment. Use for fresh nodes or missing enrollment prerequisites; existing managed-node updates use vpn-deploy.
---

# Bootstrap a VPN node

Produce an exact-node handoff ready for ordinary deployment. Bootstrap establishes management access; protocol acceptance follows deployment.

## Establish the run

1. Use root `AGENTS.md` workspace discovery, then read [fresh-node setup](../../../docs/QUICKSTART.md) and [deployment prerequisites](../../../docs/RUNBOOK-deploy.md#re-deploy-after-a-config-or-secrets-edit). For disposable staging, use [the staging recipe](../../../docs/RUNBOOK-deploy.md#staging-first) and its provider inputs instead of adapting a production example.
2. Resolve the authorized provider/account, workspace, exact inventory alias, profile, source revision, cost/resource limits and cleanup deadline. Revalidate them before action; preserve authorization across handoffs within those bounds. Inspect available inputs without exposing credential values. Use existing separate device identities or the authorized issuance workflow; each device needs its own UUID, shortId and AWG peer key.
3. For disposable nodes without management access, use recreation within the approved replacement scope. Rescue/console recovery needs the owner's explicit emergency choice. A bootstrap request does not implicitly approve Tailnet ACL changes or new production policy.

## Provision and enroll

1. Follow the selected provider's canonical Make sequence: `init`, `validate`, `plan`, review, then authorized `apply`. Inspect the actual plan; unexpected replacement, drift or excess resources stops mutation.
2. For disposable staging, create `make staging-cleanup-manifest` from the exact private state immediately after apply and **before any guest installer**. Follow [UUID-bound cleanup](../../../docs/CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup), retaining the registered manifest, private state and original controller identity. The all-four-profile disposable recipe supports one UpCloud `ci-staging-*` node; broader bootstrap support does not widen that recipe.
3. Generate inventory, independently verify the current public host-key pin and complete `make wait`. Never accept a changed key merely because the node was recreated. Complete `make install-ssh-recovery` for the exact alias before [one-node Tailnet bootstrap](../../../docs/TAILNET-MANAGEMENT.md#bootstrap-one-node).
4. Run `make bootstrap-tailnet` with the reviewed private configuration and one-node enrollment capability. Remove the enrollment key from the environment afterward. Require observed confirmation and the private handoff, including fresh public and Tailnet SSH/SFTP paths for the same original key. Failed recovery installation or incomplete bootstrap stops deployment.
5. Render inventory through `TAILNET_HANDOFFS` using that handoff, complete `make migrate-ssh-ownership` through the documented private inputs, and prepare the exact-alias SSH-context, promotion and fresh baseline-failure sink mappings. Observed contexts come from the real node; the handoff is not itself a promotion proof. Existing confirmed enrollment is reconciled according to the runbook rather than repeated.

## First disposable data-plane deployment

Read [first onboarding](../../../docs/PROTOCOL-LIVENESS.md#first-onboarding-during-a-disposable-staging-deployment). Prepare the dedicated executor through `make prepare-disposable-liveness`, using its non-default one-shot profile and private manifest.

Use `make prepare-disposable-promotion-intent` with only environment inputs: `PROMOTION_LIVENESS_CONFIG`, `PROMOTION_CLIENT`, `PROMOTION_SOPS_FILE`, `PROMOTION_AGE_KEY_FILE`, `PROMOTION_AWG_KEY_FILE`, `PROMOTION_EXECUTOR_MANIFEST`, `PROMOTION_CLEANUP_MANIFEST`, and `PROMOTION_OUTPUT_DIR`. Select an existing empty mode-0700 output directory and a predeployment JSON liveness configuration without `applied_at`. The helper creates `intent.json` and `deployment-inputs.json`; use the latter as `DEPLOY_PROMOTION_CONFIG_FILE`. It validates local intent shape, leaves credential files unopened and supplies no remote or source-parity proof. The deploy controller creates the actual binding epoch and protocol proof during deployment.

Continue with `vpn-deploy` when its prerequisites are observed and deployment is authorized. If bootstrap fails, preserve the phase and private artifacts and use `vpn-cleanup` for the authorized exact cleanup; unbound clients/executors have a separate retirement path.

## Handoff

Report the exact target and source, observed provisioning/recovery/enrollment/ownership results, private artifact locations without contents, and remaining prerequisites. Do not describe a provisioned or reachable node as a working VPN. Monitoring in scope follows [the current co-hosted contract](../../../docs/OBSERVABILITY-OPERATIONS.md#current-contract-and-task-history), including its admission and rollout limits.

When first disposable data-plane preparation is authorized, include the prepared executor and validated intent mapping in that handoff. Resolve missing client/policy inputs before preparation; management-only bootstrap can finish without claiming data-plane readiness.
