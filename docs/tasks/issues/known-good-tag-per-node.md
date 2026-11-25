---
id: OPS-1795093095746075
title: Cut the known-good tag from per-node verification
kind: bug
status: done
area: operations
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795093095746075-known-good-tag-per-node
created: 2026-11-19
updated: 2026-11-25
related_tasks: []
closed_at: "2026-11-25T15:04:07Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Per-node receipts and the inventory-scoped tag gate pass locally and in main CI at f9d6a5139; the live two-inventory tag vpn-deploy-known-good-2026-11-25-1406 covers the core fleet and the split-hop pair
---

## Goal

The operator can create a `vpn-deploy-known-good-*` tag for a fleet in which every node has its own secrets file and overrides, and the weekly drift issue reports only commits that change what a redeploy applies.

## Acceptance criteria

- A passing `make verify` with any node limit records one receipt per selected `vpn` host for the checked-out revision and deployable digest, only after `source-drift` passes.
- `make tag-known-good` tags HEAD only when every `vpn` host of every inventory in `KNOWN_GOOD_INVENTORIES` has a receipt for that exact revision and digest younger than `KNOWN_GOOD_MAX_AGE_HOURS`; otherwise it names each gap and creates no tag.
- Adding a second rendered inventory, such as a split-hop pair, makes its hosts required.
- `TAG_ON_SUCCESS` no longer exists; `vpnd deploy --tag-on-success` runs `make tag-known-good` after verify.
- `scripts/drift-since-tag.sh` lists only commits since the tag that touch `ansible/`, `scripts/`, `requirements.yml` or `terraform/`.
