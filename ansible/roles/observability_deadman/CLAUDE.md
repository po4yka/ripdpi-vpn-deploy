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
