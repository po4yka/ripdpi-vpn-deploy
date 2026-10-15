---
task_id: "ANS-1791618083683925"
change: "hysteria-ech-profiles"
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
client_evidence: "actual supported recipient parser and real authenticated protocol behavior"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

The requirement rows remain open until their complete named evidence is observed. Source implementation and the observations below do not satisfy unexecuted native, hosted or staging gates.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-ECH-CONTRACT | ANS-1791618091815754 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618093172970 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618095149688 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618093172970 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618094259404 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618095149688 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618094259404 | Real private-file and systemd compensation/intent tests with exact Hysteria connections; wrong-key, unsafe-path and interrupted-publication cases preserve prior generation. | required |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618095149688 | Real private-file and systemd compensation/intent tests with exact Hysteria connections; wrong-key, unsafe-path and interrupted-publication cases preserve prior generation. | required |
| REQ-PROTO-ECH-ACCEPT | ANS-1791618095149688 | NEW exact ECH native target plus separately authorized supported-recipient staging procedure, negotiated packet observations and guarded cleanup evidence. | required |

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
