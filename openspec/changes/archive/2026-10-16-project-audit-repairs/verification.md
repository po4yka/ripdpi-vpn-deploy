---
task_id: "SEC-1791735853691219"
change: "project-audit-repairs"
commit_sha: "3010dfb517b84cd7fbe9c3512b30b87d63b64fe8"
local: "passed"
local_evidence: "Recorded focused Mac evidence: 517 recovery/operator cases and 116 schema/Telegram cases passed, with snapshots and source lint. The monolithic local gate failed on registry timeout and its queued retry was cancelled; no complete new local success is claimed. Owner-approved full source coverage passed in actual M1 hosted CI; the failed monolithic local run is not reclassified as passing."
remote_ci: "passed"
remote_ci_evidence: "Actual integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8: CI 38792726270 completed all 88 jobs successfully with zero failed, cancelled, skipped or pending jobs. CodeQL 38792726004 completed both jobs successfully with zero open repository alerts. Native integration 116621390880, collector 116621391330, agent 116621391025, Kuma 116621392357 and transport runtime acceptance 116621390735 all passed."
dry_run: "not_applicable"
dry_run_evidence: "Source repair PR only; no real inventory or SSH transaction."
staging: "not_applicable"
staging_evidence: "No provider deployment is authorized by this source PR."
live: "not_applicable"
live_evidence: "Live convergence requires a separate reviewed rollout."
client: "not_applicable"
client_evidence: "No physical client acceptance is claimed by local regressions."
artifact: "passed"
artifact_evidence: "Actual M1 main CI 38792726270 passed all source schemas, contracts, snapshots and isolated runtime acceptance artifacts. Positive canonical collector/agent/Kuma and native client/runtime results are recorded below; no external rollout or notification receipt is inferred."
---

# Verification

## Current integrated main acceptance (passed)

Primary source is `3010dfb517b84cd7fbe9c3512b30b87d63b64fe8`. Main CI `38792726270` completed all 88 jobs successfully with zero failed, cancelled, skipped or pending jobs. CodeQL `38792726004` completed both jobs successfully with zero open repository alerts. All current mapped requirements and applicable source/client/artifact gates passed; external categories retain their original not-applicable scope. Prior numeric measurements are not reused as M1 observations.

## Historical evidence boundary

All requirement rows, commands, outcomes and numeric runtime observations in the following retained sections describe f6ad803e97237d8d8ec3839284d84db974ea986c and its recorded premerge/baseline runs. Their original source/run IDs remain unchanged. They are historical evidence, not current M1 acceptance. Statements that acceptance passed or remained pending apply to their original snapshot. Current integrated acceptance is recorded above and in Observed integrated M1 results below.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-GENERATION | SEC-1791735997436813 |Targeted guarded recovery and unguarded restart tests; runtime lane 104 passed; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-RETIRE | SEC-1791735997436813 |Exact producer-file grants and unsafe ownership refusal tests; runtime lane 104 passed; native service-write test added; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-IPV6 | SEC-1791735997436813 |Strict IPv6 render and policy regression tests; native empty-neighbour-cache test added; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-AWG | SEC-1791735997436813 |Actual localhost Ansible verifies configured instance names; secondary watchdog failure recovers its exact unit; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-RETENTION | SEC-1791735997436813 |XHTTP-only logrotate regression; all 163 template snapshots match; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-CLIENT | SEC-1791735998160729 |Exact client and ambiguous token-prefix refusal tests; operator lane 96 passed; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-SELECTION | SEC-1791735998160729 |Real Ansible limited inventory and canonical Make admission tests; observer-only and empty selections refuse; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-PROMOTION | SEC-1791735998160729 |Concurrent promotion and watcher publication regression tests; final operator subset 39 passed; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-LOCK | SEC-1791735998160729 |Held-writer exclusion, owned legacy 0644 repair and unsafe-file refusal tests; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-INSTALL | SEC-1791735998967800 |Executable installer accepts exact verified provenance and rejects bad provenance or checksum before execution; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-RELEASE | SEC-1791735998967800 |Draft-only mutation, immutable published reruns, upload-before-publication and tag handoff; final release subset 14 passed; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-FIXTURES | SEC-1791735998967800 |Synthetic Git configuration and explicit group ownership; taskctl 106 passed; five fixture modules 174 passed under hostile signing configuration; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-SSH | SEC-1791735998967800 |Active socket then service restart; failure withholds marker; loopback banner and closed-port refusal tests; final SSH subset 123 passed; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-HOST | SEC-1791735999672160 |Actual CLI and shell IP propagation; full vpnd suite 303 passed; isolated per-address ASN baseline; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-PORT | SEC-1791735999672160 |Default 8444, cohort override, explicit port and invalid-port refusal tests; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |
| REQ-AUDIT-QR | SEC-1791735999672160 |QR refresh and no-QR stale artifact removal tests; both synthetic page variants inspected in a browser; complete exact-source CI 38768887914 and native/full-stack cases passed| passed |

## Validation scope

The full vpnd suite passed 303 tests. The canonical test-transfer gate passed
all mapped cases for 206 baseline functions. Ruff, mypy, ShellCheck, actionlint,
and the offline automation-security scan passed. All 163 snapshots match.
Reproducible wheel/source construction, locked offline installation, packaged
resources and installer rollback passed. Browser inspection used synthetic data.

The full `make check` command passed its validation stages but stopped at
cloud-init schema validation because the Docker daemon is unavailable. A broad
portable unit run was interrupted after 2,552 passes, 34 failures, one skip and
138 deselections. Its failures exposed local tool selection, isolated dependency
and fixture defects; focused reruns cover the corrections. This interrupted run
is not a complete unit-suite result. Backup, monitoring and optional protocol
follow-up tests passed 91 cases with the corrected local tool environment.

Native Linux networking and systemd tests and Molecule were not run on this
macOS host with no available Docker daemon. Hosted exact-source checks remain
required. No real inventory, credential, provider or host operation was run.

## Review correction

The independent review identified one publication defect: a rerun could replace
assets on an already-published release. The workflow now refuses any mutation
unless the release is a draft. Executable workflow-shell regressions cover
published and unknown states, draft and missing releases, and upload failure.
All 14 release cases pass. The subsequent independent source review reported no
actionable P0-P2 findings. A final review of the fixture and coverage corrections
reported one P2 concern about doctor labeling external-target checks. This
finding was rejected after checking `doctor.STEPS`: doctor never invokes
`validate-target` or `tspu-canary`. Probe does invoke them and explicitly labels
them as not host-specific. The actual CLI regression confirms all six doctor
steps and selected-address propagation. No accepted finding remains.

The remaining synthetic Git fixtures use an explicit, non-autouse configuration
fixture. All 174 cases in the five affected modules pass with a deliberately
failing operator-style signer; no test invokes it. Actual repository signing is
unchanged.

The final complete staged pre-commit run passed all applicable hooks. The final
AWG, secrets-coverage and listener modules passed 64 tests; three additional
AWG cases passed with inherited privilege escalation enabled. The three shared
directory fixtures passed after setting their owned test group explicitly.

## Hosted CI repair

The first complete hosted run exposed a shared test basename, an incomplete
strict defaults oracle, and literal Jinja keys in retirement owner maps. Both
monitoring and honeypot now construct the full map as a Jinja expression. Actual
localhost Ansible tests use the unchanged consumer declarations and real retirement
stdin expression; the original map fails before the correction. The default and
custom paths and account cases keep the ownership subset check intact.

The CLI test has a unique module name for combined collection. The defaults
assertion includes the deliberate empty owner map. The installer test drops an
unused import, and the logrotate selector uses the canonical named renderer
instead of a raw Jinja environment. The focused defaults and installer modules
passed 85 cases; collection and CLI tests passed two cases; owner-map and
logrotate tests passed 17 cases. Full-stack convergence remains a hosted check.

The full vpnd suite passed 303 tests and all 206 mapped baseline functions.
The scoped source review reported one custom-path test concern. It was rejected:
`honeypot.textfile_dir` derives from `monitoring.node_exporter_textfile_dir` in
the actual role defaults; a direct rerun passed all 13 owner tests. No accepted
finding remains. All applicable staged pre-commit hooks passed. The repeated
local full gate passed container-based cloud-init schema validation after Docker
became available; its later stages and the next hosted run are still pending
at publication. The PR remains the live source for updated-head CI results.

## Integrated source verification (2026-10-15)

Exact main CI 38759230876 and CodeQL 38759230898 succeeded; all 7193 portable cases and 22 subtests and native runtime suites passed; open CodeQL alerts count zero. Source is `923304729f6bdd32edce6a9b6ceada1d51c7d011`; hosted logs were inspected directly. Focused recovery suite passed 517 and schema/Telegram portable suite 116 cases; complete local make check pending. No external infrastructure or real notification action occurred.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.

## Final source acceptance (2026-10-15)

All unchanged hosted source consumers and native acceptance passed in CI 38768887914 on `f6ad803e97237d8d8ec3839284d84db974ea986c`. Focused Mac validation, snapshots and full-history secret scanning passed as recorded above. The owner-approved task scope accepts this combined source gate; the failed monolithic Mac invocation is not reclassified as passing. No external infrastructure or human notification receipt is claimed.

## Observed integrated M1 results (2026-10-15; passed)

The following are actual observations from main CI `38792726270` on
`3010dfb517b84cd7fbe9c3512b30b87d63b64fe8`, separate from the retained
premerge evidence. All 88 CI jobs passed without failed, cancelled, skipped
or pending jobs. CodeQL run `38792726004` passed both jobs with zero open
repository alerts. Transport runtime acceptance job `116621390735` and the
final aggregate passed; complete current source acceptance is observed.

Main CodeQL acceptance passed with zero open repository alerts. Native
integration job `116621390880` passed all 138 baseline cases, both XHTTP
endpoint cases and the AWG two-instance case. Canonical enabled collector
job `116621391330`, enabled agent job `116621391025` and actual pinned Kuma
job `116621392357` also passed. Their positive process/TLS/persistence and
rollback observations do not claim production deployment. The final
transport runtime job and overall aggregate passed.

Transport runtime job `116621390735` passed all four complete cases in
1704.49 seconds on M1: Xray upgrade/retry, operator rollback with exact
unit/MainPID/candidate checks and reconvergence; Hysteria upgrade/retry;
site retirement with the remaining upgrade; and Hysteria SIGKILL validation
lease recovery. These are actual isolated Linux runtime observations.
