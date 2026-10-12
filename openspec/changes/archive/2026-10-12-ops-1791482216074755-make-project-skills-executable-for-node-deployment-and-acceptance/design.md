## Context

The existing Make/controller interfaces own live enforcement. Skills are instruction entrypoints, not a new execution engine. disposable_promotion.validate_intent already validates the single UpCloud staging target, complete profile policy, private path shape and absence of an invented deployment epoch.

## Goals / Non-Goals

- Goal: concise, discoverable lifecycle and role skills with supported handoffs and evaluable outcomes.
- Goal: one local command prepares the existing intent and exact-alias mapping from a private predeployment liveness configuration and explicit path inputs.
- Non-goal: provider or SSH operations, credential issuance, automatic policy selection, runtime gate changes, a new acceptance ledger or dedicated observability topology.

## Decisions

- Keep five bounded skills; each links to the existing runbook at the phase that needs it. OpenSpec exploration examples and spec-merge examples become conditional references.
- Preserve taskctl as the task/planning source of truth. Existing authorization survives handoffs; planning-only requests still stop before code changes.
- Add a stdlib preparer using the existing promotion validator. It reads only the explicit private JSON liveness configuration; credential input files remain path references.
- Derive host/environment and exact alias from the validated configuration, fix the supported cohort and allocate output paths under the selected empty private directory. Never infer applied_at, source parity or remote success.
- Make consumes environment inputs through an early isolated target, rejecting command-line assignments and mixed goals before .fleet.mk is parsed. Python reads the literal environment values.
- Publication opens an existing empty mode-0700 directory by descriptor before writes, uses exclusive mode-0600 files and checks its pathname binding before/after each publication. It creates no directory or changes its permissions. This avoids claiming fresh directory identity across a non-atomic mkdir/open sequence. A refused nonempty destination remains unchanged; interrupted publication retains only private partial files in the original bound directory.
- Retain human-readable forward-test cases with held-out criteria. Static tests validate artifact integrity and command/path invariants; independent scenario evaluation checks decisions rather than matching generated wording.

## Contracts and ownership

- Root owns Makefile, scripts/prepare-disposable-promotion-intent.py, its tests/docs, task artifacts, aliases, skill evaluation cases and generated hashes.
- New-skills worker owns only .agents/skills/{vpn-bootstrap,vpn-deploy,vpn-acceptance,vpn-cleanup,ansible-role}/.
- OpenSpec worker owns only explore/sync/apply skill entrypoints and supporting references under those folders.
- Shared root AGENTS.md, scripts/tests notes and generated-assets.lock.json updates are serialized by root. Other work and existing runtime contracts remain intact.

## Risks / Trade-offs

- A mistaken recipe can affect live nodes: tie every transition to current identity, bounded authorization and existing gates; forward-test failures and cleanup paths independently.
- Private configuration may contain target information: descriptor-bound mode/owner checks and categorical output; no secret decryption or credential file reads.
- Partial local publication: refuse reuse of the directory and report an incomplete result, retaining private artifacts for exact-path inspection instead of broad deletion.
- Skill files are generated assets for tasking: refresh maintained hashes and retain canonical aliases and relevant contract tests.

## Migration Plan

Additive local command and discoverable skills; existing deployment interfaces remain unchanged. Update the disposable onboarding runbook to use the helper. Validate local scenarios, unit and tasking contracts, the required local gate and exact-head hosted checks before merge. Reverting this source change removes the helper/skills without a live rollback because this task performs no live operations.
