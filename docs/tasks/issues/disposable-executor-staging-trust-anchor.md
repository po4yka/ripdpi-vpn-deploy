---
id: SCR-1795352512092131
title: Trust an explicit staging TLS anchor in the disposable liveness executor
kind: feature
status: done
area: scripts
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795352512092131-disposable-executor-staging-trust-anchor
created: 2026-11-22
updated: 2026-11-25
related_tasks: []
closed_at: "2026-11-25T05:21:50Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Anchor install and validation covered by unit tests; ci run 45426312839 on main at d09191ca4 passed; the four-profile proof through the anchor returned passed on the disposable node vpn-ci-staging-acc5 at 60a371e4b
---

## Goal

A disposable staging node serves the self-signed certificate that its generated staging secrets hold. The operator Colima executor does not trust it, so the four-profile proof refuses with `onboarding-refused` and staging acceptance stays partial. `make provision-disposable-liveness-runtime` accepts an explicit `STAGING_TRUST_ANCHOR` certificate and installs it into the executor's system trust store, as `scripts/ci-real-deploy.py` does for its disposable runner. TLS verification in the liveness profiles stays enabled.

## Acceptance criteria

- `STAGING_TRUST_ANCHOR` is an optional command-line field of `make provision-disposable-liveness-runtime`; without it the command behaves as before.
- The script refuses a file that is not exactly one PEM certificate, is not self-signed, is expired, or whose subject alternative names are not exactly one non-wildcard DNS name, before it changes the executor.
- An accepted anchor is installed under `/usr/local/share/ca-certificates/` in the executor and `update-ca-certificates` runs; the printed result names the anchor's SHA-256 fingerprint.
- A disposable staging node reaches fresh `ok` on all four liveness profiles with this anchor.
