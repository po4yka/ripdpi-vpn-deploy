---
task_id: "MON-1791618056169855"
change: "topology-authenticated-probes"
commit_sha: "df5c40554cb171f2b0acc6b275a65579a05d7806"
local: "passed"
local_evidence: "full make check exit 0: 7563 unit cases and 43 subtests, 320 vpnd cases, validation, lint, all 164 snapshots and CI parity passed on exact runtime source"
remote_ci: "passed"
remote_ci_evidence: "CI 38931291291 completed all 89 jobs successfully on df5c40554cb171f2b0acc6b275a65579a05d7806; CodeQL, Markdown and instruction-touch workflows succeeded"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source capability"
client: "passed"
client_evidence: "exact pinned Xray/Hysteria/AWG clients passed authenticated topology, actual hopping/upgrade/compensation and warm adoption; consumer 974cf06ab8d05e3b4275d0e98429a0d0de2bf598 passed two canonical arm64 matrices"
artifact: "passed"
artifact_evidence: "native and renderer contracts exercised private configuration and categorical failures; both complete arm64 APK/SO/peer/instrumentation artifact sets retained and validated; no operator material used"
---

# Verification

## Source and completion boundary

Runtime source is `df5c40554cb171f2b0acc6b275a65579a05d7806`, including
integration of source `5daffa6a630883c389257ef161f6c9663103c47c` and its XHTTP
delivery contract. Watchdog retains admitted XHTTP mode and bounded-pool fields;
real native cases cover auto and tuned stream-up. Later evidence and lifecycle
commits do not change runtime behavior.

Prerequisite `ANS-1791618048083304` reached committed `done` in `0e6bd844`.
Its complete evidence is retained in
`openspec/changes/archive/2026-10-16-awg-forwarding-dualstack/verification.md`.
All canonical dependency edges remain intact. No fleet deployment, provider
mutation, operator-secret migration or real notification receipt was performed.

## Requirement evidence

| Requirement | Execution step | Observed evidence | Result |
|---|---|---|---|
| REQ-PROTO-PROBE-TOPOLOGY | MON-1791618060162436 | Exact-source native matrix passed cohort-only REALITY, effective XHTTP/Hysteria layouts, separate frontend/backend failure and shared recovery ownership. Real two-instance AWG encrypted traffic and per-device revocation passed. Portable omitted-toggle, disabled-input and mode/pool contracts passed. | passed |
| REQ-PROTO-PROBE-AUTH | MON-1791618061120158 | All 8 native topology cases passed without skips. Exact pinned clients delivered controlled requests; wrong UUID/password, SAN/trust and mismatched Salamander failed while direct controls succeeded. Real source-built AWG authenticated independent instances. | passed |
| REQ-PROTO-PROBE-OWNERSHIP | MON-1791618061120158 | Executable watchdog/lifecycle/state/notification tests passed: exact socket PID, foreign socket refusal, owned bounded TERM/KILL cleanup, kernel lock release after SIGKILL, durable pre-action budgets and exact recovery target. Real Hysteria delivery followed by SIGSTOP observed bounded failure and cleanup. Two-cohort smoke cleanup passed. | passed |
| REQ-PROTO-PROBE-EVIDENCE | MON-1791618062766877 | Full local gate and all 89 exact-source hosted jobs passed. Native AWG warm adoption observed new ELF inode/PID and unit sandbox, followed by unchanged PID convergence. Real Hysteria hopping passed before/after upgrade and compensation. AWG prerequisite, both canonical Android matrices, consumer CI and clean committed federation passed. | passed |

## Source gates

Complete local `build-gate -- make check` exited 0: 7563 unit cases,
43 subtests and 320 vpnd cases passed. Terraform validation and test groups,
policies, Ansible lint and syntax, schema/secret coverage, all 164 snapshots,
canonical parser checks, lint/type checks and vpnd parity passed. The unit lane
intentionally deselected 181 native cases; separate Linux lanes supplied actual
native acceptance. Canonical sing-box 1.14.3 and Xray 26.3.27 were used.

CI run 38931291291 completed all 89 jobs successfully on the exact runtime
source. Native integration passed 13 ECH, 138 generic runtime, 10 XHTTP delivery,
8 authenticated topology and 6 AWG dual-stack cases without selected skips.
The topology target completed in 164.17 seconds. Both transport runtime shards
passed three cases each; each intentionally deselected the other shard's three.
The Hysteria shard observed real hopping traffic before upgrade, after upgrade
and after compensation, including unchanged convergence and unrelated UDP
control traffic. The warm fixture staged exact tools outside the source checkout
while preserving the actual `ProtectHome=yes` unit sandbox.

CodeQL run 38931291088, Markdown run 38931291427 and instruction-touch run
38931291044 also completed successfully. The merged-source integration passed
95 focused cases, all 164 snapshots, ordinary commit hooks and independent
specification/standards reviews. All later task commits retain ordinary hooks.

## Client and dependency evidence

Consumer source `974cf06ab8d05e3b4275d0e98429a0d0de2bf598` passed two independent
original-peer API 35 arm64 native-core matrices. Each delivered 8 sessions and
64 IPv4/IPv6 TCP/UDP/DNS observations at MTU 1280/1420, baseline plus three
reconnects each, with eight successful real socket protection calls. Both complete
APK/SO/peer/instrumentation artifact sets passed the producer's
`make verify-awg-dualstack-client-evidence`, with invocation/source identity,
artifact digests, exact packaged library and actual measurement logs checked.
Their exact receipt and binary identities are recorded in the AWG archive.
Physical-device and Android VpnService/TUN acceptance were explicitly excluded
by the owner; these native-core results do not claim those outcomes.

Consumer CI 38946668519 succeeded on that exact source: 33 jobs passed,
25 conditional jobs skipped and all 40 executed PR checks successful, including
CodeQL, secret scan and all three release verification shards. No checks remained
pending. Full affected JVM modules passed 3132 cases on byte-identical module
source; the companion UDP fix passed a genuine red/green regression, all
95 warp-core tests, async Clippy and independent general/cancellation reviews.

`make task-federation` validated 189 tasks against clean committed producer
`748ae57bfc5da6b0a9920761b9c89160a2df5e24` and consumer
`974cf06ab8d05e3b4275d0e98429a0d0de2bf598`. A qualified reference alone was
not counted as federation evidence.

## Earlier failures and operator boundary

Earlier local aggregates failed a trailing empty line, a local sing-box version
mismatch, exact Terraform provider network downloads and Docker Ubuntu APT
reachability. Those failures were fixed using reviewed formatting, verified
pinned tools, a checksum-enforced provider mirror and a bounded local TLS
CONNECT route; the complete later aggregate passed. The initial combined
focused run had 134 passes and one watchdog fixture startup failure; the
corrected watchdog suite passed all 17 cases, followed by the full source gate.
An incomplete generic local lab had 87 passes, 26 failures, 19 setup errors and
6 skips; the configured hosted lane subsequently passed all 138 native cases.
An earlier warm fixture failed under `ProtectHome=yes`; only its tool staging
was repaired, and the production unit sandbox was preserved.

Two older original-peer Android invocations failed UDP reconnect and produced
no acceptance receipt. Diagnostic peer variants passed but were not counted.
The independently proven UDP startup gap has a real red/green regression;
causality for those earlier timeouts remains unproven. The later two unchanged
canonical matrices passed on the new source, with assertions and deadlines
preserved. Historical failures are not relabeled as successful runs.

Enabled Hysteria now requires a separately enrolled watchdog identity (default
`watchdog`); recipient credentials are never reused. Configure that identity
before any separately authorized deployment. No production rollout or private
credential issuance is implied by source completion.
