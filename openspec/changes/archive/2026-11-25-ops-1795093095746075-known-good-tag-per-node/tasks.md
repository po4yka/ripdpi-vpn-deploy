# OPS-1795093095746075: Cut the known-good tag from per-node verification

## Objective

`make tag-known-good` creates the fleet known-good tag from per-node verification receipts, and the drift report counts only deployable commits.

## Ownership

`Makefile`, `scripts/known-good.py`, `scripts/drift-since-tag.sh`, the callers that passed `TAG_ON_SUCCESS`, `vpnd/src/vpnd/commands/deploy.py`, `vpnd/src/vpnd/cli.py`, their tests, `docs/how-to/deploy.md`, `docs/reference/testing.md`, the generated references and this change.

## Execution

- [x] OPS-1795093593849458 Record per-node receipts in make verify and add make tag-known-good with inventory scope #bug !high @item:OPS-1795093095746075
- [x] OPS-1795093606367202 Remove TAG_ON_SUCCESS and route vpnd --tag-on-success through make tag-known-good #bug !high @item:OPS-1795093095746075
- [x] OPS-1795093619046117 Count only deployable commits in the drift report and document the tag workflow #bug !high @item:OPS-1795093095746075

## Verification

- Local: `pytest tests/unit/test_known_good.py tests/unit/test_make_strict_gates.py`, the touched device and vpnd tests, `make docs-check`, `make check`.
- Remote CI: the pull request's `required checks`.
- Live: the fleet rollout and first tag are a separate operator action after merge.
