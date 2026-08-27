---
id: SCR-1786299499104067
title: Emit a versioned AmneziaWG protocol-revision contract
kind: feature
status: blocked
area: scripts
priority: high
risk: high
owner: AWG contract
parent: null
blocked_by: [TST-1786299293097217]
spec_mode: required
openspec_change: scr-1786299499104067-version-amneziawg-protocol-revision-contract
created: 2026-08-09
updated: 2026-08-27
related_tasks: ["po4yka/RIPDPI#TRN-1786299802611226"]
status_detail: Blocked on TST-1786299293097217 current-client live acceptance; no wire-revision compatibility claim is emitted from substitute evidence.
---

## Goal

Extend the canonical RIPDPI bundle with an explicit AmneziaWG wire-revision
contract so the server can stage a new revision without silently feeding it to
an incompatible client.

## Ownership

- Primary surfaces: canonical bundle schema, emitters, public version metadata,
  cross-repository goldens, validators, source watcher, and staging documentation.
- Serialized lanes: the canonical bundle schema and shared golden fixtures have
  one writer at a time.

## Acceptance criteria

- Every emitted AWG entry names a supported wire revision and implementation
  provenance without exposing configuration secrets.
- Unknown or mismatched revisions fail closed before a profile can be activated.
- The current revision remains behaviorally unchanged while a later revision is
  available only through an explicit staging cohort.
- Revision-specific fingerprints and fixtures prevent parameters from being
  interpreted under the wrong wire contract.
- Deploy and RIPDPI CI validate byte-identical schema and cross-stack goldens.

## Verification

- `make task-check`
- Bundle schema/emitter negative fixtures and cross-repository contract checks
- Staging render and artifact validation; no live promotion in this task
