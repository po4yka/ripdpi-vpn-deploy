---
task_id: "SCR-1791618064422507"
change: "hysteria-stable-upgrade"
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
| REQ-PROTO-HY-VERSION | SCR-1791618069580618 | Version-consumer consistency, digest rejection and exact native parser cases; recorded execution-time refresh and staging eligibility are separate from unit fixture assertions. | required |
| REQ-PROTO-HY-VERSION | SCR-1791618072302643 | Version-consumer consistency, digest rejection and exact native parser cases; recorded execution-time refresh and staging eligibility are separate from unit fixture assertions. | required |
| REQ-PROTO-HY-TUNING | SCR-1791618070531675 | Schema boundary tests, exact binary startup under rendered sandbox, effective sysctl inspection and coordinated client configuration tests. | required |
| REQ-PROTO-HY-TUNING | SCR-1791618072302643 | Schema boundary tests, exact binary startup under rendered sandbox, effective sysctl inspection and coordinated client configuration tests. | required |
| REQ-PROTO-HY-MEASURE | SCR-1791618071381219 | NEW measured runtime target with controlled Linux network impairment and two real clients; do not silently skip required modes or substitute a fixture server. | required |
| REQ-PROTO-HY-MEASURE | SCR-1791618072302643 | NEW measured runtime target with controlled Linux network impairment and two real clients; do not silently skip required modes or substitute a fixture server. | required |
| REQ-PROTO-HY-UPGRADE | SCR-1791618071381219 | Extend real runtime-release adoption/compensation cases with exact Hysteria sockets, secure trust, Salamander and multi-port traffic; capture process identity instead of invoking only the new installed command. | required |
| REQ-PROTO-HY-UPGRADE | SCR-1791618072302643 | Extend real runtime-release adoption/compensation cases with exact Hysteria sockets, secure trust, Salamander and multi-port traffic; capture process identity instead of invoking only the new installed command. | required |

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

The three exact Linux profiles passed in native job `116572820157` at source
`237b622f672629cbfecb53e010632af0c2e52273`: authenticated TCP/UDP/DNS, paired
client measurements, zero receive drops, 7,500,000-byte socket ceilings and
33,144–33,396 KiB server RSS. The baseline source assertion's accepted integer
boundaries and refusal-before-mutation cases passed eight tests. Both BBR modes
in the actual systemd sandbox, warm Salamander/hopping upgrade and compensation
remain required; the execution step stays open until those observations exist.
The refreshed Hysteria release/advisory check cleared; the combined pair check
still refuses unavailable sing-box metadata. The 48-hour staging soak is pending.
