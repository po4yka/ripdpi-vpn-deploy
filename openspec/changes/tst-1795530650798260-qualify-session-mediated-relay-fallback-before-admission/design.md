## Context

The MIT-licensed kulikov0/whitelist-bypass project implements headless Pion DataChannel and VP8 relay paths through third-party session services. The P3 tier of [the architecture map](../../../docs/reference/architecture.md) already names manual WebRTC relays as an operator reachability fallback, but the repository ships no automated, tested or documented session-mediated path. This task qualifies that automated path; it does not replace the manual P3 fallback. A service claiming allowlist reachability does not establish end-to-end payload reliability, confidentiality or durable availability.

## Goals / Non-Goals

- Goal: implement reproducible qualification fixtures and an explicit admission report.
- Non-goal: enable a production transport, publish credentials, promise universal filtering evasion or perform external account actions.

## Decisions

Use only a synthetic local signalling/relay fixture for automated checks. Never create or join real sessions, import cookies, solve CAPTCHAs, load service credentials or send traffic through external platforms under this task. Review authentication, peer admission, confidentiality independently of obfuscation, metadata exposure, reconnect, session expiry, UDP loss and bounded buffering.

Use the exact pinned upstream client/server implementation against controlled fixtures, not a substitute implementation of its protocol. If isolation requires material protocol rewriting, record blocked/rejected qualification instead of treating a mock as candidate evidence. Use external runtime fixtures rather than copying upstream networking code into the deployment tool. Reuse existing test isolation and transport acceptance where applicable. Validate negative cases and byte integrity, not only handshakes. Pin exact revisions and review licensing before executing upstream binaries. Treat throughput claims as upstream claims until reproduced.

## Contracts and ownership

Own future `tests/integration/session_relay_qualification/` fixtures and a `docs/research/` qualification report, following documentation indexing conventions. Terraform roots, Ansible runtime roles, configuration profiles, secrets schema and vpnd do not change. Client contract review may produce a later peer task; do not advertise unsupported capabilities in the current bundle.

## Risks / Trade-offs

Third-party availability and service constraints cannot be controlled by this stack. Default-off is insufficient unless credential, cleanup and explicit opt-in boundaries are also proven. Authentication secrets and session links must never enter logs or public artifacts. Obfuscation alone is not an end-to-end security guarantee. Stop on any unresolved security boundary.

## Migration Plan

No production migration. Fixtures are disposable and all resources are bounded and cleaned up on success, cancellation or timeout. Admission requires reviewed protocol/client evidence and tests; a reject decision is a valid research outcome. Any actual integration or external measurement needs its own scoped approval and specification. Validate planning using taskctl, OpenSpec strict mode and docs-check; implementation adds focused fixture tests and selected CI.
