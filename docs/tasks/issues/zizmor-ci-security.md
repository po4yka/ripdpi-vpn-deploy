---
id: CIC-1786295418152915
title: Integrate zizmor and remediate GitHub Actions security findings
kind: feature
status: backlog
area: ci
priority: high
risk: high
owner: CI security
parent: null
blocked_by: []
spec_mode: required
openspec_change: integrate-zizmor-ci-security-gate
created: 2026-08-09
updated: 2026-08-09
related_tasks: []
---

## Goal

Make `zizmor` a pinned, reproducible local and GitHub Actions security gate,
and remediate every finding in the repository-owned GitHub Actions and
Dependabot inputs without weakening existing security or validation gates.

## Ownership

- Primary paths: `.github/workflows/`, `.github/dependabot.yml`, `mise.toml`,
  `Makefile`, and focused validation tests or documentation required by the
  integration.
- Planning paths: this issue and
  `openspec/changes/integrate-zizmor-ci-security-gate/`.
- Read-only parallel lanes: template-injection triage, checkout credential
  persistence triage, Dependabot and low-severity triage, integration design,
  and validation impact analysis.
- Serialized write lanes: shared workflow files, `Makefile`, `mise.toml`, task
  lifecycle files, and generated task board changes have one writer at a time.
- The primary agent owns all implementation edits, staging, commits, and task
  lifecycle transitions; sub-agents do not write or commit.

## Acceptance criteria

- A repository-pinned `zizmor` version is available through the canonical local
  toolchain and a documented Make target.
- CI audits repository-owned workflow, action, Dependabot, and pre-commit inputs
  with strict collection and fails on actionable findings.
- All default-persona findings under `.github/` are fixed or narrowly justified
  with an inline/configuration suppression that documents why the flagged data
  cannot be attacker controlled; blanket rule disabling is forbidden.
- Third-party or vendored test fixtures do not become CI inputs accidentally.
- The integration itself uses least-privilege permissions and immutable action
  references, and it does not expose tokens or enable unnecessary online access.
- Targeted tests, the pinned `zizmor` scan, `make ci-fast`, and `make validate`
  pass, or any environment-only blocker is reported with the exact failing gate.
- Each coherent implementation change is committed separately on `main` with a
  Conventional Commit message; unrelated work remains untouched.
