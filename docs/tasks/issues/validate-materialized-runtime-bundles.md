---
title: Validate materialized runtime bundles
type: task
status: doing
area: scripts
priority: high
owner: Codex
parent: null
blocks: []
blocked_by: []
created: 2026-07-18
updated: 2026-07-18
---

# Validate materialized runtime bundles

- [ ] #task Validate materialized runtime bundles #repo/RIPDPI-VPN-DEPLOY #area/scripts #status/doing ⏫

## Goal

Add an explicit validation mode for a locally materialized Android bundle containing an AmneziaWG private key while preserving the strict redacted distribution schema as the default contract.

## Ship definition

- [ ] Default validation continues to reject inline private keys.
- [ ] Runtime mode accepts exactly one valid inline AmneziaWG private key per entry and validates the normalized redacted shape.
- [ ] Runtime mode rejects missing, malformed, or ambiguous private-key state without printing secret material.
- [ ] Regression tests cover full and bare runtime bundles and secret-safe diagnostics.
