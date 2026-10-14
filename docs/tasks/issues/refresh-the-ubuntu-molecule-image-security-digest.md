---
id: CIC-1791950809934804
title: Refresh the Ubuntu Molecule image security digest
kind: bug
status: doing
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-14
updated: 2026-10-14
spec_reason: dependency-only
related_tasks: []
status_detail: Refresh the immutable Ubuntu test dependency to clear exact-source Trivy findings blocking runtime and observability acceptance.
---

## Goal

Clear the fixable Ubuntu Molecule image findings that block runtime and observability source acceptance, using a freshly published immutable test dependency.

## Acceptance criteria

- The exact rebuilt Ubuntu image passes the existing HIGH/CRITICAL Trivy policy without ignore additions or threshold changes.
- Every active Ubuntu image consumer and its pin regression uses the scanned digest.
- Pin and cloud-init acceptance regressions, relevant hooks and complete hosted checks pass.
- Production images, hosts and credentials remain outside this dependency refresh.
