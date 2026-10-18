# Change: Repair protocol compatibility and audit validation defects

Task ID: `XRY-1792265213021342`

## Why

The P0 exporter sends sing-mux to an Xray server that accepts Mux.Cool. The
research mtg installer treats release archives as binaries and accepts invalid
FakeTLS secrets. Naive error logs can retain CONNECT metadata. REALITY shortId
validation does not enforce wire uniqueness. PQE release notes state an incorrect
stable-release restriction. Existing synthetic checks do not prove engine compatibility.

## What Changes

- Refuse incompatible P0 client output before publication and test real engines.
- Install the pinned mtg archive, preserve legacy same-version receipts, and reject
  invalid FakeTLS input before mutation.
- Exclude CONNECT request metadata from Naive error logs.
- Require valid, wire-unique REALITY shortIds.
- Correct PQE history while preserving the enforced HOLD and classical clients.
- Correct related Naive compatibility notes and qualify Snell using its real runtime.
- Refresh reviewed Naive and Snell pins where native compatibility is established.
- Correct the opt-in Finalmask contract so it cannot silently ignore the setting.
- Remove CR and LF from encoded inventory metadata before publication.

## Capabilities

### New Capabilities

- `transports/protocol-audit-compatibility`: fail-closed protocol admission and real-engine regression evidence.

### Modified Capabilities

- None. The added requirements constrain the existing delivery surfaces.

## Impact

- Ansible Xray, Naive, Snell and probe-matrix-target roles; client generation;
  secret validation; protocol tests and required CI.
- No provider, production, credential rotation or listener expansion.
- Previously accepted invalid inputs and incompatible client output now refuse.
