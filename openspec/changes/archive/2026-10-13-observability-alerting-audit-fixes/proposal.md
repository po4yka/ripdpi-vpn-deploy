# Change: Repair alert delivery and monitoring evidence boundaries

Task ID: `MON-1791825755591250`

## Why

The source audit defects allow valid alert payloads to be rejected, frozen evidence to remain healthy, normal watchdog output to be rejected, required coverage to be misclassified, and interrupted observer backups to disable monitoring. Correctness must be established at real producer/consumer boundaries before any rollout.

## What Changes

- Accept bounded actual Prometheus alert URLs and Telegram Message responses without rendering private URLs.
- Consume canonical private watchdog state and replace malformed backup/restore evidence with categorical failure metrics.
- Expire producer evidence centrally even when exporters keep scraping retained textfiles.
- Derive expected-target and required-service presence from actual reviewed producer contracts.
- Restore the observer's prior running state after backup errors, termination and deadline expiry while preserving disable/rotation ordering.
- Reserve delivery-canary attempt sequences before upstream work and record freshness only after confirmed edits.
- Submit operator drills with the current relay contract and confirm their API delivery before resolution.
- Align collector acceptance of reordered sender queue batches with its bounded retained history; keep exact historical delivery assertions.
- Add executable boundary regressions and complete the local and hosted source gates.
- BREAKING: metric and expected-evidence contracts change with every in-repository consumer updated; no compatibility routes are retained.

## Capabilities

### New Capabilities

- `operations/observability-alerting-reliability`: bounded alert delivery, truthful source freshness and coverage, and interruption-safe observer backups.

### Modified Capabilities

- None; this repair contract complements the active resource-bounded observability rollout requirements.

## Impact

- Ansible observability agent, collector and independent observer roles, metric contracts, snapshots and focused tests; the native CI role gate includes observer interruption recovery.
- No new dependency, public listener, credential issuance, Terraform change or protocol configuration.
- Source-only PR. No deployment, real host access, real Telegram messages or live acceptance. The resource-bounded rollout hold remains in place.
