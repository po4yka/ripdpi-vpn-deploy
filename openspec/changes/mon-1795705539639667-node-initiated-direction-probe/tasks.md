# MON-1795705539639667: Probe node-initiated connections from the liveness sentinel to separate one-way from two-way blocks

## Objective

The sentinel path also tests connections that the node starts toward domestic targets. Block detection (D5) can then tell "unreachable for clients only" from "blocked both ways".

## Ownership

`ansible/roles/` exporter files, alert template annotations (serialized after D5), docs. One writer.

## Verification

Planning: `./taskctl validate`, strict OpenSpec validation and `make docs-check`. Implementation: the narrow tests of the touched area, then `make check`. Staging: a node probe series reaches the collector; the hint shows both direction texts.

## Execution

- [ ] MON-1795705571968001 Add the node-side probe with a bounded target count and a direction-labelled metric, with tests #feature @item:MON-1795705539639667
- [ ] MON-1795705600194316 Add the direction text to the D5 hint output and a promtool case for client-only and two-way blocks #feature @item:MON-1795705539639667
- [ ] MON-1795705620493344 Document the probe and its limits in docs/reference/protocol-liveness.md #feature @item:MON-1795705539639667
