---
task_id: ANS-1791618083683925
change: hysteria-ech-profiles
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
staging: not_applicable
staging_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
live: not_applicable
live_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
client: not_applicable
client_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
artifact: not_applicable
artifact_evidence: "Task dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance."
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


## Requirement evidence

Each requirement row remains open until its complete named evidence is observed. Source implementation and the observations below do not satisfy unexecuted native, hosted or staging gates.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-ECH-CONTRACT | ANS-1791618091815754 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618093172970 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618095149688 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618093172970 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618094259404 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618095149688 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618094259404 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618095149688 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |
| REQ-PROTO-ECH-ACCEPT | ANS-1791618095149688 | Dropped: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance. | not_applicable |

## Source implementation observations (2026-10-15)

- Candidate inputs: Hysteria 2.13.0 and official sing-box 1.14.3, with exact
  architecture digests in `scripts/hysteria-runtimes.json`. Release channel,
  publication timestamps and asset digests were retrieved at execution time;
  the subsequent advisory refresh was unavailable, so promotion eligibility
  remains unconfirmed.
- Complete affected schema/runtime suites passed (267 tests); coordinated
  emitter/liveness/installation suites passed (206 tests); separate schema,
  bundle, liveness and lane-wiring suites passed (285 tests). Later focused
  interface checks passed (165 tests). These overlapping suites are not summed.
- A checksum-verified Hysteria 2.13.0 process completed real authenticated ECH
  loopback traffic with negotiated-ECH client telemetry. Wrong SAN, untrusted
  certificate, stale public configuration and wrong credentials refused. Private
  ECH keys were absent from captured process output. This is native Hysteria
  loopback evidence, not official sing-box, Linux sandbox or packet-capture proof.
- Affected-role Ansible lint passed (39 files); shellcheck at the repository's
  warning threshold, secret schema/coverage, all 163 render snapshots, task
  validation and strict OpenSpec validation passed.
- The full `build-gate -- make check` invocation failed retrieving Terraform
  provider authentication checksums from upstream releases. A complete portable
  suite was restarted after diagnosing an inactive local SOPS shim; its final
  result is reported with the PR and is not assumed here.
- At the initial handoff, official recipient traffic, packet observations, complete
  Linux activation/rotation/compensation and terminal exact-SHA hosted checks
  were unverified. The continuation observations below supersede that boundary.
  Runtime downloads and Linux test dependency preparation were blocked by
  network timeouts. No deployment, real issuance or recipient redistribution ran.

## PR 303 continuation observations (2026-10-15)

- Source `237b622f672629cbfecb53e010632af0c2e52273`, CI run
  `38778141118`, native job `116572820157`: all three selected ECH/resource
  cases passed in 49.09 seconds before the later source push cancelled the
  remaining job. This is not a pass for the complete native suite.
- Actual Hysteria 2.13.0 and official sing-box 1.14.3 completed authenticated
  TCP/UDP/DNS and the wrong-SAN, untrusted-CA, stale-generation, wrong-auth and
  ECH-disabled-server failures. Decoded QUIC captures contained the outer SNI
  and no inner SNI. Receive-buffer drops stayed zero; server RSS was
  33,144–33,396 KiB and the two measured clients each sustained
  3.14–3.25 million bytes/second on the identical controlled path. These
  observations establish behavior and bounds, not a performance improvement.
- Four portable shards in run `38775829979` reported 7,227 passed tests.
  Later affected contracts passed 247 tests, the focused ECH/release suite passed 55,
  and the baseline assertion/mutation-boundary suite passed eight. Counts
  overlap. The complete aggregate and exact final-head gates remain required.
- Native verified generation with real SOPS passed issuance, rotation,
  invalid-identity ciphertext preservation and private file permissions.
  Checksum-verified Darwin ARM64 sing-box 1.14.3 and Xray 26.3.27 parsed the
  canonical liveness artifacts successfully.
- Current source adds debug-level private-key leak checks and both BBR modes
  inside the actual systemd credential generation. Their new native execution,
  ECH rotation/compensation and full final-head source gates remain pending.
  Hysteria release eligibility refreshed successfully; the combined refresh
  still refuses when sing-box release metadata is unavailable. No staging,
  production deployment or real credential issuance occurred.

## Integrated native continuation (2026-10-15)

- Integrated source `4b5468333d7bfdf76f8cbe97a434aa59811d7541`, CI run
  `38794509169`: native transaction job `116628420233` passed both selected
  cases in 600.73 seconds. These execute actual systemd credential activation,
  unchanged convergence, admission SIGKILL/lease recovery, the complete ECH
  failure/death matrix, rotation, exact whole-route key/receipt compensation,
  both BBR profiles, classical transition and retirement. No selected case skipped.
- The ECH step in native integration job `116628420264` also passed all three
  resource profiles with debug-level key-leak assertions, real Hysteria 2.13.0
  and official sing-box 1.14.3 TCP/UDP/DNS, required-ECH/trust/auth failures and
  decoded outer-SNI captures. The complete job subsequently passed all 138
  native cases, both XHTTP cases and the AWG device-binding case. Warm-upgrade job
  `116628420272` subsequently passed its three cases in 1,658.81 seconds,
  including real Salamander and observed multi-port traffic before/after adoption
  and compensation. The integrated CI run completed with all 89 jobs successful.
- Whole-route authority now captures the private ECH key, and frontend-only
  changes open that recovery boundary before candidate staging. Isolated inline
  probe imports use the controller-prepared semantic companion. Focused regressions
  passed 180, 160 and 76 tests in overlapping suites; merged CI wiring passed 87.
- Parser adoption regressions now execute both actual CI installation fragments
  against an owned destination, preserving real prior parser usability after
  tampered/truncated, wrong-version or incompatible executable refusal. Their
  native execution remains required on the subsequent source revision.
- Current release channel and asset metadata refreshed; the direct combined
  advisory refresh still refused unavailable metadata. Publication eligibility
  therefore remains unconfirmed. The full local gate acquired a machine-wide slot after queueing; its
  complete result remains pending. Waiting is not a passing validation result.
- No staging soak, production deployment, real authority issuance or recipient
  redistribution ran. The 48-hour staging and dependency acceptance gates remain
  open; source/native observations do not close them.

The final identity correction selects the declared ECH inner name independently
of the nginx frontend in export, liveness and smoke probing. Its source and native
regressions retain distinct hostnames; subsequent exact-head validation is required.
