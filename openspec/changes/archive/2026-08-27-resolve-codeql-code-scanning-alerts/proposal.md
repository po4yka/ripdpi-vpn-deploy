# Change: Resolve all open CodeQL code scanning alerts

Task ID: `SEC-1786336086885514`

## Why

The default branch has eight open CodeQL findings at source SHA
`cfb52893594d4f7c9c9f423787f872f4935206ad`. One is a high-severity
world-readable metrics-file finding; two silently ignore exceptions; the other
five identify redundant imports or an overwritten assignment. The findings
must be fixed in source without suppressing CodeQL and without making the local
Prometheus textfile unreadable to node_exporter.

## What Changes

- Restrict the Xray diagnostic textfile to owner and shared-group reads while
  explicitly granting the node_exporter account membership in that group.
- Preserve failure-metric publication and emit a redacted diagnostic if that
  fallback write also fails.
- Make the expected, bounded socket-readiness retry explicit rather than using
  an unexplained empty exception handler.
- Remove the four unused or mixed imports and the overwritten taskctl
  execution-path assignment reported by CodeQL.
- Add focused regression coverage for permissions, reader access, and error
  handling, then require hosted CodeQL evidence on the exact implementation
  SHA before closure.

## Capabilities

### New Capabilities

- `secure-code-scanning-baseline`: Repository Python and Ansible-owned runtime
  code remain free of the eight identified CodeQL findings while the local
  metrics path retains least-privilege reader access and observable failures.

### Modified Capabilities

- None.

## Impact

- Ansible monitoring runtime ownership and service-group configuration.
- Xray StatsService textfile output and its focused unit/Molecule checks.
- Protocol-liveness and operator-monitor Python scripts.
- Repository taskctl tooling and its tests.
- Hosted CodeQL remains the authoritative alert-closure evidence; no workflow
  permissions, query packs, or suppression policy change.
