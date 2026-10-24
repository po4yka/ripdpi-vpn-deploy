# Change: Stop terminal reviews after worker signal delivery

Task ID: `SEC-1792842686096891`

## Why

A worker can receive a process stop signal while the main thread blocks on a
review terminal read. The Python handler then waits for terminal input, leaving
the pipeline and its secrets cleanup pending. A controlled real-launcher
reproduction retained synthetic plaintext until an answer released the read.

## What Changes

- Keep review input responsive to signals regardless of the receiving thread.
- Preserve default refusal, explicit terminal authority and Make-step ownership.
- Complete cleanup and terminal resource release after signals or cancellation.
- Keep the existing command flags and operator prompts. No CLI contract break.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations/deployment-readiness-followups`: responsive, terminal-authorized
  deploy and reconverge reviews with signal priority.
- `vpnd/runtime-safety`: cleanup after review interruption or task cancellation,
  without retained terminal readers or detached cleanup.

## Impact

- Python CLI review, terminal input and pipeline cleanup code and regressions.
- Existing standard-library APIs only; no dependency or runtime pin change.
- Reviewed test-fixture environment repairs support the full local acceptance.
- No Terraform, cloud-init, Ansible runtime, provider or credential mutation.
