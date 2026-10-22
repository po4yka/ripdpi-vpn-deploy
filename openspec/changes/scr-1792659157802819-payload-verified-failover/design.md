## Context

The existing shell probe trusts curl exit status. Official sing-box urltest uses
HEAD and does not inspect the response body. RIPDPI already has a protected
candidate payload probe and selector reload lifecycle; extending that consumer
avoids inventing unsupported sing-box configuration or an uninstalled sidecar.

## Goals / Non-Goals

- Goal: exact bounded download/upload observations and real recipient failover.
- Goal: explicit alternate listeners with complete default-contract parity.
- Non-goal: deploy, create servers, issue credentials, select real control origins,
  or claim availability on any unmeasured client network.
- Non-goal: change cryptographic fingerprints, protocol versions, or AWG policy.

## Decisions

- Canonical probe bytes are the prefix of concatenated SHA256 blocks over
  ASCII `vpn-deploy-payload-v1:` followed by an unsigned eight-byte big-endian
  counter starting at zero. A small stdlib helper serves bounded GET payloads
  and validates POST payloads before echoing them; it binds loopback by default.
  Operators may place it behind their existing owned HTTPS origin. The probe
  verifies actual content and length, not response headers alone.
- Keep the shell entry point, explicit loopback SOCKS selection and bounded curl
  execution. Ignore ambient curl/proxy settings; never follow redirects or
  fall back from SOCKS to direct. Optional upload probes verify the echoed body.
- Add optional non-secret `client_payload_failover` to the resolved Ansible
  context, default null. Configured hosts must agree. Only RIPDPI bundles emit
  it as `ripdpi.payload_failover`; ordinary sing-box retains its supported
  latency-only selector. No fabricated default control URL is published.
- Policy version 1 binds `selector_tag: select`, exactly two distinct HTTPS
  origins, each with `url`, `expected_bytes` (32768..65536) and lowercase
  `sha256`. Timing fields are `interval_seconds` (30..3600),
  `timeout_seconds` (1..30), `failure_threshold` and `recovery_threshold`
  (2..10), `cooldown_seconds` (30..3600), and `max_backoff_seconds` (60..3600).
  Timeout cannot exceed interval; maximum backoff cannot be below interval.
  Suggested values are 60/10/2/2/120/900 respectively.
- The client verifies either control through the actual candidate path, bounds
  consecutive failures/recovery and retry backoff, retains cooldown and rejects
  stale network observations. All-path failure retains the encrypted route.
- Set the default alternate REALITY port to zero. Update current provider
  examples, render fixture and disposable CI inputs together. Explicit opt-in
  tests keep exercising a nonzero alternate. Do not silently rewrite an
  operator's retained private provider contract or remove a live listener.

## Contracts and ownership

- Probe worker: shell probe, new canonical content helper/canary, probe tests,
  and payload-throttle operator documentation.
- Client worker: separate RIPDPI worktree, its task/spec lifecycle, parser,
  persisted policy, real probe/controller integration, tests and matching schema.
- Parent: deployment task/spec lifecycle, canonical bundle schema and emitter,
  default listeners and all affected providers, Make interface, shared folder
  notes, integration verification, PR coordination and merge.
- Shared files and lifecycle commands are serialized by the parent. Workers
  must preserve all unrelated changes and request ownership before crossing lanes.

## Risks / Trade-offs

- Useful-data probes consume more traffic: explicit opt-in, two small controls,
  bounded intervals, cooldown and backoff limit it.
- Control origin failures can resemble path failures: either independent
  authenticated exact payload qualifies; mismatch is not proof of censorship.
- Mobile network behavior is not reproduced by portable tests: real local
  sockets and runtime/controller tests prove implementation, not live availability.
- Changed defaults can expose stale private listener declarations: existing
  cross-layer preflight must refuse instead of weakening contract checks.

## Migration Plan

Merge the matching client support before producer promotion. Configure two owned
HTTPS controls with known exact payload hashes to enable the new policy; absent
configuration preserves latency-only operation. Refresh recipient profiles after
an authorized rollout. Keep existing runtime and provider alternate declarations
explicit if an alternate is still required. Source rollback uses a normal revert;
runtime deployment and recipient redistribution are separate operations.

Verification starts with real socket regressions and typed contract tests, then
provider/listener renders and native parsers, `make check`, security review and
protected checks on both PR heads. No credential-bearing test inputs are used.
