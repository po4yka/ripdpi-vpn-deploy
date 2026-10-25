# Change: Deliver AWG range and signature profiles

Task ID: `ANS-1792776076428131`

## Why

The client and server contract cannot carry the header ranges and signature packets used by the reviewed AWG 3.1 source. An exported configuration can therefore lose the wire parameters that the server requires.

## What Changes

- BREAKING: require the named `awg-3.1-ranges-v1` wire profile, canonical string headers, and tagged signature programs in AWG delivery.
- Validate and render non-overlapping header ranges and bounded I1-I5 programs through the same server, export, and client contract.
- Admit range and signature server settings only with the exact reviewed source pair. Retain S3/S4 zero and separate release eligibility.
- Prove real traffic against the source-pinned peer. Keep physical arm64 and filtered-path observations open when unavailable.

## Capabilities

### New Capabilities

- `awg-range-signature-profile`: strict profile admission and lossless delivery for supported AWG 3.1 wire fields.

### Modified Capabilities

- None.

## Impact

Ansible runtime admission and templates, secrets schema and generators, client exports, bundle schema, cohort fingerprint, native qualification, and the paired Android consumer. No provider change, credential use, private pin update, or production rollout is included.
