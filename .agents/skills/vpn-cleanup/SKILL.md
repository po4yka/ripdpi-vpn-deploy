---
name: vpn-cleanup
description: Finish or resume exact authorized VPN staging cleanup, disposable sentinel/client retirement or monitoring removal. Use after completed, failed or interrupted runs; general Mac/cache cleanup and broad fleet destruction are outside this workflow.
---

# Finish exact VPN cleanup

Cleanup authority is resource- and phase-bound. A run's explicit cleanup authorization carries across interruption within its bounds; retained files alone supply no new authority. Inspect available evidence first and resolve the exact provider/account, workspace, resource IDs, original controller registry, state, manifest and deadline without printing private contents.

## Classify what remains

- **Configured runtime plaintext:** `make clean` removes the selected `SECRETS_FILE` through its canonical contract. Record any failure or retained plaintext; this does not remove provider resources, issued identities or executors.
- **Disposable provider node:** follow [UUID-bound staging cleanup](../../../docs/CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup). Use the registered current manifest and original private state, not another checkout's copied authority.
- **Bound disposable sentinel/executor:** follow [disposable lifecycle](../../../docs/PROTOCOL-LIVENESS.md#disposable-consumer-uplink-executor), preserving binding and generation artifacts for de-onboarding.
- **Never-bound client/executor:** use that same runbook's explicit unbound retirement path. An absent binding is not permission to fabricate one or delete a VM directly. Unknown or partial onboarding state remains a reconciliation blocker.
- **Monitoring component:** [current observability operations](../../../docs/OBSERVABILITY-OPERATIONS.md#command-effects) defines exact-host `make observability-remove`, which retains data/secrets. Historical dedicated-staging resources use only [retained cleanup](../../../docs/OBSERVABILITY-OPERATIONS.md#retained-dedicated-staging-cleanup-only) with its sealed authority, not a new dedicated deployment.

## Destroy and retire in order

1. For disposable staging, review the canonical delete-only plan for the manifest-bound resource set and run `make staging-destroy` with the exact provider/environment, `STAGING_CLEANUP_MANIFEST` and reserved `STAGING_POST_DESTROY_EVIDENCE` path according to the runbook. Changed resources, state, account, plan or expired authority stop a new apply. A legitimate same-node state change uses `make staging-cleanup-reissue` at the documented boundary, retaining prior manifests; reissue cannot extend creation-derived deadlines or bypass pending destruction.
2. Resume interrupted destruction through the same controller registry and journaled evidence path. Once apply started, the controller resumes provider absence observation rather than launching a new apply. A pre-expiry apply may finish verification after expiry through that supported contract; expiry alone does not authorize another delete.
3. Require exact typed provider absence, including chargeable server/root storage and no active owned resources. Authentication/forbidden/ambiguous responses are failures, not absence. Preserve state, reservation and manifests until that verification succeeds. Resource absence does not reverse cumulative billing; retain recovery artifacts until the account billing review required by the runbook.
4. **Bound:** after verified guarded destroy evidence, run `make deonboard-disposable-liveness` with the original manifest/binding, single-sentinel configuration, registry, dedicated encrypted secrets and evidence output. The command retires the encrypted client first, exact assignment/config next, and marker-bound non-default executor last. Resume its existing phase after interruption and retain categorical receipts.
5. **Unbound:** after verified absence and current empty state, run `make retire-unbound-staging-client` with the original intent, registered cleanup manifest, absence/state inputs, dedicated SOPS file and journal/receipt paths. Only after verified ciphertext/client retirement run `make retire-unbound-staging-executor` with the same authority and a fresh executor receipt. Its initial VM-marker check requires the prepared VM running; its own interrupted removal can resume after stop/delete. Preserve one-shot profile names and the default Docker context.

Every lifecycle goal runs separately with its documented environment/private-path inputs. A refused or unreconciled identity retains evidence and becomes an explicit residual; do not broaden deletion, erase a binding, switch controller home or bypass a guard to continue. New production/resource/credential deletion needs exact additional authority when outside the existing run.

## Completion

Report provider absence, client retirement, executor/profile absence, plaintext cleanup and retained recovery evidence separately. Include incomplete phases, deadline/billing residuals and the next supported action. Failed deployment or protocol acceptance stays failed even after successful cleanup.
