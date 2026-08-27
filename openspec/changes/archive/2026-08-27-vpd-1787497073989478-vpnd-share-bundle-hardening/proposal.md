# Change: Harden share bundle token handling and file permissions

Task ID: `VPD-1787497073989478`

## Why

The vpnd deep audit found four defects in `vpnd share`: an empty subscription token passes validation and is baked into served URLs; a missing subscription host silently produces `(unset)` URLs in a fully rendered page; a crashed run leaves a stale temp file that blocks every future share for that client with os error 17; and QR SVGs carrying the bearer token are written world-readable while the rest of the bundle goes through the 0600 path.

## What Changes

- Token validation rejects empty tokens before URL construction.
- Share fails with an actionable error when no subscription host is configured instead of emitting dead links.
- Bundle writes become crash-safe: stale temps are replaced, temps carry 0600 from creation, and failed writes leave no blocking residue.
- QR artifacts join the same 0600 atomic-write path as the rest of the bundle.

## Capabilities

### New Capabilities

- `vpnd/share-bundle`: Correctness and permission contract for generated recipient bundles.

### Modified Capabilities

- None

## Impact

- `vpnd/src/commands/share.rs`, `vpnd/src/pages/qr.rs` and their tests.
- Operator-visible behavior changes from silent garbage output to explicit errors.
