---
task_id: ANS-1791586652330612
change: ansible-role-audit-improvements
commit_sha: null
local: passed
local_evidence: Uninterrupted make check passed on the canonical role corrections; 5793 Python tests, 22 subtests, 56 Bats tests, 205 Rust tests and 152 snapshots. Actual hardened nonroot Naive and shared-nginx reconvergence plus receipt/unsafe-authority boundaries passed; independent reviews approve.
remote_ci: required
remote_ci_evidence: Pending exact-source hosted checks on existing PR 282.
dry_run: not_applicable
dry_run_evidence: Source-only scope; no real inventory or controller SSH transaction.
staging: not_applicable
staging_evidence: No provider resources or live rollout authorized by this PR request.
live: not_applicable
live_evidence: Production convergence and private-state acceptance remain separate.
client: not_applicable
client_evidence: Local synthetic protocols are not external client or human acceptance.
artifact: required
artifact_evidence: Pending reviewed source extension in existing PR 282.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IMP-RETENTION | ANS-1791587032080262 | Versioned bounded grants, monotonic 30-day compaction, mixed-policy/clock/GC/capacity checks, no-scan invalid requests, count/byte archive contraction, actual retained-path rejection and maintenance sandbox | passed locally |
| REQ-IMP-ACTIVATION | ANS-1791587032645227 | Native nginx SIGKILL and delayed/missing HUP worker adoption; exact candidate retirement; geodata paired activator and actual metadata read repair; unchanged probe-disable recovery | passed locally |
| REQ-IMP-TLS-CONCURRENCY | ANS-1791587032645227 | Actual self-steal interleaved rotation/disable and seven-day memory TLS validation; locked pruning plus portable 70-rotation and 80-empty-scaffold regressions | passed locally |
| REQ-IMP-DEVICE-AUTH | ANS-1791587033216706 | Real age/SOPS issue/readout/revoke and all-profile transaction; exact native JSON Caddy two-to-one-to-zero CONNECT, private artifact retirement and managed-PID activation | passed locally |
| REQ-IMP-METRICS | ANS-1791587033777473 | Permanent actual same-inode truncate/replacement regressions; admitted counters above log cap; native four-socket IPv4/IPv6 loopback and approved local Tailnet exporter scrapes; both sender jobs share normalized endpoint | passed locally |
| REQ-IMP-RECOVERY-INTENT | ANS-1791587034315130 | Existing replay suite plus durable outbox regressions: failed recovery, fresh pulses, restart, stale completion and matching successful acknowledgement | passed locally |
| REQ-IMP-AUDIT-GATE | ANS-1791587034859002 | Actual distro Lynis machine report plus disabled/unavailable/stale/malformed/warning gate failures; actual WARP fixture playbook idempotence, connection/trace refusals and reconvergence | passed locally |
| REQ-IMP-ACCEPTANCE | ANS-1791587035398569 | I01-I15/F43 evidence, prior safety, complete local/hosted gates and PR | pending |

## Coverage and scope

I01/I02/I04/I05/I06 corrections and I03 supported Unbound boundary are already
in the reviewed P2 extension; their evidence remains in that change. I11
same-inode recovery is present and receives permanent regression proof. Full
DNS-Morph source matching the role has not been found; no implementation source
has been supplied. Preserve the supported Unbound boundary qualification. No invented artifact or live/vendor claim is permitted.
New implementation covers I07-I15 and F43. No archive or feature closure follows
from a refusal-only or missing external-artifact state.

## Native evidence limits

The geodata drill uses the actual publisher and activation shell with a private
systemd HTTP asset consumer; it proves byte/metadata adoption and process-death
recovery, not Xray routing semantics. WARP command fixtures execute the actual
role and failure/reconvergence playbooks, not vendor registration. The local
canonical container completed convergence and idempotence but its verification
command hit an emulation SIGSEGV; hosted native architecture verification remains
required. Private exporter namespace addresses are synthetic local assignments,
not Tailnet enrollment or fleet evidence. Bootstrap legacy or missing authority
requires reviewed retirement/recreation and reissuance; no automatic reset occurs.

## Canonical role corrections

The first hosted run exposed root-created Naive log ownership and a disabled
self-steal owner with a missing document root on second shared-nginx convergence.
Both were reproduced with actual roles. Naive now provisions safe byte-preserving
service-owned logs before validation; hardened nonroot adoption, unchanged role
convergence, verification and actual 100 MiB log rotation pass. Disabled nginx
roots remain absent, and a typed disk-only witness permits unchanged promotion
only after a strictly newer canonical master on the same kernel boot. Native
first/second role convergence preserves the actual master/workers, returns zero
changes and serves TLS; malformed, future, stale and unsafe authority cases pass.
Independent review approves both corrections.
