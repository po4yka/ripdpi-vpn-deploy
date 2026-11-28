# Change: Accept service IPv4 rotation on a disposable staging node with a refreshed client

Task ID: `OPS-1795867688528839`

## Why

`OPS-1795856574795376` shipped movable client IPv4 generations, the client and host address split and the guest `/32` lifecycle with mock-provider, unit, policy and Molecule coverage. The feature is off by default (an empty generation list). Provider attach behaviour, provider-edge delivery to a movable address and a refreshed device on the filtered path cannot be shown offline. The owner closed the source task without that run and moved its dry-run, staging and client evidence here.

## What Changes

- No source change. One operator acceptance run of `docs/how-to/rotate-service-ip.md` on a disposable staging node with a real client device, then cleanup of the node and its addresses.

## Capabilities

### New Capabilities

- `operations/service-ip-rotation-staging-acceptance`: staging and client acceptance of the service IPv4 rotation cycle.

### Modified Capabilities

- None.

## Impact

- Live staging resources and one client device under explicit operator authorization. No repository behaviour changes unless the run finds a defect, which then gets its own fix.
