## Context

The existing `client_payload_failover` policy feeds the recipient's selector,
which already owns cooldown, health thresholds and configuration/network fences.
Candidate runtimes own actual encrypted transport and cleanup. The recipient
also has a non-root QUIC DPLPMTUD implementation with separate IPv4 and IPv6
evidence. These remain the owners of selection and packet measurements.

## Goals / Non-Goals

- Goal: make a healthy but slow relay eligible for replacement by a repeatedly
  better measured candidate without sacrificing existing failure recovery.
- Goal: bound measurements before I/O and explain verified, partial, unavailable,
  deferred and stale observations in the existing recipient UI.
- Goal: give a scoped MTU diagnosis from actual packet evidence, including the
  family-specific IP packet lower bound.
- Non-goal: add a second selector, mandatory telemetry/backend, production
  dependency, automatic AWG activation or MTU mutation, provider operation or
  deployment. Plain sing-box URLTest remains the engine's RTT-only mechanism.

## Decisions

### Coordinated policy version 2

Keep the existing top-level bundle version and replace the nested payload
policy version with 2. Version 1 is rejected by producer and recipient. The
optional `quality` object has exactly these integer fields:

| Field | Bounds |
|---|---|
| `max_pass_bytes` | 65538 through 16777216 |
| `max_window_bytes` | 65538 through 268435456 |
| `window_seconds` | 60 through 86400 |
| `minimum_gain_percent` | 5 through 100 |
| `maximum_loaded_latency_increase_ms` | 0 through 2000 |

The window byte cap is at least the pass cap, its duration is at least the
existing interval, and the pass cap is at least twice the sum of the two
`expected_bytes + 1` allowances. Each object is 32768 through 1048576 bytes.
All existing URL, digest, independent-origin and host-agreement checks remain.
Quality absence in version 2 retains health-only behavior. The example uses
two 256 KiB objects, a 2 MiB pass cap and a 16 MiB one-hour window, 20 percent
minimum gain and 50 ms permitted loaded-latency increase.

### Actual transfer and load observation

Reuse the same two static HTTPS objects. A baseline HEAD and a concurrent HEAD
must return status 200 and the expected Content-Length without downloading a
body. The GET uses exact length and digest checks. Goodput is verified body
bytes divided by a positive monotonic body duration; request latency includes
the complete control transaction and is not RTT.

A loaded control is valid only when its complete interval is inside the actual
GET body interval, from the first positive body read through EOF before final
digest comparison. Waiting for headers or the first body byte is not load. Fast completion can produce valid goodput with unavailable
loaded latency. Preserve that as partial evidence rather than deliberately
throttling the body or claiming saturation. Automatic quality promotion needs
complete evidence for both members; ordinary health recovery continues to use
verified reachability. The optional local canary gains HEAD and four bounded
workers so server serialization cannot masquerade as path load. It remains an
operator-owned test helper rather than a required deployed service.

### Budgets and selection

Reserve each GET's `expected_bytes + 1` allowance before opening sockets. Failed
and cancelled attempts do not receive refunds. A serialized durable
application-wide window prevents resets through restart, network or policy
changes. Reuse checked preference commits and the recipient's elapsed clock
with boot identity. Persist at most 4096 reservations and retain their bounds
for the maximum 24-hour policy window. Same-boot restarts retain elapsed age;
a changed boot conservatively restarts retained reservation aging. Unknown boot
identity, corrupt state or failed persistence defers I/O. Wall-clock movement
cannot replenish a window. A pass has at most
the active member and one rotating challenger, with two possible origins per
member. Headers, HEAD attempts, concurrent operations and deadlines retain
separate hard limits. This is an application body allowance, not an estimate
of TLS, tunnel, retransmission or IP wire bytes.

The current selector remains the only decision owner. Consecutive quality wins
reuse `recovery_threshold`; actual changes retain `cooldown_seconds`. A
goodput winner meets the percentage gain and does not exceed the active loaded
latency by the allowed milliseconds. A latency winner has a strict percentage
reduction and non-regressing goodput. Partial observations cannot win.
Network/configuration/manual-selection drift discards the observations but
retains the budget ledger. Cleanup must complete before publishing evidence or
starting another native candidate. Existing encrypted failure recovery remains.
REALITY uses the existing Xray candidate adapter; it is not silently omitted
from the existing relay pool. AWG stays outside that pool.

### Recipient diagnosis

A typed observable store carries only group/member identity, verified byte and
duration values, goodput, baseline and loaded latency, overlap state, bounded
reason categories and budget state. The existing profile presentation consumes
it. URLs, peers, credential material and raw network identifiers are excluded.

MTU diagnosis reuses validated QUIC evidence. A current acknowledged outbound
UDP payload lower bound implies a minimum IP packet size of payload plus 28
bytes for IPv4 or 48 bytes for IPv6. These are lower bounds, not an exact path
maximum, reverse-path measurement or supported VPN tunnel MTU. Configured
interface MTU remains separately labeled. Scope revocation removes current
numeric advice while historical facts remain explicitly historical. Search
losses, failures and HTTP cliffs never invent a PMTU or causal filtering claim.

## Contracts and ownership

- Server primary: task/OpenSpec lifecycle, documentation, shared folder guidance,
  combined validation, independent review and PR/main integration.
- Server implementation agent: policy validator, bundle contract and fixture,
  producer call sites, canonical payload helper, optional canary and their tests.
- Paired client implementation agent in its own worktree: policy/parser, durable
  budget, candidate measurements, existing selector, observable results and
  positive native acceptance. It owns client task/OpenSpec planning.
- Primary in a separate client worktree: MTU diagnosis, profile/diagnostic UI,
  all locale resources and their tests. Integrate this slice into the client
  feature branch before combined gates. Shared wire/schema and fixtures have
  one owner per repository and must remain byte-identical.
- No Terraform, cloud-init, secrets schema or deployed Ansible runtime changes
  are required. No provider or private credential input is read for validation.

## Risks / Trade-offs

- An object may finish too quickly to establish loaded latency. Report partial
  evidence and retain the current member rather than infer unobserved quality.
- Static origins can affect observed quality. Use the same origin for each
  compared member and retain the independent second origin for health checks;
  origin failure alone does not establish a broken transport.
- Native runtime cancellation and uncertain cleanup can leak resources or
  invalidate measurements. Preserve existing lifecycle ownership and test
  cancellation, busy admission and cleanup before accepting results.
- A durable clock may move. Conservative expiry can temporarily defer probes;
  this is preferable to unexpectedly exceeding the configured traffic budget.
- A policy break requires paired client/server integration. Contract tests and
  documentation make the nested version break explicit; no legacy shim is added.

## Migration Plan

Persisted recipient catalogs receive a one-time checked storage migration from
version 1 health-only policy to version 2 health-only policy. Preserve member
identities, ownership, manual choices and unrelated catalog data. This does not
accept version 1 from imports or retain a second runtime policy. A failed write
leaves the original catalog intact and prevents activation of an uncommitted
migration. The migrated catalog must accept a subsequent version 2 refresh.

1. Update the paired recipient and canonical producer contract together in
   reviewable branches. Validate identical fixtures and federation links.
2. Run real socket and native client acceptance, scoped MTU tests, required
   local gates and independent reviews. Merge the recipient before enabling
   version 2 publication from the producer.
3. Merge both PRs under normal protection and observe exact-main CI. No
   deployed profile is changed by source integration.
4. Operators migrate an existing opt-in policy to version 2 before refreshing
   recipients. To disable quality, remove only its optional object; to disable
   payload probing, remove the opt-in policy. Reverting both source revisions
   is a separate coordinated rollback, not a parallel runtime compatibility path.
