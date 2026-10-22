# OPS-1792679812321846: Unify device issuance refresh and complete revocation

## Objective

Issue, refresh and fully revoke a device across the complete declared fleet,
with usable delivery, bounded native checks and durable interrupted execution.

## Ownership

- Primary owns scripts/device_lifecycle.py, scripts/device_lifecycle_io.py,
  scripts/device_lifecycle_credentials.py, CLI, Make, secrets schema/example,
  task/spec lifecycle, shared guidance and controller/integration tests.
- transport_audit may own only scripts/device_lifecycle_probe.py,
  scripts/device_lifecycle_probe_worker.py and dedicated probe test files after
  explicit assignment. It must not change shared Make/schema/guidance paths.
- operations_audit owns only monotonic revocation changes in runtime-release
  transaction code, transport-egress outer/rollback/prepare/activation, AWG
  consumer/firewall recovery, their dedicated tests and nearest role CLAUDE.md.
  It also owns rotate-credentials.yml while implementing the shared mode.
  Primary owns controller IO, schema, manifest, shared scripts guidance and
  task/spec state. Native probe/discovery files remain transport_audit-owned.
- Operations in separate recovery and destination failover worktrees retain
  their existing ownership; no worker commits or merges independently.

## Execution

- [x] OPS-1792680221456320 Implement exact fleet discovery and per-protocol issue refresh revoke transformations with real encrypted authority tests #feature !high @item:OPS-1792679812321846
- [ ] OPS-1792680222031123 Implement bounded native device credential probes and isolated positive and revoked access tests #feature !high @item:OPS-1792679812321846
- [x] OPS-1792680222634877 Deliver encrypted resumable execution and exact runtime adoption across nodes with lost acknowledgement tests #feature !high @item:OPS-1792679812321846
- [x] OPS-1792680223324164 Deliver all-grant publication revocation and private recipient artifacts through canonical Make with integration tests #feature !high @item:OPS-1792679812321846
- [ ] OPS-1792680223917464 Verify integrated device operations through full local and native gates independent review and protected PR main CI #feature !high @item:OPS-1792679812321846

## Verification

Complete portable/domain/SOPS/publication tests, real isolated native credential
checks, make check, independent review and protected PR/exact-main CI. Live
infrastructure and physical-device acceptance remain outside source scope.
