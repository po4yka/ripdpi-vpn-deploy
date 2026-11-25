# Change: Cut the known-good tag from per-node verification

Task ID: `OPS-1795093095746075`

## Why

The only way to create a `vpn-deploy-known-good-*` tag was `make verify TAG_ON_SUCCESS=1`, which refused any `ANSIBLE_LIMIT`. The fleet no longer fits that shape: each node has its own SOPS document, environment, provider and private `ANSIBLE_EXTRA_VARS_FILE`, and the Makefile requires a limit whenever extra vars are set. `verify` also passes one secrets file to every host. No fleet-wide verify can pass, so the tag has not advanced since 2026-07-26 and the weekly drift check opened issues 59, 73, 294, 408 and 632 for a fleet that was verified node by node. The drift report also counted documentation and task-record commits, which change nothing on a redeploy.

## What Changes

- `make verify` records a private receipt per selected `vpn` host (alias, revision, deployable digest, time) after `source-drift` passes.
- New `make tag-known-good` tags HEAD only when every `vpn` host of every inventory in `KNOWN_GOOD_INVENTORIES` has a fresh receipt for exactly that revision and digest.
- **BREAKING** `TAG_ON_SUCCESS` is removed from the Makefile and every caller; `vpnd deploy --tag-on-success` runs `make tag-known-good` after verify.
- `scripts/drift-since-tag.sh` lists only commits that touch deployable paths.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `deployment-integrity`: adds REQ-AUDIT-KNOWN-GOOD.

## Impact

- `Makefile`, new `scripts/known-good.py`, `scripts/drift-since-tag.sh`, `vpnd deploy`, callers that passed `TAG_ON_SUCCESS=0`, the deploy how-to and testing reference.
- Operators keep receipts under `~/.config/vpn-provision/known-good/` by default; they hold aliases and revisions, no secrets.
- Creating and pushing a tag remains an operator action.
