---
task_id: "TST-1791618376497512"
change: "stable-client-parser-upgrade"
commit_sha: null
local: "required"
local_evidence: "complete affected tests, exact native cases and full source gates after implementation"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: "required"
artifact_evidence: "validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA"
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


## Requirement evidence

The requirement rows remain open until their complete named evidence is observed. Source implementation and the observations below do not satisfy unexecuted native, hosted or staging gates.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-PARSER-INTEGRITY | TST-1791618385464569 | Installer transaction and checksum failure tests with verified real candidate version output. | required |
| REQ-PROTO-PARSER-PAYLOADS | TST-1791618386942234 | Complete emit_singbox_roundtrip and liveness suites plus native-four-protocol acceptance on old/candidate inputs. | required |
| REQ-PROTO-PARSER-ROLLBACK | TST-1791618388220484 | Actual installed-tool rollback and complete hosted parser/native jobs with exact-SHA evidence. | required |
| REQ-PROTO-PARSER-ELIGIBILITY | TST-1791618385464569 | Deterministic release-age boundaries, unknown metadata and advisory cases; actual candidate parser/native compatibility remains a separate mandatory gate. | required |

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
- Exact official sing-box parsing/traffic, decoded packet observations, complete
  Linux ECH authority activation/rotation/compensation, terminal exact-SHA hosted
  checks and the separately authorized 48-hour staging soak remain required.
  Runtime downloads and Linux test dependency preparation were blocked by
  network timeouts. No deployment, real issuance or recipient redistribution ran.

## PR 303 continuation observations (2026-10-15)

Official sing-box 1.14.3 completed the exact Linux ECH parser, TCP/UDP/DNS,
trust/negotiation failure and outer-SNI packet matrix at source
`237b622f672629cbfecb53e010632af0c2e52273` (native job `116572820157`). Its
checksum-verified Darwin ARM64 release and Xray 26.3.27 also parsed complete
canonical liveness artifacts locally. The four portable shards at `87a52b6b`
reported 7,227 passed tests; final-head aggregate/native gates and complete
parser adoption/rollback acceptance remain required. Combined release
eligibility still refuses unavailable sing-box metadata; no production
recipient redistribution occurred.

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
