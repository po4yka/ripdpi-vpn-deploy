## Context

The policy currently reduces each DNS answer to one minimum admitted IPv4 literal.
The normalizer sends one authenticated SOCKS CONNECT through a fixed gateway.
The existing relay starts only after the upstream reply and already owns bounded
buffers, half-close draining, idle expiry and request cleanup.

## Goals / Non-Goals

- Goal: complete TCP forwarding through a later admitted address when an earlier
  address fails or stalls, while retaining the existing destination isolation.
- Goal: bounded sockets, attempts, control parsing, time and cancellation cleanup.
- Non-goal: UDP failover/replay, post-connect stream retries, new DNS authority,
  route changes, client/credential updates or live deployment.

## Decisions

- Replace scalar `select_admitted` with one immutable canonical candidate tuple.
  Deduplicate mapped forms, apply the complete existing policy, sort numerically
  within each family, then interleave IPv4 and IPv6. Existing UDP code consumes
  only the first entry, preserving its current family preference and binding.
- Resolve once through the existing bounded resolver pool. The DNS worker still
  rejects more than 64 addresses. Cap TCP attempts at eight after family ordering.
  Recheck policy immediately before sending each numeric CONNECT request.
- Use the existing selector-based wait primitive and nonblocking gateway sockets,
  with at most two in flight. Start the first immediately, stagger another by
  250 milliseconds and refill a failed/expired slot promptly. Do not create
  per-candidate threads or another global executor.
- One monotonic `connect_seconds` deadline covers all gateway connection,
  authentication and CONNECT stages. DNS retains its existing separate bounded
  lookup deadline. Per-attempt caps divide the total connection budget across
  the necessary two-slot waves so two stalls cannot starve later candidates.
  These caps never extend the overall deadline. A literal or at most two
  candidates retain the complete connect budget.
- Read only bounded SOCKS control bytes before success; do not consume or forward
  application bytes during the race. Once one valid success reply is complete,
  close every loser, acknowledge the recipient and enter the existing relay.
  Any subsequent error closes the selected stream with no new attempt.
- Check process stop and recipient closure during bounded wait iterations. A
  recipient that pipelines application data must not cause a ready-read busy
  loop; its bytes remain queued until the winner. Every exceptional path closes
  candidate sockets, while `_handle` retains semaphore and worker ownership.

## Contracts and ownership

- Owned implementation: `scripts/transport_destination_policy.py`,
  `scripts/transport_egress_normalizer.py`.
- Owned validation: new `tests/unit/test_transport_destination_failover.py` and
  necessary scalar-API call-site updates in the existing destination tests.
- Ownership notes: precise TCP scope in `scripts/CLAUDE.md` and `tests/CLAUDE.md`;
  serialize those small additions with other branches during integration.
- Task/spec ownership: this task's issue/change files and generated board.
- No Makefile, role defaults/templates, CLI, secrets/config schema, dependency,
  Terraform root or cloud-init changes. Ansible retains ownership of runtime
  installation through the existing transport-egress role.

## Risks / Trade-offs

- Two simultaneous CONNECTs may reach two permitted remote listeners before one
  wins. Only the winning stream receives application bytes; close losers before
  relay and prove their socket closure with actual fixture peers.
- DNS sets larger than eight are bounded intentionally. Family interleaving
  preserves both-family opportunity before truncation; no hidden unbounded retry.
- Slow viable endpoints may exceed a per-attempt share in large answer sets.
  The cap is needed to make later candidates reachable within the fixed budget;
  small sets retain the full budget and all behavior is covered by the spec.
- Portable tests use real TCP/SOCKS sockets and owned destination listeners but
  an owned gateway fixture, not deployed native gateway proof. Existing native
  isolation lanes remain required CI coverage and live rollout is separate.

## Migration Plan

No persisted state or configuration migration is needed. Replace the internal
scalar policy API and update all callers in one change. Keep UDP semantics and
public categorical errors unchanged. Run the complete destination-boundary and
new failover suites, strict OpenSpec/task checks, then the full credential-free
`make check` under the machine build gate. Require hosted checks on the reviewed
revision before merge. Any later authorized rollout uses the existing guarded
runtime publication and rollback; this task does not mutate a running node.
