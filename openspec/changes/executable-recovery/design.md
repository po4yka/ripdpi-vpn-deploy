## Context

`restore.sh` has only a dry-run recipe. Existing bootstrap and deployment
controllers own live transactions and already reject uncertain or foreign state.
Recovery composes these contracts instead of replacing them.

## Goals / Non-Goals

- Goal: a fully executable UpCloud Path A replacement with safe continuation after
  interruption and existing-device continuity through a surviving publisher.
- Non-goal: automatic root-restic overwrite, rescue/GRUB, replacing other providers,
  destroying the unavailable node, or recovering a destroyed co-located publisher.
- Non-goal: live deployment as part of this source-delivery task.

## Decisions

- One private versioned manifest binds immutable recovery selection and paths.
  Source revision, target environment and account are checked before mutation.
  Selected mutable phase inputs are hashed into the phase's approval challenge.
- A private locked journal records a write-ahead operation intent and accepted
  observations with atomic file replacement and directory synchronization. Resume
  re-observes provider and guest state; journal phase flags never establish truth.
- Provision only a separate replacement workspace. Canonical Terraform init/plan/
  policy/apply remain the executor. The UpCloud API proves current account and
  unique resource identity. A lost apply response cannot authorize another create.
  An orphan requires exact resource import review, then a new canonical plan.
- Host pin acceptance is an explicit authenticated operator checkpoint, bound to
  current provider UUID/address and exact known-hosts bytes. No ssh-keyscan trust.
- Canonical management helpers retain their configured/unchanged reconciliation.
  Pending guest transactions remain owned by their existing recovery mechanism.
- Generate fresh deployment failure sinks for each attempt; never remove a receipt
  to make retry pass. Full dry-run requires a current review before deploy. Current
  source-drift and verify can reconcile a completed deployment with lost response.
- Device migration prepares target credential continuity before convergence and
  publishes only after the target passes. Its ready contract owns final device and
  stable-origin acceptance. No cleanup or node retirement is implicit.
- Capture private diagnostics under the recovery directory and expose categorical
  errors, phase and review digest only. Supervised subprocesses have finite total
  deadlines and are reclaimed on cancellation. Owned plaintext is always removed.

## Contracts and ownership

- New `scripts/recovery_*.py`, `scripts/recovery.py`, `scripts/restore.sh` and new
  dedicated tests belong to the recovery implementation lane.
- The primary integration lane owns Make, runbooks and subtree instruction edits.
- Existing Terraform/cloud-init/Ansible roles remain authoritative and unchanged.
- Device migration is an integration prerequisite with its own final readiness.
- No arbitrary operator command hooks or new production dependency are introduced.

## Risks / Trade-offs

- A provider operation can complete without state publication. Account/resource
  observation plus exact import review avoids duplicate creation or blind adoption.
- Input or resource identity can change during a long phase. Re-admit before every
  child and before final acceptance, keeping unclear outcomes unresolved.
- An interrupted guest transaction may need its existing bounded recovery window;
  recovery reports that concrete pending condition and retains its artifacts.
- A surviving dedicated publisher is an explicit topology requirement. A destroyed
  publisher needs backup authority restoration and is not accepted by this feature.
- Portable fixtures prove orchestration and interruption behavior only; real node,
  provider and client acceptance are reported separately.

## Migration Plan

Real Path A callers supply a private manifest; old dry-run recipes remain useful
for inspection. New Make entrypoint forwards literal inputs. Rollback means stop
before the next mutation and retain the replacement and journal; explicit migration
rollback or exact resource retirement remains separately authorized. Run dedicated
unit/integration failure tests, task validation, full repository gate, independent
review and exact-source PR/main CI before source closure.
