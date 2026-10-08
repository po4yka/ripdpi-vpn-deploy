## Context

The thirteen predecessor tasks reached different source and hosted-check
boundaries, but their remaining Critical and High acceptance depended on real
provider, SSH, fleet, client, alert-delivery, and offsite-storage capabilities.
Their terminal cancellation records correctly state that unperformed evidence
did not pass, yet the current objective requires those gaps to remain active and
be completed when their external capabilities are available.

On 2026-09-28 the owner excluded Android installation/device testing, alert
drills, and offsite copy/restore from this acceptance. Historical obligations
remain identifiable, but these exclusions are not successful observations and
do not authorize removing configured alert paths or retained backups.

Current protected main is the only source candidate. External execution must
not use the conflicted shared checkout, stale inventories, cached evidence, or
prior PASS records. Provider state is local, deployment secrets are SOPS-owned,
provider credentials are environment-only, and private evidence must stay
outside Git with same-owner mode 0600.

## Goals / Non-Goals

- Goal: Preserve one active, auditable successor for every unfinished Critical
  and High external acceptance obligation within the owner-approved scope.
- Goal: Execute the shortest safe path from exact protected source through
  capability preflight, guarded staging, serial live convergence, authenticated
  client traffic, recovery, and provider-confirmed cleanup.
- Goal: Stop at the exact missing external capability without weakening a gate
  or converting missing evidence into a pass.
- Non-goal: Reuse or rewrite the terminal predecessor task IDs or their Git
  history.
- Non-goal: Reimplement behavior that is already present on protected main
  unless an observed acceptance failure identifies a source defect.
- Non-goal: Create a permanent staging fleet, expand production topology, enable
  a public administration surface, or spend beyond an explicit current owner
  authorization.
- Non-goal: Require Android, alert drills, or offsite restore in this scoped run,
  or credit their exclusion as proof that those capabilities work.

## Decisions

- Use one Critical successor epic rather than resurrecting thirteen terminal
  IDs. Terminal IDs and dropped execution IDs remain immutable; the successor
  spec maps every prior obligation to current evidence before closure.
- Freeze a single clean protected-main revision before external work. Re-run
  source checks only when the candidate changes or an observed external failure
  requires a fix; repeated local gates on an unchanged tested tree add no live
  evidence.
- Run a capability preflight before any mutation. It checks credential presence
  without reading values, provider account identity, selected environment and
  state, cost and expiry authorization, unique staging identifiers, cleanup
  reservation, SOPS decryption, inventory, strict SSH contexts, current client
  profiles, pinned runtimes, and the authorized client executor.
- Keep missing capabilities as typed blockers in the task and verification
  frontmatter. An unavailable provider credential, target, client runtime,
  executor, or human action required by the scoped run
  blocks only its owning phase and never becomes `not_applicable`.
- Use the repository Makefile and typed controllers as the operator surface.
  Raw Terraform, ad hoc Ansible, browser-cookie extraction, plaintext provider
  credentials, and direct state manipulation are prohibited.
- Create at most one isolated staging node per invocation. Bind it to a private
  cleanup manifest before apply, enforce the approved cost ceiling and expiry,
  use unique client and transport identities, and destroy it even when a later
  phase fails. Provider-confirmed absence is part of the same invocation.
- Promote only after the staging SSH migration and recovery rehearsal proves the
  effective listener, pinned algorithms, firewall contract, emergency access,
  and required VPN paths. Live rollout remains serial and stops on the first
  failed or unreachable target.
- Treat four-transport client acceptance and recurring AmneziaWG acceptance as
  separate evidence. Four-transport proof covers current client reachability;
  recurring proof additionally requires a fresh nonce, revision, recovery, and
  teardown result and may retain but never republish an older PASS.
- Require post-firewall authenticated profiles and guarded client/executor
  retirement. The scope decision does not remove existing alert paths or
  retained backups and does not authorize an alert or restore drill.

## Contracts and ownership

- **Portfolio and OpenSpec:** `docs/tasks/issues/complete-critical-high-external-acceptance.md`
  and this change own requirement mapping, phase status, blockers, and closure.
  Only `./taskctl` performs lifecycle transitions, board generation,
  validation, archival, and closure.
- **Protected source:** GitHub protected `main` and its required checks own the
  source candidate. The dedicated worktree must be clean and equal to the named
  main commit before any external phase.
- **Terraform:** `terraform/providers/*`, `scripts/terraform-env.sh`, and the
  provider-specific cleanup guard own resource planning, apply, state, identity,
  and absence verification. Provider credentials enter through environment
  variables only.
- **Ansible:** `scripts/deploy-controller.py`, rendered inventory, strict SSH
  contexts, and the canonical playbooks own dry-run, deployment, verification,
  security verification, source drift, and SSH recovery
  runtime state. Exact target limits and serial ordering are mandatory.
- **Secrets and evidence:** SOPS+age owns deployment secrets at rest. Private
  manifests, reports, journals, and client handoffs live in a
  same-owner mode-0600 directory outside the repository and contain redacted
  target data.
- **Client and AWG:** Current profiles and pinned client runtimes belong to the
  authorized executor. This repository validates their invocation-bound
  handoff, drives the disposable target, and records actual authenticated
  traffic and cleanup; it does not fabricate a client result.
- **Execution ownership:** This task uses one provider/network writer at a time.
  No parallel task may create, mutate, promote, or destroy the same provider,
  state, inventory, SSH path, executor, or staging identity.

## Risks / Trade-offs

- External execution can lock out SSH or interrupt VPN service. Mitigation:
  isolated rehearsal, verified recovery path, strict listener and firewall
  contracts, serial live limits, and stop-on-first-failure behavior.
- Disposable resources incur cost and may outlive a failed controller.
  Mitigation: explicit cost and expiry authorization, pre-apply cleanup
  reservation, manifest-bound destruction, recovery-safe cleanup, and
  provider-confirmed absence.
- Stale secrets, inventories, artifacts, or evidence can appear valid.
  Mitigation: exact source and digest binding, current account and target reads,
  fresh nonces, content identities, mode checks, and refusal of cached evidence
  as a new observation.
- A source defect may appear only in staging or live operation. Mitigation: stop
  the external sequence, clean up the owned resource, reproduce the root cause,
  fix and integrate through protected main, then restart with a new invocation.
- Consolidation can hide a predecessor requirement. Mitigation: verification
  contains an explicit predecessor matrix and archive readiness fails while any
  row lacks scope-matching proof.

## Migration Plan

1. Commit and merge this successor planning record through protected main so
   the external obligations are active before execution evidence is gathered.
2. Select the newest clean protected-main commit with all required hosted checks
   successful; record its commit and deployable digest.
3. Run the read-only capability preflight. Populate each evidence category with
   `required`, `blocked`, or observed `passed`; record exact blockers without
   secret values. Do not perform provider or network writes when a mandatory
   preflight capability is absent.
4. When all staging capabilities are present, reserve private evidence and
   cleanup paths, create one isolated node, rehearse SSH recovery and required
   runtime behavior, collect evidence, and destroy the exact owned resources.
5. Run canonical fleet dry-run and then serial live convergence. After each
   target, run verification, security verification, and source drift; stop and
   roll back on the first failure.
6. With current profiles, pinned runtimes, and an authorized executor, execute
   four-transport traffic acceptance and a distinct recurring AmneziaWG
   invocation with failure, recovery, and teardown evidence.
7. Repeat authenticated traffic after firewall promotion and retire only the
   invocation-owned client, executor, and temporary access capabilities.
8. Reconcile every predecessor row, exact source, rollback, and cleanup result.
   Only then transition to review, run strict validation and archive readiness,
   and follow the two-commit taskctl close lifecycle.

Rollback is phase-specific: abort before mutation on preflight failure; destroy
only manifest-bound staging resources after staging failure; use reviewed SSH,
configuration and credential rollback controllers for live failures;
retain the last valid recurring PASS as historical evidence and leave retained
offsite copies intact. There is no compatibility migration for
terminal task IDs: they remain terminal and the new successor ID is canonical.
