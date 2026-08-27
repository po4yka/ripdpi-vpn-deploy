# VPD-1787497252303967: Fix probe-matrix process leaks, timeouts, durability, and evidence semantics

## Objective

Bounded cells and control, durable interruptible sessions, zero-duration rejected, and windows that only ever claim filtering evidence.

## Ownership

- The primary agent owns vpnd/src/commands/probe_matrix.rs, vpnd/src/runner/process.rs, vpnd/tests/probe_matrix_snapshot.rs, docs/PROBE-MATRIX.md, and this change's artifacts.

## Execution

- [x] VPD-1787497252661429 Enable kill_on_drop on the capture path used by cells and add a timeout test asserting child termination #bug !high @item:VPD-1787497252303967
- [x] VPD-1787497252679177 Wrap the control invocation in the cell timeout budget with Unknown-on-expiry handling and test #bug !high @item:VPD-1787497252303967
- [x] VPD-1787497252698055 Add per-tick checkpointing, JSONL crash log, and SIGINT/SIGTERM flush with interrupted marker and nonzero exit; cover with a simulated-interrupt test #bug !high @item:VPD-1787497252303967
- [x] VPD-1787497252715025 Reject duration 0 in config validation and narrow windows() onset to Blocked/Throttled with unit tests for both; refresh the insta snapshot and docs/PROBE-MATRIX.md #bug !high @item:VPD-1787497252303967

## Verification

Use the exact gates and evidence categories in verification.md.
