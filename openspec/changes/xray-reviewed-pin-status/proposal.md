# Change: Separate reviewed Xray pins from release status

Task ID: `XRY-1792776853872491`

## Why

The pin check reads the upstream Latest heading as the local reviewed pin. A newer security release therefore makes accurate release tracking appear to require an immediate pin change before staging.

## What Changes

- Use an explicit repository-pin marker for local pin parity.
- Record the current security release separately, with its compiler fix and retained rollout gates.
- Reject missing or duplicate repository-pin declarations.

## Capabilities

### New Capabilities

- `xray-reviewed-pin-status`: distinguish reviewed source pins from upstream availability.

### Modified Capabilities

- None.

## Impact

The local pin check, its tests, and the release-line reference. No private pins, credentials, provider state, or runtime deployments change.
