---
id: OPS-1795093095746075
title: Cut the known-good tag from per-node verification
kind: bug
status: review
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
---

## Goal

The operator can create a `vpn-deploy-known-good-*` tag for a fleet in which every node has its own secrets file and overrides, and the weekly drift issue reports only commits that change what a redeploy applies.

## Acceptance criteria

- A passing `make verify` with any node limit records one receipt per selected `vpn` host for the checked-out revision and deployable digest, only after `source-drift` passes.
- `make tag-known-good` tags HEAD only when every `vpn` host of every inventory in `KNOWN_GOOD_INVENTORIES` has a receipt for that exact revision and digest younger than `KNOWN_GOOD_MAX_AGE_HOURS`; otherwise it names each gap and creates no tag.
- Adding a second rendered inventory, such as a split-hop pair, makes its hosts required.
- `TAG_ON_SUCCESS` no longer exists; `vpnd deploy --tag-on-success` runs `make tag-known-good` after verify.
- `scripts/drift-since-tag.sh` lists only commits since the tag that touch `ansible/`, `scripts/`, `requirements.yml` or `terraform/`.
