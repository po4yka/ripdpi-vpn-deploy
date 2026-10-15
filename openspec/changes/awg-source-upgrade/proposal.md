# Change: Build and validate upgraded AmneziaWG sources locally

Task ID: `SCR-1791618073850409`

## Why

The current deployment pins precede the v3 source family. A source bump alone
cannot establish packet compatibility or running-process adoption. The owner
requires this task to be executable without external infrastructure, so the
change delivers a complete local source-candidate lab rather than a fleet rollout.

## What Changes

- Build the exact baseline and upgraded Go/tools pairs with checksum-pinned Go.
- Add `make test-awg-source-candidate`: a disconnected local Linux systemd/TUN
  lab with real encrypted TCP, UDP and DNS, packet captures and reconnects.
- Exercise two owned daemons, pair and unit adoption, failed build/readiness
  compensation, idempotency and preservation of a third unrelated tunnel.
- Keep production source defaults, client contracts and S3/S4 safe floors intact.
  Candidate acceptance is Linux runtime evidence, not physical Android evidence.

## Capabilities

### New Capabilities

- `transports/awg-source-runtime`: reproducible local candidate source upgrade
  and positive encrypted interoperability with the retained deployment pair.

### Modified Capabilities

- None.

## Impact

- `contract/awg-source-candidate.json` owns exact candidate/control sources,
  toolchain digests and explicit non-production eligibility.
- Local Docker build/runner, isolated acceptance tests, Makefile and test docs.
- No provider, inventory, host-management SSH, VPN private inputs, published
  ports or deployment. Public GitHub sources use workstation Git authentication.
- Existing integrated device-binding and source-publisher code is reused.
  Completion does not depend on the broader four-protocol acceptance portfolio.
