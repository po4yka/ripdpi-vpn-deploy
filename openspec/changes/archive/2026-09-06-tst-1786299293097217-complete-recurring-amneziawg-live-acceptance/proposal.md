# Change: Complete recurring AmneziaWG live acceptance

Task ID: `TST-1786299293097217`

## Why

The deploy repository can provision and monitor AmneziaWG, while RIPDPI has a
standalone client runtime, but the shared acceptance boundary still lacks a
complete real-client run covering data flow, recovery, and teardown. Listener
health and synthetic handshakes are not sufficient evidence for this path.

## What Changes

- Turn the existing fail-closed real-VPS lane into an observed current-revision
  acceptance gate with exact-source, freshness-bound evidence.
- Require authenticated bidirectional traffic, restart, reload, recovery,
  negative-key, and cleanup outcomes in one coherent run.
- Preserve explicit blocked outcomes when external infrastructure is absent.

## Capabilities

### New Capabilities

- `amneziawg-live-acceptance`: Produce repeatable, redacted, cross-repository
  evidence for the current supported AmneziaWG revision.

### Modified Capabilities

- `protocol-liveness`: Treat real data-plane and recovery evidence as distinct
  from process and listener health.

## Impact

- Affects the existing AWG real-VPS executor, sentinel, evidence contracts,
  tests, operator scheduling, and RIPDPI evidence consumption.
- Does not authorize production protocol revision changes or expose live data.
