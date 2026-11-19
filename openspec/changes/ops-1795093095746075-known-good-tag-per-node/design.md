# Design

## Receipts, not one unbounded run

A tag must mean that every node passed `verify` and `source-drift` at one revision. Per-node secrets and overrides make a single run impossible, so `verify` writes a receipt for each host it selected, and `tag-known-good` requires the conjunction. The receipt binds alias, revision and deployable digest; the tag gate recomputes both from the clean checkout and refuses a receipt for another revision, another digest, or older than `KNOWN_GOOD_MAX_AGE_HOURS` (default 24).

## Failure handling

A failed receipt write warns and leaves `verify` green: the per-node controllers (device lifecycle, migration, recovery, fleet maintenance, CI) gate on `verify`, and a missing receipt only withholds the tag. The tag is annotated with the verified node list, so a tag cut from a narrow inventory is visible.

## Scope by inventory

The required host set is the `vpn` group of each inventory in `KNOWN_GOOD_INVENTORIES` (default: the canonical generated inventory). A split-hop pair keeps its own rendered inventory, so the operator includes it by adding that path. No per-host include or exclude list exists: an inventory is the unit the deploy controller already freezes.

## Rejected alternatives

- Keep `TAG_ON_SUCCESS` on `verify` and loop it per node: a per-node verify cannot know whether other nodes passed.
- Compare the drift check against live node manifests: the scheduled workflow has no fleet access by design.
