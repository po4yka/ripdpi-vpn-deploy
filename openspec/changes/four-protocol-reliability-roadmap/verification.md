---
task_id: "EPC-1791618453830051"
change: "four-protocol-reliability-roadmap"
commit_sha: null
local: "required"
local_evidence: "complete child local/native suites after implementation; planning checks are not runtime acceptance"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "this source/feature portfolio does not run real deployment inputs; any rollout gets its own authorized controller scope"
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: "not_applicable"
live_evidence: "no production rollout or revival of cancelled fleet acceptance is part of this portfolio"
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: "required"
artifact_evidence: "exact-source contract/rendered/private-output and redacted native/candidate evidence mapped to every finding"
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-PORTFOLIO-ISOLATION | EPC-1791618459636532 | Run the child isolation, binding, schema and native-completion scenarios with exact runtime and client identities; link every A01-A22 row to a child or inherited owner. | required |
| REQ-PROTO-PORTFOLIO-LIFECYCLE | EPC-1791618460420156 | Map real warm AWG, hopping, Xray rotation, nginx compensation/privacy and health topology scenarios to inherited and new linked owners. | required |
| REQ-PROTO-PORTFOLIO-EVOLUTION | EPC-1791618461249475 | Require candidate-specific architecture/hash/advisory refresh, exact local parser/traffic, bounded local runtime and compensation cases; retain PQE and nonzero S3/S4 HOLD. | required |
| REQ-PROTO-PORTFOLIO-EVIDENCE | EPC-1791618462520842 | Validate complete audit coverage, DAG, source-fixed pointers and child evidence mappings; verify actual future source/native/client/staging results before feature completion. | required |
