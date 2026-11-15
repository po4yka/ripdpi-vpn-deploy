# SCR-1794726174976734: Reach the cloud liveness sentinel over its Tailnet address

## Objective

The promotion scope check reaches a cloud liveness sentinel over its Tailnet address when that route proves the same pinned host key as the sentinel's Terraform-state public address.

## Ownership

Single lane: `scripts/cloud_promotion_scope.py`, `tests/unit/test_cloud_promotion_scope.py`, `docs/how-to/deploy.md`, `scripts/DESIGN-NOTES.md`.

## Execution

- [x] SCR-1794726257687734 Admit a Tailnet sentinel route bound by the alias and public-address pin #feature !high @item:SCR-1794726174976734

## Verification

- Local: `tests/unit/test_cloud_promotion_scope.py`.
- Remote: PR CI on the exact head SHA.
- Dry-run and live: the production `node-b` prepare, dry-run and deploy with sentinel `node-a` on its Tailnet route, as a separate authorized step after merge.
