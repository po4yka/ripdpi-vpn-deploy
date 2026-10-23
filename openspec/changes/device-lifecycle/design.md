## Context

The existing AWG enrollment helper generates per-device identities, the shared
payload renderer consumes explicit sources, and the device-migration feature
provides atomic publisher snapshots/CAS and pinned per-node verification.
Specialized commands do not establish full-fleet device completion. Discovery
must inspect protocol authorities, including credentials left on a retired
migration source whose registry now names another node.

## Goals / Non-Goals

- Goal: one controlled issue/refresh/revoke operation with exact scope, usable
  delivery, actual runtime checks and durable continuation.
- Non-goal: provider provisioning, automatic device telemetry, global discovery
  outside the declared operator inventory, or automatic credential resurrection.

## Decisions

- A strict private JSON manifest names the operation UUID, action, device,
  complete inventory, known-hosts file, journal authority, per-node encrypted
  documents/cohorts, publishers, selected delivery hosts and private output.
  All managed inventory nodes require a declared authority, including hosts
  without this device. Preview computes affected subsets from actual content.
- Enrollment generates identity once, then prepares enabled protocol rows per
  target. AWG addresses remain per instance while the one device key is retained
  across its own nodes. Native server keys and unrelated devices stay intact.
  Explicit cohort membership and multi-host AWG selection are mandatory.
- A typed `device_operations` journal in one encrypted authority records input
  fingerprints, before/after documents, exact publication intent, generated
  values and phase evidence. A stable operation lock and each existing SOPS
  writer lock serialize local changes. Cross-document intent precedes writes;
  resume recognizes exact before/after states and never re-generates identities.
- Runtime adoption uses canonical exact-node dry-run/deployment or credential
  rotation gates with frozen inventory, SSH keys/pins and private plaintext
  projections. Source, manifest and authority fences are checked again after
  each long phase. A lost runtime acknowledgement is reconciled by fresh
  canonical verification and the operation-specific credential probe.
- Refresh normalizes each active grant to the current selected device profile
  while preserving that grant's format, expiry and URL. Publication reuses the
  device-migration service's snapshot/CAS protocol. A newly issued token is kept
  in encrypted intent until its private recipient artifact is committed.
- Revocation removes all matching Xray/Hysteria/AWG/Snell/Naive identities and
  cohort memberships from every authority, clears active registry binding and
  adds every discovered grant hash to its publisher's revocation authority.
  Every configured publisher and any retained publisher authority must be
  accounted for. An owned credential-free token is served over TLS before
  adoption, its hash joins the revoked authority, and the same running route
  must then deny it. Snapshot flags alone do not prove running policy. Old keys may
  remain only inside encrypted operation history for reconciliation/probing;
  they are never restored automatically to active lists.
- A bounded private native probe runs over the same pinned management channel
  on the exact node. It uses installed canonical Xray/Hysteria/Snell clients,
  actual TLS CONNECT for Naive, and the existing namespace-isolated AWG probe
  lifecycle with the installed admitted AWG toolchain. Fresh issuance requires
  successful authenticated traffic; revocation requires current runtime
  authority without the identity and failed old authenticated access. A direct
  HTTPS control, exact runtime health and resource cleanup must succeed;
  setup/timeout/control ambiguity is unfinished. A disabled empty-user transport
  retains its established role behavior and must have confirmed inactive
  forwarding plus old-access denial. No synthetic probe receipt is acceptance.
- Private outputs use no-clobber publication with exact-byte resume. Public
  output contains device/node aliases, counts and categorical states, never
  tokens, payloads, passwords, private keys or raw subprocess diagnostics.

### Monotonic credential revocation

Revocation passes the exact operation UUID and prepared intent digest to the
canonical role owners. The shared runtime transaction, outer route owner and
AWG consumer persist this mode before publishing credentials. Failure quiesces
the affected runtime and retains pending candidate authority; recovery cannot
start the old credentials, including from an ordinary deploy caller or reboot.
Only the exact prepared candidate may resume forward to a new accepted receipt.
After a consumer commit, a later route failure also retains the new credential
set instead of compensating to its predecessor. Existing boot admission and
publisher locks remain authoritative. No generic skip-rollback bypass is added.

## Contracts and ownership

- Primary owns `scripts/device_lifecycle*.py`, the Make entry point, secrets
  schema/example, operation tests, documentation and task/spec lifecycle.
- A separately assigned worker may own only the native probe renderer/worker
  and their dedicated tests after an explicit ownership message. Shared schema,
  Make, documentation and journal changes remain serialized with primary.
- Ansible remains the runtime state owner; probe resources are ephemeral and
  removed before completion. No Terraform/cloud-init contract changes.
- The migration feature's public modules and publisher protocol are reused
  after integration, with no copied implementation or compatibility shim.

## Risks / Trade-offs

- Fleet-wide revocation cannot be atomic over disconnected nodes. Per-node
  progress stays incomplete until every affected node is observed denied.
- Exact input fencing can require explicit reconciliation after unrelated
  operator edits; this is preferable to overwriting independent authority.
- Native old-access checks require the managed Linux tools. Missing tools or
  unavailable nodes block completion, while prepared revocation remains durable.
- An encrypted journal retains historical credential bytes for bounded resume;
  it is private authority and must never be exported as a report.

## Migration Plan

Install the reviewed source and publisher protocol through ordinary deployment.
Use a complete private manifest, inspect the preview, approve its exact digest
and execute or resume through Make. Existing per-transport commands remain
available with their narrower scope. Enrollment/refresh can reconcile exact
owned publication; full revoke is monotonic and has no automatic rollback.
Run complete domain/SOPS/publisher/CLI suites, isolated native credential cases,
`make check`, independent security review and protected PR/exact-main CI. Source
qualification does not claim a live deployment or physical-device observation.
