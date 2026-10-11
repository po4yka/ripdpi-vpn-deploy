---
task_id: ANS-1791586652330612
change: ansible-role-audit-improvements
commit_sha: "cf01f94a640913412f3316b5cb288881639712ce"
local: "passed"
local_evidence: "Complete local gate components passed across native macOS and Linux arm64 on unchanged runtime source cf01f94a640913412f3316b5cb288881639712ce. Mac validation and every ci-fast stage before test-unit passed; all four complete disjoint Linux ordinary-user portable groups passed (6340 tests passed across all four complete disjoint portable CI groups; group 1: 1585 passed, 4890 deselected, 5 warnings, 7 subtests passed in 255.95s (0:04:15); group 2: 1584 passed, 4891 deselected, 6 warnings, 9 subtests passed in 232.44s (0:03:52); group 3: 1585 passed, 4890 deselected, 5 warnings in 232.07s (0:03:52); group 4: 1586 passed, 4889 deselected, 2 warnings, 6 subtests passed in 256.55s (0:04:16)), all CLI tests passed (297 passed in 26.87s), lint and baseline transfer passed, and all 57 shell tests passed. No single make check invocation is claimed successful; earlier failures are retained below."
remote_ci: "passed"
remote_ci_evidence: "Protected-main CI run 38134843683 completed successfully on exact integrated source cf01f94a640913412f3316b5cb288881639712ce; all jobs succeeded, including portable, native, role, failure and full-stack checks. Scorecard, CodeQL and release-please completed successfully on the same source."
dry_run: not_applicable
dry_run_evidence: Source-only scope; no real inventory or controller SSH transaction.
staging: not_applicable
staging_evidence: No provider resources or live rollout authorized by this PR request.
live: not_applicable
live_evidence: Production convergence and private-state acceptance remain separate.
client: not_applicable
client_evidence: Local synthetic protocols are not external client or human acceptance.
artifact: "passed"
artifact_evidence: "Exact integrated source cf01f94a640913412f3316b5cb288881639712ce passed all 86 hosted jobs; 163 rendered templates and golden snapshots matched locally. Complete scoped native artifacts and reviewed private-output/contract proofs are retained below; no new production artifact or fleet rollout is claimed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IMP-REVIEW | ANS-1791605822012676 | Initial 46 findings and subsequent ownership findings corrected; zero open CodeQL findings on exact source/merge, all 22 threads automatically resolved, actual FD/group/umask/ENOENT/private-export proofs and independent approval | passed |
| REQ-IMP-RETENTION | ANS-1791587032080262 | Versioned bounded grants, monotonic 30-day compaction, mixed-policy/clock/GC/capacity checks, no-scan invalid requests, count/byte archive contraction, actual retained-path rejection and maintenance sandbox | passed |
| REQ-IMP-ACTIVATION | ANS-1791587032645227 | Native nginx SIGKILL and delayed/missing HUP worker adoption; exact candidate retirement; geodata paired activator and actual metadata read repair; unchanged probe-disable recovery | passed |
| REQ-IMP-TLS-CONCURRENCY | ANS-1791587032645227 | Actual self-steal interleaved rotation/disable and seven-day memory TLS validation; locked pruning plus portable 70-rotation and 80-empty-scaffold regressions | passed |
| REQ-IMP-DEVICE-AUTH | ANS-1791587033216706 | Real age/SOPS issue/readout/revoke and all-profile transaction; exact native JSON Caddy two-to-one-to-zero CONNECT, private artifact retirement and managed-PID activation | passed |
| REQ-IMP-METRICS | ANS-1791587033777473 | Permanent actual same-inode truncate/replacement regressions; admitted counters above log cap; native four-socket IPv4/IPv6 loopback and approved local Tailnet exporter scrapes; both sender jobs share normalized endpoint | passed |
| REQ-IMP-RECOVERY-INTENT | ANS-1791587034315130 | Existing replay suite plus durable outbox regressions: failed recovery, fresh pulses, restart, stale completion and matching successful acknowledgement | passed |
| REQ-IMP-AUDIT-GATE | ANS-1791587034859002 | Actual distro Lynis machine report plus disabled/unavailable/stale/malformed/warning gate failures; actual WARP fixture playbook idempotence, connection/trace refusals and reconvergence | passed |
| REQ-IMP-ACCEPTANCE | ANS-1791587035398569 | I01-I15/F43 evidence with supported-Unbound scope, independent reviews, 83 passing hosted checks and existing PR 282; final closure local gate components passed; the earlier fixture deadline remains historical | passed |

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

## Closure reconciliation (2026-10-11)

The preceding sections retain their historical source and environment boundaries. The earlier verification SHA was `39e613244f281e639f499f0e806bb8440720b9af`. The accepted integrated source for this closure is `cf01f94a640913412f3316b5cb288881639712ce`; protected-main CI run `38134843683` completed with every job successful. This supersedes earlier pending PR/hosted-check observations without claiming a new deployment. Runtime and source files are unchanged by the closure increment.

## Final closure acceptance (2026-10-12)

The closure snapshot `e6ac235439bc66f9bb2bf9d9c71a4dded780ac38` has byte-identical production runtime files to integrated source `cf01f94a640913412f3316b5cb288881639712ce`. Validation was assembled from the complete passed Mac `validate` and `ci-fast` pre-test stages, then the complete ordinary-user Linux `make test-unit-shard PYTEST_GROUP=1..4`, `make vpnd-lint vpnd-test vpnd-parity-check` and `bats tests/bats/` stages. Portable result: 6340 tests passed across all four complete disjoint portable CI groups; group 1: 1585 passed, 4890 deselected, 5 warnings, 7 subtests passed in 255.95s (0:04:15); group 2: 1584 passed, 4891 deselected, 6 warnings, 9 subtests passed in 232.44s (0:03:52); group 3: 1585 passed, 4890 deselected, 5 warnings in 232.07s (0:03:52); group 4: 1586 passed, 4889 deselected, 2 warnings, 6 subtests passed in 256.55s (0:04:16). CLI result: 297 passed in 26.87s. All 57 shell tests passed; all 206 baseline transfer functions mapped to passing cases. No selected tests were skipped and no assertions, deadlines, locks or production source were changed.

Earlier attempts retain their failed diagnostic status: tool activation, root-only runner admission, absent parser/cache prerequisites, existing Mac fixture deadlines, and the intermittent monolithic SSH recovery unit failure did not count as acceptance. Read-only tracing diagnosed the original failure. The acceptance snapshot isolates the adapter test clock interface from the shared standard-library time module; production behavior, assertions and deadlines are unchanged. The complete 118-test SSH module subsequently passed without tracing. The tracer observed Python subprocess polling consuming the shared test fake clock and making its fixed synthetic worker timestamps stale; production freshness checks remained intact. All four canonical CI groups subsequently passed without the diagnostic tracer and with unchanged production source and assertions. The Linux arm64 standalone `make check` stopped at a Scaleway cached-provider checksum mismatch; the repository lockfile was preserved and the already-passed native Mac Terraform validation supplied that component. This record claims passed components across both environments, not one successful standalone `make check`. Protected-main CI run `38134843683` passed all 86 jobs on `cf01f94a640913412f3316b5cb288881639712ce`, including the complete native, role, failure and full-stack lanes.
