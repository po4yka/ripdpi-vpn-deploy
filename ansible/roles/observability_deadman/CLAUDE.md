# role: observability_deadman — independent monitoring-plane loss detector

## Design decisions

The receiver accepts only compact schema-1 HMAC pulses with an advancing
sequence and bounded expiry. It has neither fleet credentials nor primary
Telegram authority. Its secondary token enters only through `LoadCredential`.
The pulse receiver binds at its explicit ingestion port; all local state and
administrative semantics stay private to the role account.
The public pulse listener uses a dedicated SOPS-owned CA and an exact server
SAN. The control plane receives only that CA as a systemd credential and never
falls back to the public trust store, plaintext, proxy, or redirect handling.
Secondary Telegram transport retries only timeouts, transport errors, 429 and
5xx responses. Retry-After and exponential delay are capped by the same
validated five-second request bound; other 4xx responses fail immediately.
The operator dead-man component remains retired under the current observability
contract. Retaining and testing this source never enables its former sender.
The raw listener admits at most four workers before TLS negotiation; one
five-second absolute connection deadline covers handshake, headers and body.
Aggregate input bytes are bounded, and capacity is returned on every rejection.
Durable schema-2 replay state names the configured `source_generation`. Only
an authenticated healthy pulse from that generation can advance its epoch.
An authorized configuration generation change permits sequence one, while the
expiry fence stays monotonic across epochs and configuration rollback.

Recovery health and notification acknowledgement are separate. A private bounded
`.recovery.json` outbox is fsynced before clearing incident health; failed or
ambiguous deliveries remain queued across ticks and process restarts. Matching
attempt nonces fence stale completion, and acknowledgement is durable before
clearing its reservation. Delivery is at least once: an API acknowledgement lost
before its receipt is persisted can produce a duplicate. No human receipt or
retired topology activation is implied.

## What's done well

Immutable configuration generations are validated before their current link is
switched. The service and timer use strict systemd hardening and state is
atomically persisted at mode 0600. Invalid, replayed, expired and future pulses
are rejected without emitting their contents.

## Pitfalls

The receiver's successful secondary API response is not human receipt. Source
tests do not establish independent hosting, firewall reachability, control-plane
pulse publication, or live firing/recovery acceptance. Do not add a primary
bot token, Prometheus query access, fleet SSH, or a provider credential here.
Do not retry semantic Telegram 4xx responses or log response/request bodies.
Restart the receiver inside its successful activation block whenever its
credential, verifier, generation link, or unit changes; deferred restart can
escape rollback or resurrect a later disabled lifecycle.
Unbound schema-1 state fails closed without migration or deletion. Its owner
must explicitly authorize offline retirement of the private state before a
fresh schema-2 state can be created; do not infer a generation or weaken replay
counters. Generation transitions preserve incident and delivery reservations.

- Check mode runs read-only contract and capacity probes before predicting
  publication. It never creates a private credential candidate, activates units,
  or consumes stdout from commands skipped by Ansible check mode. Native candidate
  validation and readiness still run in ordinary convergence before acceptance.

The fixed deadman scope of the shared authority snapshot helper captures
credential bytes, verifier, unit files, generation link and service states before
the first publication. Rollback restores the complete authority and the exact
prior active/enabled states; replay and incident counters are never rewound.
A failed compensation retains its private recovery snapshot and blocks reuse.

Capture the tick timer with the same direct named-unit query as its service.
Service-only enumeration must never turn a previously active timer into a
false absent snapshot or skip stopping a candidate timer during compensation.
