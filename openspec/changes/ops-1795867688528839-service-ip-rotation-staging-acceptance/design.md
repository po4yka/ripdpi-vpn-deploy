## Context

The source change `ops-1795856574795376-service-ip-rotation` is merged; its protected-main evidence is at `0938faa0968b0bb1d0433f4f8301b0b796b8f42d`. Its verification maps dry-run, staging and client evidence to this task.

## Goals / Non-Goals

- Goal: one complete rotation cycle on a disposable staging node with one refreshed device.
- Non-goal: production rotation, a new ASN or prefix, or repeated runs on every provider.

## Decisions

- One provider is enough for the first run; the runbook and the guest `/32` path are provider-neutral. Record which provider was used; other providers keep their mock-provider evidence until a run covers them.
- Use a disposable staging node and the cleanup workflow, so no production node or address changes.

## Contracts and ownership

- Operator-run acceptance under explicit authorization. One writer for the evidence records.

## Risks / Trade-offs

- A provider may need more than the guest `/32` (Vultr reboot, Scaleway DHCP) -> the deploy refuses when the address does not reach the guest; record the result and file a fix.
- A new address shares the provider prefix -> this run proves the mechanism, not filtered-path survival.

## Migration Plan

None. Cleanup retires the disposable node and its addresses.
