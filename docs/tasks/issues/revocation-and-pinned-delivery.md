---
id: SEC-1794728936979277
title: Keep revoked devices revoked and bind secret delivery to pinned hosts
kind: bug
status: review
area: security
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794728936979277-revocation-and-pinned-delivery
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
status_detail: Implemented in 545221f8; remote CI, dry-run, staging and live evidence pending
---

## Goal

A revoked device credential stays unusable across rollback and share bundles. Device payloads go only to hosts with a pinned identity. Removing a secrets recipient ends that recipient's access to later versions. Source: the 2026-11-15 repository audit. `SEC-1794287701595900` owns the first-contact host-key pin that this work uses.

## Acceptance criteria

- The `config` rollback refuses a previous configuration that holds a client identity absent from the accepted configuration.
- A request for a revoked token's share bundle returns the same response as an unknown token, in the normal and the retained-publisher flow, and a revoked token gets no new bundle. Bundles that are not revoked are kept.
- `scripts/issue_sub_token.py` sends nothing when the subscription host key is not pinned, and ignores a permissive user SSH configuration.
- A mirror with a remote source refuses to install without a host-key secret, and the internet-facing service user cannot read the mirror key, the pinned host key or the backup password; the published payload is still owned by the service user.
- `scripts/rotate-secrets.sh` leaves the file with a new data key, or unchanged when the rotation fails.
