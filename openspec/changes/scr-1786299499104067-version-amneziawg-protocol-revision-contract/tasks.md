# SCR-1786299499104067: Emit a versioned AmneziaWG protocol-revision contract

## Objective

Make every AWG bundle entry revision-aware, revision-fingerprinted, and safe for
cross-repository staging without changing the current production revision.

## Ownership

Own the canonical schema, emitters, public pins, source watcher, goldens, and
staging documentation. Serialize shared contract artifacts.

## Execution

- [ ] SCR-1786299506619776 Define the canonical AWG revision and provenance schema with revision-bound fingerprints #feature !high @item:SCR-1786299499104067
- [ ] SCR-1786299506639578 Emit current and staging revisions with fail-closed compatibility validation #feature !high @item:SCR-1786299499104067 @blocked_by:SCR-1786299506619776
- [ ] TST-1786299506659645 Add cross-repository goldens and negative fixtures for missing, unknown, and substituted revisions #feature !high @item:SCR-1786299499104067 @blocked_by:SCR-1786299506639578
- [ ] DOC-1786299506682712 Document staged rollout, evidence gates, and rollback without production promotion #feature !high @item:SCR-1786299499104067 @blocked_by:TST-1786299506659645

## Verification

Run task contracts, schema/emitter tests, cross-repository drift checks, and an isolated staging render.
