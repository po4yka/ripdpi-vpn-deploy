# OPS-1795704918170150: Check a new node address from a filtered-side vantage before bundle admission

## Objective

A new node address is checked for TCP and TLS reachability from a filtered-side vantage before any bundle publishes it. A node whose /24 block is already unreachable is refused and recreated with a new address. No liveness decision relies on ICMP alone.

## Ownership

`scripts/` (emit path and the check script), `docs/how-to/deploy.md`, `docs/explanation/threat-model.md`. One writer.

## Verification

Planning: `./taskctl validate`, strict OpenSpec validation and `make docs-check`. Implementation: the narrow tests of the touched area, then `make check`. Staging: one new node on a staging provider is checked from the liveness executor before and after publication.

## Execution

- [x] OPS-1795705312358436 Fix the vantage, control points and refusal rule in the design, then add the check script with tests for pass, unreachable block and missing result #feature @item:OPS-1795704918170150
- [x] OPS-1795705349825337 Wire the gate into the bundle emit path and add a test that a refused node never appears in a bundle #feature @item:OPS-1795704918170150
- [x] OPS-1795705412632581 Document the gate and the ICMP rule in docs/how-to/deploy.md #feature @item:OPS-1795704918170150
