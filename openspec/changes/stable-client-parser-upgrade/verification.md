---
task_id: "TST-1791618376497512"
change: "stable-client-parser-upgrade"
commit_sha: null
local: "required"
local_evidence: "complete affected tests, exact native cases and full source gates after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal required checks on the exact integrated implementation SHA"
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "required"
client_evidence: "real isolated consuming-client behavior named in the requirements; not host activity alone"
artifact: "required"
artifact_evidence: "validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA"
---

# Verification

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
  architecture digests in `contract/hysteria-runtimes.json`. Release channel,
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
