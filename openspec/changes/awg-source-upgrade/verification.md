---
task_id: "SCR-1791618073850409"
change: "awg-source-upgrade"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "required"
staging_evidence: "separately authorized bounded 48-hour candidate soak and exact rollback before promotion"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior; physical Android arm64 must establish exact candidate core, three reconnects, DNS and sustained bidirectional transfer; S3/S4 floor remains unchanged"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-VERSION | SCR-1791618078367215 | Source-consumer consistency, real exact-source builds, immutable-ref rejection and receipt output checks; metadata and soak claims require separate observed evidence. | required |
| REQ-PROTO-AWG-VERSION | SCR-1791618079169597 | Source-consumer consistency, real exact-source builds, immutable-ref rejection and receipt output checks; metadata and soak claims require separate observed evidence. | required |
| REQ-PROTO-AWG-VERSION | SCR-1791618081446678 | Source-consumer consistency, real exact-source builds, immutable-ref rejection and receipt output checks; metadata and soak claims require separate observed evidence. | required |
| REQ-PROTO-AWG-WIRE | SCR-1791618078367215 | Exact upstream parser and packet-capture interoperability matrix, fingerprint goldens and existing version-floor tests; compare actual bytes and offsets, not release-note assertions. | required |
| REQ-PROTO-AWG-WIRE | SCR-1791618079169597 | Exact upstream parser and packet-capture interoperability matrix, fingerprint goldens and existing version-floor tests; compare actual bytes and offsets, not release-note assertions. | required |
| REQ-PROTO-AWG-WIRE | SCR-1791618081446678 | Exact upstream parser and packet-capture interoperability matrix, fingerprint goldens and existing version-floor tests; compare actual bytes and offsets, not release-note assertions. | required |
| REQ-PROTO-AWG-ADOPT | SCR-1791618080142425 | Extend native lifecycle to exact real AWG daemons and TUN traffic, inspect running executable identity and service restrictions, and inject candidate build/start/readiness failures. | required |
| REQ-PROTO-AWG-ADOPT | SCR-1791618081446678 | Extend native lifecycle to exact real AWG daemons and TUN traffic, inspect running executable identity and service restrictions, and inject candidate build/start/readiness failures. | required |
| REQ-PROTO-AWG-ARM64 | SCR-1791618081446678 | Named physical test procedure integrated with candidate evidence; no emulator, synthetic data or local server fixture substitutes for hardware proof. | required |
