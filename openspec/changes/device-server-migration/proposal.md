# Change: Migrate devices during server replacement

Task ID: `OPS-1792673523985723`

## Why

Blue-green replacement provisions a new node but leaves device selection,
credential transfer and subscription publication disconnected. Publication does
not prove that a device received the new profile or exercised the replacement.

## What Changes

- Add a reviewed, resumable device migration controller behind Make: discover
  affected active devices, prepare their target credentials, publish exact
  replacement profiles through existing subscription URLs, import explicit
  client receipts, and gate retirement on complete per-device evidence.
- Preserve the source node and credentials during overlap. Reconcile interrupted
  publication by comparing exact remote documents rather than blindly replaying.
- Add authenticated inventory-bound publication inspection and compare-and-swap
  replacement to the existing subscription runtime, retaining revocation/expiry.
- Add a paired RIPDPI client contract for received and candidate-path-tested
  receipts. Export is a user action; no required service or background telemetry.
- Integrate migration into blue-green so an empty or partially verified device
  set cannot silently count as a completed handover.
- BREAKING: blue-green replacement requires separate target secrets and an
  explicit migration plan; it no longer deploys the source's AWG binding as if
  that binding belonged to the target.

## Capabilities

### New Capabilities

- `operations/device-server-migration`: exact device handover, resumable private
  state, stable subscription publication and evidence-gated retirement.

### Modified Capabilities

- None. Existing transport and delivery authorities remain their owning source.

## Impact

- Operator scripts, Make and blue-green; encrypted device registry and secrets
  schema; subscription-host runtime and tests; bundle/receipt wire contracts.
- Paired client work: `po4yka/RIPDPI#TRN-1792673614153980`.
- No new production dependency, provider mutation, deployment, private input
  migration or physical-device acceptance is included in this source change.
