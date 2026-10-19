## Context

The audit covered source tree 5ecc9342. The eight defects are described in
proposal.md. Existing deployment recovery and secret ownership remain mandatory.

## Goals / Non-Goals

- Goal: close all eight observed boundaries with executable failure regressions.
- Goal: retain prod state location, supported clients, accepted generations and private authority.
- Non-goal: deploy, access providers or real hosts, rotate credentials, change DPI profiles or implement new client transports.

## Decisions

- Reserve the literal default environment alias at operator entrypoints. Keep
  prod mapped to Terraform's default workspace and reject invalid names early.
- Stage ciphertext privately, then publish without replacing an existing backup.
  Preserve supported timestamp names; bound collision retries. Restore through
  an owned sibling file, validate the decrypted state and atomically replace only
  after success. Failure cannot truncate accepted state or log plaintext.
- Keep dedicated share ancestry root:www-data 0750 and files 0640. Repair old
  nested modes on normal convergence while retaining nginx group read access.
- Reject RIPDPI hopping before materialization; official sing-box keeps its contract.
- Align restore checks with the effective backup input selection. Exercise the
  actual rendered drill and real restic with missing selected artifacts.
- Retire exact mirror units before enabled-role writes when its sub-toggle is
  false. Preserve masks, accepted generations, replay fences, revocation state
  and private credentials. Do not implicitly migrate back to direct issuance.
- Recovery documentation follows current bootstrap and deployment contracts,
  including explicit private mappings and renewed admission after root restoration.
- Admit DHCPv6 on a validated uplink selected explicitly or from default IPv6,
  then IPv4 facts. Exclude loopback, management overlay and AWG interfaces.
  Default replies use link-local scope; an optional exact IPv6 address list
  supports legacy global server unicast without broad global UDP exposure.

## Contracts and ownership

- Recovery worker: environment/state scripts, state restore helper, incident and
  restore runbooks, matching unit/Bats tests and scripts/CLAUDE.md.
- Delivery worker: subscription-host role, recipient hopping admission and
  dedicated tests. It sends script-note changes to the recovery worker.
- Network worker: firewall role, DHCPv6 tests and minimal native suite registration.
- Integration owner: backup role/drill, shared tests/CLAUDE.md, snapshots,
  task artifacts, security review, integration validation and Git operations.
- Terraform provider contracts and production secret schemas stay unchanged.
- External writes are limited to the authorized source branch, PR and normal merge.

## Risks / Trade-offs

- New admission can expose invalid operator configuration. Refuse with categorical
  diagnostics before mutation and preserve existing prod behavior.
- Narrow file modes can block nginx if group ownership drifts. Test both allowed
  nginx access and denied unrelated UID access.
- Mirror retirement can race active publication. Stop the timer and service before
  other writes, retain persistent authority and test repeated convergence.
- DHCPv6 needs an actual network contract. Validate interface and address inputs;
  cover multicast replies and wrong-interface/source cases in an isolated native lab.
- Portable tests prove source behavior. Systemd, nftables and real UDP acceptance
  remain separate native CI gates, never inferred from rendered text alone.

## Migration Plan

No live migration is performed. After the reviewed source is merged, a future
authorized deploy repairs share modes and disabled mirror units. Existing prod
state and valid encrypted backup names remain usable. Invalid default aliases
must be renamed to a distinct environment. RIPDPI hopping refuses explicitly.

Run focused pytest/Bats checks, review and refresh affected snapshots, then run
make check. Require selected PR CI, real Molecule and native evidence before
normal merge. Record local, remote CI and artifact evidence separately; mark
staging, live and real-client deployment gates not applicable to this source-only task.
