---
id: CIC-1793457997498773
title: Merge every pull request by rebase and keep lifecycle commits in one pull request
kind: feature
status: doing
area: ci
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1793457997498773-merge-every-pull-request-by-rebase-and-keep-lifecycle-commits-in-one-pull-request
created: 2026-10-31
updated: 2026-10-31
related_tasks: [CIC-1792911952227614]
---

## Goal

`main` accepts rebase merges only, so every pull-request commit lands unchanged as its own first-parent commit; CI validates each commit subject and trailer; `taskctl` drops the protected-ref gate from `CIC-1793437852879654`; the lifecycle documentation allows review, terminal and purge commits to share one pull request as separate commits while the purge audit keeps its first-parent proof.

## Acceptance criteria

- `.github/repository-policy.json` allows rebase merges only (no squash, no merge commits, linear history kept) and the contract test pins it; the configuration command is unchanged.
- The `PR title` CI job fails a pull request whose commit range contains a non-conventional subject, a trailing period, Codex metadata or a `Co-authored-by` trailer, naming the commit; valid ranges pass; the job stays read-only.
- `close prepare --outcome done` and `verify --archive-ready` no longer consult any remote ref or accept `--protected-ref`; the `HEAD` committed-review check and the purge audit are unchanged and covered by tests.
- Task README, CONTRIBUTING, branch-protection how-to, testing reference and the lifecycle skills describe rebase-only merges and single-pull-request lifecycles with separate commits; the asset lock is refreshed and `./taskctl validate` passes.
- Focused tests, `make docs-check`, `make check` and exact-head CI pass; the policy is applied to GitHub through the authorized Make command and read back.
