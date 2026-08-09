# Change: Make filtered-vantage protocol liveness a recurring fleet gate

Task ID: `MON-1786299441667649`

## Why

The repository already models authenticated multi-vantage liveness, but current
fleet evidence does not cover every profile from filtered client paths. Local
service health cannot distinguish censorship from server failure.

## What Changes

- Require recurring control-plus-filtered evidence for every supported profile.
- Preserve explicit unknown and stale states and sustained quorum before any
  rotation candidate is issued.
- Observe failure, recovery, and unavailable-vantage behavior without automatic promotion.

## Capabilities

### New Capabilities

- `recurring-filtered-liveness`: Maintain freshness-bound client-path evidence
  for the full logical profile portfolio.

### Modified Capabilities

- `protocol-liveness`: Make recurring multi-vantage evidence the fleet gate
  while preserving explicit operator-controlled promotion.

## Impact

- Affects liveness policy, evaluator, sentinel schedule, redacted state,
  alerting, rotation integration, tests, and deployment-status documentation.
