---
id: TST-1787850553468536
title: Deliver authenticated fleet probes and passive inspection
kind: feature
status: review
area: testing
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: tst-1787850553468536-fleet-observation
created: 2026-08-27
updated: 2026-08-28
related_tasks: []
---

## Goal

Operators can inspect the fleet without invoking repair and can separately run
authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG probes from dedicated
external sentinels. Local service state never substitutes for client traffic.

## Acceptance criteria

- Passive inspection uses pinned SSH identities, bounded reads, explicit host
  selection, and redacted output; it never invokes watchdog, Ansible, restore,
  service restart, package update, or provider mutation.
- Fullstack onboarding uses compatible pinned runtimes, unique client material,
  explicit AWG target selection, and rejects revoked or mismatched keys.
- Direct control and tunneled HTTPS probes cannot inherit curl configuration or
  proxy bypass settings; all four transports have observed external traffic proof.
- Backup freshness, local versus remote source, and actual restore success are
  reported separately. Missing evidence remains unknown, not healthy.
- Restore cleanup never deletes a pre-existing target and preserves previous
  success evidence on failure; no retention changes.
- A canonical configuration-only backup command installs the existing rclone
  dependency and remote configuration during an exclusive disabled-timer window,
  without backup/prune/restore, service actions, or full-site convergence.
  Actual first copy and remote isolated restore remain separate live evidence.
- Existing tests are extended tests-first; runtime parser checks, independent
  review, and a real external probe are required. Fixtures alone do not close work.

## Ownership

- Primary owns implementation in `codex/fleet-observation-implementation`.
  Shared Makefile, scripts, tests, and liveness contract changes are serialized.
  Read-only reviewers do not edit source.
- No Terraform, firewall, SSH migration, credential rotation, recurring AWG
  acceptance, Rust schema migration, or offsite provider selection is included.
- The existing backup restore runner may be exercised separately within its
  isolated runtime directory; no backup prune or restore into live paths.
- The bounded backup configuration delta owns the backup role configuration
  slice, dedicated playbook, Make target, existing backup tests and docs in
  `codex/backup-configure-20260828`. Inventory-worker files remain untouched;
  shared Makefile edits are serialized. This slice has source-only authority.

## Implementation delivery

- Current user-authorized phase is implementation and CI only. Do not run SSH,
  provider actions, installation, live probes, restore, or device operations.
  Live/staging/client acceptance remains open after code delivery.
- Primary owns inspector, Makefile, docs/contracts, task records, integration,
  and later onboarding changes in the implementation worktree.
- Bounded worker ownership was assigned sequentially: restore cleanup, AWG
  runner, then evaluator; curl isolation, profile builder, then installer.
  Both workers released their files before independent cross-review. Primary
  owns the generation engine and integration. Shared test counts, task
  transitions, commits, and CI remain serialized by primary.
