## Context

The canonical controller already fences inputs, supervises child processes and
recovers protected runtime transactions. Fleet rotation already has an exact-plan
journal. The new surface connects these facilities; it does not replace them.

## Goals / Non-Goals

- Deliver all nine requirements, starting with resume, release inputs and kit recovery.
- Keep operator authority and private values outside Git and remote logs.
- Do not provision servers, add a remote command daemon, bypass preview gates or
  automatically repair drift.

## Decisions

- Use a detached local worker and fixed canonical Make stages. Reject arbitrary
  commands and Make injection. Bind a clean revision, effective inventory, private
  inputs and a finite deadline. Prefer a clean controller without `.fleet.mk`.
- Hold sorted locks for shared nodes, inventory and owned plaintext destinations.
  Journal intent before mutation. Reuse the existing owned-process supervisor.
- Stream logs through an owned, bounded age process; require successful encryption
  separately from command success. Always run canonical cleanup and prove absence.
- Resume accepted boundaries only after source/input checks. An uncertain mutation
  requires canonical state reconciliation. A refused preview never becomes a
  generic success; retained runtime journals follow the documented recovery path.
- Derive archive members from one release identity, then verify downloaded archive
  contents and checksum. Use one version for package installation and APT policy.
- Snapshot only admitted kit roots. Enforce file authority and archive bounds,
  authenticate decrypted manifests, rescan inputs before a current-coverage claim,
  and publish a separate post-delivery acknowledgement.
- Reuse native protocol verification, backup restore drills and passive inspection
  for serial rollout and periodic checks. Notifications are limited to actionable
  state changes through the private monitoring path.
- Address changes require a private exact-scope grant. Terraform owns provider
  firewall state; runtime firewall changes use the existing canonical transaction.
- Routine credential contexts exclude administrative provider keys. Verify narrow
  provider grants before switching consumers; preserve independent recovery.

## Contracts and ownership

Primary owns new maintenance/release/kit scripts, matching tests, Make wiring,
documentation and CI. Existing Ansible role changes stay in their owning roles.
Shared Make and CI edits are serialized. Independent review is read-only.
Terraform state and provisioned resources remain unchanged unless a reviewed
address-only plan is necessary and within current authorization.

## Risks / Trade-offs

- Lost responses can conceal completed writes: retain uncertain intent and
  reconcile through the existing canonical controller.
- Concurrent operator work can change recovery inputs: resource locks and complete
  manifest comparison refuse a false current-coverage claim.
- Secret-bearing diagnostics can outlive a process: encrypt before disk write,
  bound output and retain encryptor/descendant ownership until cleanup completes.
- Periodic jobs can outlive grants: check deadlines before each mutation, never
  merely at startup. Passive checks need no mutation authority.

## Migration Plan

Validate planning, implement and test points 1–3, review and integrate. Continue
serial rollout, scheduled verification, bounded address management and CI against
the resulting contracts. Observe hosted checks on exact merged revisions. Apply
only required runtime changes to existing hosts with canonical previews and
acceptance. Refresh ignored configuration, encrypted recovery and offsite readback.
Retain prior recovery until the new restore proof succeeds.
