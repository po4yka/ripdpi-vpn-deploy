---
task_id: "ANS-1791618048083304"
change: "awg-forwarding-dualstack"
commit_sha: "df5c40554cb171f2b0acc6b275a65579a05d7806"
local: "passed"
local_evidence: "full make check exit 0: 7563 unit cases, 43 subtests, 320 vpnd cases, validation and CI parity; portable AWG design matrix 204 passed"
remote_ci: "passed"
remote_ci_evidence: "deployment CI 38931291291: all 89 jobs passed on df5c40554cb171f2b0acc6b275a65579a05d7806; consumer CI 38946668519 succeeded on 974cf06ab8d05e3b4275d0e98429a0d0de2bf598"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source capability"
client: "passed"
client_evidence: "consumer 974cf06ab8d05e3b4275d0e98429a0d0de2bf598 passed two independent original-peer arm64 API 35 matrices, each 8 sessions and 64 observations, IPv4/IPv6 TCP/UDP/DNS at MTU 1280/1420 with three reconnects each; producer evidence validator passed both"
artifact: "passed"
artifact_evidence: "both invocation-bound receipts and complete APK/SO/peer/instrumentation artifact sets retained and revalidated against actual digests; Linux native traffic, counters and compensation observed without operator material"
---

# Verification

## Source and acceptance boundary

Deployment runtime source is `df5c40554cb171f2b0acc6b275a65579a05d7806`.
Consumer source is `974cf06ab8d05e3b4275d0e98429a0d0de2bf598`, proposed in
RIPDPI PR #619 under `po4yka/RIPDPI#DAT-1792081130689287`. Its task remains
in review; this deployment task does not close the consumer record.
The earlier AWG contract implementation was integrated through deployment
PR #304 and consumer PR #616. No fleet deployment, provider mutation or actual
operator-secret migration was performed.

The owner explicitly scoped Android acceptance to arm64 emulator/native-core.
Physical-device and Android VpnService/TUN acceptance are outside this change.
The actual supported core used S3=S4=0; the arm64 version floor is unchanged.
Linux forwarding, revocation, tunnel-death lockdown and whole-configuration
compensation remain required and passed separately.

## Requirement evidence

| Requirement | Execution step | Observed evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-FORWARD | ANS-1791618053810186 | Real native one/two-instance namespace traffic, exact uplink NAT counters and authenticated return traffic; retained firewall compensation preserves foreign tables. | passed |
| REQ-PROTO-AWG-FORWARD | ANS-1791618055065632 | All six native AWG cases passed on exact deployment source in CI 38931291291; full local source gate passed. | passed |
| REQ-PROTO-AWG-DUAL | ANS-1791618053112824 | Typed device addresses share server, standalone, bundle and liveness resolution; portable design matrix 204 passed; complete affected consumer JVM suites 3132 passed. | passed |
| REQ-PROTO-AWG-DUAL | ANS-1791618054450509 | Two canonical original-peer arm64 matrices each delivered actual IPv4/IPv6 TCP/UDP/DNS through eight sessions; clean committed federation validated 189 tasks. | passed |
| REQ-PROTO-AWG-DUAL | ANS-1791618055065632 | Native one/two-instance family traffic, DNS and device revocation passed; exact-source producer and consumer hosted checks succeeded. | passed |
| REQ-PROTO-AWG-MTU | ANS-1791618053112824 | Shared instance/cohort/role/default precedence and malformed MTU refusal passed with parser/runtime boundary coverage. | passed |
| REQ-PROTO-AWG-MTU | ANS-1791618054450509 | Actual native-core exchanges at MTU 1280 and 1420 passed baseline plus three reconnects each in two independent canonical runs. | passed |
| REQ-PROTO-AWG-MTU | ANS-1791618055065632 | Constrained Linux path at MTU 1280 delivered 30 recorded exchanges; 720/720 UDP replies, byte/time observations retained in hosted native logs. | passed |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618053810186 | Native firewall retention and failed activation restore complete addresses, MTU, private bytes and prior service or fresh default-drop baseline. | passed |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618054450509 | Native tunnel-death and revoked-device failures cannot bypass routing/firewall authority; liveness policy and consumer contract integration passed. | passed |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618055065632 | All six exact-source native cases and complete source gate passed; actual Android acceptance remains native-core scoped. | passed |

## Local and hosted gates

Complete local `build-gate -- make check` exited 0: 7563 unit cases,
43 subtests and 320 vpnd cases passed, with schema/secret coverage, Terraform
validation/tests/policies, Ansible lint, all 164 snapshots and CI parity.
The unit lane deselected 181 native cases by design; native acceptance was
observed independently on Linux root/systemd/TUN.

Deployment CI run 38931291291 completed all 89 jobs successfully on the exact
runtime source. Native integration passed 13 ECH, 138 generic runtime,
10 XHTTP delivery, 8 authenticated topology and all 6 AWG dual-stack cases,
without selected skips. The AWG target completed in 89.03 seconds.
Its actual namespace test was
`test_owned_uplink_nat_mtu_dns_reconnect_revocation_and_no_native_bypass`;
activation tests exercised whole-config restoration and both owned/fresh
firewall compensation. Thirty recorded exchanges each delivered 127104 bytes
in 0.003104760000042006 to 0.018433120000281633 seconds, with 720/720 UDP
replies total. These are aggregate isolated-lab byte/time observations, not an
Internet benchmark or a claim that an MTU preset is optimal.

Consumer CI run 38946668519 succeeded on the exact consumer SHA: 33 jobs passed
and 25 conditional jobs were skipped. All 40 executed PR checks succeeded,
including CodeQL, secret scan, harness checks, the required aggregate and Play,
F-Droid and GitHub release verification. No checks remained pending. These
conditional job selections do not replace the unskipped canonical runs below.

Qualified `make task-federation` validated 189 tasks against clean committed
producer `748ae57bfc5da6b0a9920761b9c89160a2df5e24` and consumer
`974cf06ab8d05e3b4275d0e98429a0d0de2bf598`. No qualified reference alone was
counted as federation acceptance.

## Consumer runtime and artifacts

Complete affected JVM modules passed 3132 tests on consumer
`335d5de361445c8decef5560a07ebf3f60fe524f`: data/parser 887, service 2245,
no failures, errors or skips. These modules and the interop harness remained
byte-identical at the new consumer source; the companion fix changes Rust UDP.

A real pre-poll UDP datagram regression failed on the old source and passed on
`974cf06ab8d05e3b4275d0e98429a0d0de2bf598`. The full warp-core suite passed
95 cases, strict async-holding Clippy and ordinary commit hooks passed, and
independent general and async cancellation reviews approved the exact file.
The production subscription is now created synchronously and moved into run;
terminal teardown remains explicit.

Two independent canonical runs used original peer
`2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf` (v0.2.12, go1.27.1), API 35,
arm64-v8a, and unchanged assertions/deadlines. Each delivered 8 sessions and
64 measured IPv4/IPv6 TCP/UDP/DNS observations, baseline plus three reconnects
at both MTUs, with eight successful real socket protection calls. Both complete
artifact sets passed standalone validation and the producer's
`make verify-awg-dualstack-client-evidence`; their retained copies also passed.
Each APK packages exactly its recorded native library.

Invocation nonces are
`topology-awg-startup-974cf06ab8d05e3b4275d0e98429a0d0de2bf598` and the same
value suffixed `-confirmation`. Receipt SHA-256 values are
`2013956f82e2fa4c4e3e1bc0b7298ec729ae567197b004275dd0318b263aaf4f` and
`74d05b6a79cca857ae951ab978e6d8c96b8b7a301ed2a493c1711595a4802b89`.
Both record native library
`19408cf9b2b19dfc48ef7c45133a01261a327a185803ecbb9a99b2753dbec135`
and test APK
`fadf364a4de709f76081a31e7bcc1ac460d2c9b365c1a83301529be820e82355`.
Each independently built original peer binary has its own validated digest;
no byte-identical peer-binary claim is made.

## Earlier failed attempts and limits

Earlier local aggregates failed pinned Terraform registry downloads, Docker
Ubuntu APT reachability and HOME-sensitive SOPS/tool resolution. Exact cached
providers, verified tools and a bounded local TLS CONNECT route enabled the
later full successful aggregate without relaxing TLS, pins or gates. An earlier
generic local lab returned 87 passed, 26 failed, 19 setup errors and 6 skipped;
the configured exact-source hosted lane subsequently passed all 138 cases.
A liveness aggregate had an Xray startup failure; its three cases passed on a
focused rerun, and the complete later source gate passed. Earlier all-files
hook failures are not reported as successful runs; every actual commit used
ordinary passing hooks.

Two original-peer canonical attempts on the older consumer failed UDP receive
during reconnect and generated no acceptance receipt. Diagnostic logging and
in-memory peer variants passed but were not used as acceptance. The separately
proven startup gap has a real red/green regression; its causal relationship to
those older timeouts remains unproven. A missing temporary public peer input
also stopped one invocation before build/device and was restored at the exact
pin. Later canonical success does not relabel any of those failures as passes.

All heavy compilation and test invocations used the machine-wide build gate.
No foreign process was stopped. No fixture, fabricated receipt or selected skip
was used to claim positive native or Android acceptance.
