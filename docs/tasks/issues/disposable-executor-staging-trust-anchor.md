---
id: SCR-1795352512092131
title: Trust an explicit staging TLS anchor in the disposable liveness executor
kind: feature
status: review
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
---

## Goal

A disposable staging node serves the self-signed certificate that its generated staging secrets hold. The operator Colima executor does not trust it, so the four-profile proof refuses with `onboarding-refused` and staging acceptance stays partial. `make provision-disposable-liveness-runtime` accepts an explicit `STAGING_TRUST_ANCHOR` certificate and installs it into the executor's system trust store, as `scripts/ci-real-deploy.py` does for its disposable runner. TLS verification in the liveness profiles stays enabled.

## Acceptance criteria

- `STAGING_TRUST_ANCHOR` is an optional command-line field of `make provision-disposable-liveness-runtime`; without it the command behaves as before.
- The script refuses a file that is not exactly one PEM certificate, is not self-signed, is expired, or whose subject alternative names are not exactly one non-wildcard DNS name, before it changes the executor.
- An accepted anchor is installed under `/usr/local/share/ca-certificates/` in the executor and `update-ca-certificates` runs; the printed result names the anchor's SHA-256 fingerprint.
- A disposable staging node reaches fresh `ok` on all four liveness profiles with this anchor.
