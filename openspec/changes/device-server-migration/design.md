## Context

The registry owns per-device delivery options and private AWG recovery material.
Only eight token-hash characters are recorded there; the installed publisher
owns complete grant hashes and exact documents. Multiple issued URLs can remain
active. A delivery-host move must preserve the origin, not just token filenames.

## Goals / Non-Goals

- Goal: positive migration of the four baseline transports, all active grants
  for affected delivered devices, and both stationary and replaced publishers.
- Goal: distinguish publication, import and exact candidate-path evidence.
- Non-goal: automatic DNS/provider mutation, automatic node destruction,
  mandatory telemetry, new client key generation or hardware attestation.

## Decisions

- A versioned private JSON plan names source/target provider-environment pairs,
  inventory aliases, cohorts and encrypted files; exact publication aliases,
  namespace and stable HTTPS origin; pinned inventory and known-hosts inputs.
  Target secrets exist independently and retain their server keys. Inventory
  admission and transport use the existing strict fleet inspection helpers.
- Make owns `device-migration` actions: plan, prepare, publish, status,
  receipt, attest, ready and rollback. Mutation requires reviewed exact inputs;
  `prepare` retains that approved identity for subsequent resume. Blue-green
  prepares before target deployment, publishes only after verify/smoke, and
  checks readiness before its drain guidance. DNS pivot remains explicit.
- Source encrypted authority retains a bounded migration journal. It contains
  full grant hashes, encrypted old/new document snapshots, exact plan/input
  identities and per-device progress. The existing SOPS writer preserves
  recipients and serializes source edits. A stable per-migration lock covers
  cross-document phases; target publication is recognized by exact before/after
  identities. No plaintext payload is persisted as operational state.
- Transfer only selected per-device Xray/Hysteria credentials, matching optional
  Snell/Naive identities and AWG peer authority. Preserve target server settings
  and unrelated devices. Resolve exact target instances, allocate both address
  families, retain the physical device's AWG public/private identity, and update
  target registry binding. Conflicts or unsupported cohort relations refuse
  before target publication. Source credentials remain valid during overlap.
- Publisher snapshot runs under the existing state lock, validates bounded
  atomic documents, and returns private full-hash/document bytes plus expiry
  and revocation state. Unsupported legacy or mirror authority refuses rather
  than silently omitting a grant. All live grants for an affected device use
  its current authoritative host/cohort selection; retain each grant's format
  and exact expiry. The review lists grant counts and this normalization.
- The runtime supports compare-and-swap replacement, deliberate absent-target
  creation for an approved publisher move, and owned-document rollback/delete.
  All actions recheck revocation, expiry, client identity and authority under
  one lock. Exact already-applied bytes are fsynced and accepted after lost
  acknowledgements; conflicts are preserved. A publisher move also copies
  unrelated live documents unchanged so retirement cannot strand their URLs.
  Source and destination origin/TLS/listener configuration must preserve the
  reviewed URL. Active single-use bootstrap grants require draining before
  publisher retirement; consumed state is never replayed as a fresh grant.
- The canonical renderer prepares new profiles from target credentials and
  recorded alternate sources. Source and target registry delivery metadata are
  committed only after all required publishers contain the exact new bytes.
  Every continuation checks the owned old/new states and source assumptions;
  unknown changes never become implicit success. Rollback CAS-restores old
  documents and recorded registry options while retaining target credentials.
- RIPDPI receives `ripdpi.migration` with schema version 1, migration UUID,
  per-grant delivery UUID, exact target tags, an `awg_previous_tags` mapping and
  a random 256-bit receipt key. The map binds opaque target AWG tags to their
  previous tag in the same subscription; an empty map means no key carryover.
  It permits retaining that physical device's local private key without manual
  export or lookup across unrelated groups. Old names never enter receipts.
  It hashes exact HTTP entity bytes before decoding, then stores receipt
  context only with completed import. The receipt contains no token, key,
  endpoint or device label. HMAC binds the fixed newline-delimited fields
  documented in the shared contract and golden vectors.
- The client probes exact P0/P1/Hysteria/Snell candidates through its existing
  bounded native payload probe. AWG requires the imported configuration to be
  the exact consumed running configuration and rechecks that session through
  the existing payload verifier. A changed generation/network/configuration
  invalidates evidence. This proves candidate payload reachability, not full
  device capture or physical-device acceptance of this source change.
- Existing non-RIPDPI formats retain their parser-compatible bytes. An explicit
  generation-bound per-device operator attestation can satisfy human acceptance;
  it is always labeled separately from an authenticated client export. No
  publication or generic service-health result creates this attestation.

## Contracts and ownership

- Primary owns controller/credential modules, Make and blue-green integration,
  secrets schema, public receipt contracts, operator documentation and task
  lifecycle. `operations_audit` owns the subscription runtime CAS/snapshot API,
  pure credential-transfer module and their dedicated regressions. Shared role/test guidance is serialized
  through the primary. No Terraform/cloud-init behavior changes.
- `transport_audit` owns the separate RIPDPI worktree, including client task
  `po4yka/RIPDPI#TRN-1792673614153980`, parser/storage, exact-path verification,
  explicit export UI, all locales, contract copies and client tests.
- No `vpnd` backend duplicates the controller; its existing fleet/blue-green
  delegation inherits the canonical Make operation.

## Risks / Trade-offs

- SOPS and remote publishers cannot commit atomically: exact encrypted snapshots,
  per-phase fencing and idempotent CAS reconciliation bound uncertain outcomes.
- Receipt possession proves knowledge of that delivery, not an uncompromised
  handset. A received-only receipt never satisfies a path-test gate.
- Bounded journals can refuse an oversized fleet before mutation. Splitting the
  reviewed fleet into coherent migrations is explicit, never automatic omission.
- Independent delivery-origin ownership remains an operator responsibility;
  readiness reports source/CI evidence separately from real DNS/client rollout.

## Migration Plan

Deploy the new publisher runtime and paired client before using the operation.
Prepare separate target secrets and a reviewed plan; transfer credentials,
converge/verify green, publish all grants, then collect explicit per-device
evidence and perform the origin pivot. Keep blue until readiness passes.
Rollback only owned unchanged publication generations. No force overwrite or
automatic source destruction is provided. Old blue-green inputs fail with an
actionable requirement for the new plan and target secrets.

Validation uses real encrypted SOPS transactions, real loopback publisher/HTTP
tests, failure/concurrency/fsync tests, four-transport client verification tests,
shared receipt vectors, schema/template/snapshot and shell checks, full
`make check`, client area gates and protected PR/main CI. No live deployment
or production-secret use is part of development acceptance.
