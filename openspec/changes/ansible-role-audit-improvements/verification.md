---
task_id: ANS-1791586652330612
change: ansible-role-audit-improvements
commit_sha: 39e613244f281e639f499f0e806bb8440720b9af
local: blocked
local_evidence: Final make check passed controller validation and all 152 snapshots, then reported 5850 Python tests and 22 subtests passed with one existing Snell smoke fixture exceeding its 45-second Ansible deadline before cleanup. The fixture, playbook and Snell template are unchanged from origin/main. The complete 57-case module and exact normal/umask077 host and Linux cases pass unchanged; the stall cause is unproven. Remaining local ci-fast stages did not run. Latest helper proofs passed 62 portable tests and 33 runtime guard tests on the owned Linux VM. Before the descriptor-only follow-ups, unchanged TLS/rendering/Naive consumers also passed 48 native integration tests; independent reviews approve. Full local acceptance remains pending.
remote_ci: passed
remote_ci_evidence: All 83 hosted checks passed for 39e613244f281e639f499f0e806bb8440720b9af; CI run 38028589428 and auxiliary runs 38028589239, 38028589246 and 38028589257 completed successfully. CodeQL reported zero open findings on merge commit 5f38c91c9f1ef7dd6da095072ffbef4d3732ecd2 and automatically resolved all 22 review threads.
dry_run: not_applicable
dry_run_evidence: Source-only scope; no real inventory or controller SSH transaction.
staging: not_applicable
staging_evidence: No provider resources or live rollout authorized by this PR request.
live: not_applicable
live_evidence: Production convergence and private-state acceptance remain separate.
client: not_applicable
client_evidence: Local synthetic protocols are not external client or human acceptance.
artifact: passed
artifact_evidence: Existing PR 282 contains the reviewed runtime, TLS, named-renderer and private selected-credential export corrections at 39e613244f281e639f499f0e806bb8440720b9af. Local acceptance remains blocked by the recorded existing fixture deadline; no archival or feature closure follows.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IMP-REVIEW | ANS-1791605822012676 | Initial 46 findings and subsequent ownership findings corrected; zero open CodeQL findings on exact source/merge, all 22 threads automatically resolved, actual FD/group/umask/ENOENT/private-export proofs and independent approval | passed source and CI |
| REQ-IMP-RETENTION | ANS-1791587032080262 | Versioned bounded grants, monotonic 30-day compaction, mixed-policy/clock/GC/capacity checks, no-scan invalid requests, count/byte archive contraction, actual retained-path rejection and maintenance sandbox | passed locally |
| REQ-IMP-ACTIVATION | ANS-1791587032645227 | Native nginx SIGKILL and delayed/missing HUP worker adoption; exact candidate retirement; geodata paired activator and actual metadata read repair; unchanged probe-disable recovery | passed locally |
| REQ-IMP-TLS-CONCURRENCY | ANS-1791587032645227 | Actual self-steal interleaved rotation/disable and seven-day memory TLS validation; locked pruning plus portable 70-rotation and 80-empty-scaffold regressions | passed locally |
| REQ-IMP-DEVICE-AUTH | ANS-1791587033216706 | Real age/SOPS issue/readout/revoke and all-profile transaction; exact native JSON Caddy two-to-one-to-zero CONNECT, private artifact retirement and managed-PID activation | passed locally |
| REQ-IMP-METRICS | ANS-1791587033777473 | Permanent actual same-inode truncate/replacement regressions; admitted counters above log cap; native four-socket IPv4/IPv6 loopback and approved local Tailnet exporter scrapes; both sender jobs share normalized endpoint | passed locally |
| REQ-IMP-RECOVERY-INTENT | ANS-1791587034315130 | Existing replay suite plus durable outbox regressions: failed recovery, fresh pulses, restart, stale completion and matching successful acknowledgement | passed locally |
| REQ-IMP-AUDIT-GATE | ANS-1791587034859002 | Actual distro Lynis machine report plus disabled/unavailable/stale/malformed/warning gate failures; actual WARP fixture playbook idempotence, connection/trace refusals and reconvergence | passed locally |
| REQ-IMP-ACCEPTANCE | ANS-1791587035398569 | I01-I15/F43 evidence with supported-Unbound scope, independent reviews, 83 passing hosted checks and existing PR 282; final local gate has one recorded existing fixture deadline | source/CI passed; local gate blocked |

## Coverage and scope

I01/I02/I04/I05/I06 corrections and I03 supported Unbound boundary are already
in the reviewed P2 extension; their evidence remains in that change. I11
same-inode recovery is present and receives permanent regression proof. The operator selected the supported Unbound boundary for I03. Full DNS-Morph
bridge functionality remains outside this PR capability; preserve that explicit
limitation. No invented artifact or live/vendor claim is permitted.
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

## PR review corrections

Xray and watchdog use explicit lexical descriptor ownership, including failed
inspection, directory handoff and cleanup paths. Watchdog obtains entropy before
opening files, preserves valid budget counters when tightening the prior group
grant, and treats only acquisition-time ENOENT as an absent budget. New candidates
are private; foreign replacement or collision bytes are never removed. Xray
validates both logs before granting the exact writer/reader group, and the policy
service provisions that group without GID drift or a DAC bypass capability.
Naive logs and watchdog state are owner-only. TLS probes reject deprecated
protocols. Named HTML/XML rendering escapes markup while preserving nonmarkup
credentials and quoting. Selected Naive readout requires an explicit new private
OUTPUT artifact; stdout contains only operation metadata. No warning suppression,
test exclusion, timeout increase or relaxed assertion was used.

The final full local run completed with 5850 tests and 22 subtests passed, one
45-second Ansible fixture deadline failure, and 123 native cases deliberately
partitioned to native jobs. The failure occurred during or after mock curl and
before the intended stop failure; retained uncertain ownership was preserved.
The complete unchanged 57-case module and normal/umask077 exact-case host/Linux
proofs pass. The precise controller stall cause remains unproven; local gate
acceptance is blocked, even though all 83 exact-source hosted checks pass.
