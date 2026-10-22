# Change: Deliver payload-verified failover and explicit alternate listeners

Task ID: `SCR-1792659157802819`

## Why

The payload-throttle probe accepts a two-byte HTTP response as a completed
32-KiB transfer. Generated latency-only selectors can therefore prefer a path
which answers small requests but cannot transfer useful data. The default
alternate REALITY port also creates an additional public listener without an
explicit operator choice.

## What Changes

- Verify exact payload size and content through bounded explicit transport probes.
- Deliver a typed payload-aware selection policy to the matching RIPDPI client,
  including independent controls, cooldown and bounded retry backoff.
- Preserve official sing-box parser compatibility and distinguish its latency-only
  selector from the coordinated RIPDPI capability.
- BREAKING: the payload endpoint must implement the documented verified content
  contract; arbitrary successful HTTP bodies no longer pass.
- BREAKING: alternate REALITY listeners default to disabled. Operators retaining
  an alternate must declare both its runtime setting and provider listener.

## Capabilities

### New Capabilities

- `operations/payload-verified-probes`: bounded exact-content transfer observations.
- `clients/payload-aware-failover`: coordinated recipient policy and runtime selection.
- `network/explicit-alternate-listeners`: explicit alternate listener selection.

### Modified Capabilities

- None.

## Impact

- Operator scripts, tests, client payload generator and shared recipient schema.
- Ansible defaults, Terraform examples and disposable CI listener construction.
- Coordinated RIPDPI client parsing, probe execution and selector runtime.
- No provider access, credential issuance or live deployment is authorized by this change.
