---
title: Scope local gitleaks to repository content
type: task
status: doing
area: ci
priority: high
owner: Codex
parent: null
blocks: []
blocked_by: []
created: 2026-07-18
updated: 2026-07-18
---

# Scope local gitleaks to repository content

- [ ] #task Scope local gitleaks to repository content #repo/RIPDPI-VPN-DEPLOY #area/ci #status/doing ⏫

## Goal

Keep `make validate` fail-closed for committed and staged repository material without scanning the ignored operator-only `secrets/local/` directory.

## Ship definition

- [ ] Repository history and tracked changes remain covered by gitleaks.
- [ ] Ignored local operator credentials do not make the repository gate fail.
- [ ] A force-added secret under `secrets/local/` is still detected.
- [ ] Tests lock the intended scan scope.
