---
task_id: SEC-1791735853691219
change: project-audit-repairs
commit_sha: 923304729f6bdd32edce6a9b6ceada1d51c7d011
local: required
local_evidence: "Focused recovery suite passed 517 and schema/Telegram portable suite 116 cases; complete local make check pending."
remote_ci: passed
remote_ci_evidence: "Exact main CI 38759230876 and CodeQL 38759230898 succeeded; all 7193 portable cases and 22 subtests and native runtime suites passed; open CodeQL alerts count zero."
dry_run: not_applicable
dry_run_evidence: Source repair PR only; no real inventory or SSH transaction.
staging: not_applicable
staging_evidence: No provider deployment is authorized by this source PR.
live: not_applicable
live_evidence: Live convergence requires a separate reviewed rollout.
client: not_applicable
client_evidence: No physical client acceptance is claimed by local regressions.
artifact: passed
artifact_evidence: https://github.com/po4yka/ripdpi-vpn-deploy/pull/290
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-GENERATION | SEC-1791735997436813 | Targeted guarded recovery and unguarded restart tests; runtime lane 104 passed | local regression passed; native or live acceptance separate |
| REQ-AUDIT-RETIRE | SEC-1791735997436813 | Exact producer-file grants and unsafe ownership refusal tests; runtime lane 104 passed; native service-write test added | local regression passed; native or live acceptance separate |
| REQ-AUDIT-IPV6 | SEC-1791735997436813 | Strict IPv6 render and policy regression tests; native empty-neighbour-cache test added | local regression passed; native or live acceptance separate |
| REQ-AUDIT-AWG | SEC-1791735997436813 | Actual localhost Ansible verifies configured instance names; secondary watchdog failure recovers its exact unit | local regression passed; native or live acceptance separate |
| REQ-AUDIT-RETENTION | SEC-1791735997436813 | XHTTP-only logrotate regression; all 163 template snapshots match | local regression passed; native or live acceptance separate |
| REQ-AUDIT-CLIENT | SEC-1791735998160729 | Exact client and ambiguous token-prefix refusal tests; operator lane 96 passed | local regression passed; native or live acceptance separate |
| REQ-AUDIT-SELECTION | SEC-1791735998160729 | Real Ansible limited inventory and canonical Make admission tests; observer-only and empty selections refuse | local regression passed; native or live acceptance separate |
| REQ-AUDIT-PROMOTION | SEC-1791735998160729 | Concurrent promotion and watcher publication regression tests; final operator subset 39 passed | local regression passed; native or live acceptance separate |
| REQ-AUDIT-LOCK | SEC-1791735998160729 | Held-writer exclusion, owned legacy 0644 repair and unsafe-file refusal tests | local regression passed; native or live acceptance separate |
| REQ-AUDIT-INSTALL | SEC-1791735998967800 | Executable installer accepts exact verified provenance and rejects bad provenance or checksum before execution | local regression passed; native or live acceptance separate |
| REQ-AUDIT-RELEASE | SEC-1791735998967800 | Draft-only mutation, immutable published reruns, upload-before-publication and tag handoff; final release subset 14 passed | local regression passed; native or live acceptance separate |
| REQ-AUDIT-FIXTURES | SEC-1791735998967800 | Synthetic Git configuration and explicit group ownership; taskctl 106 passed; five fixture modules 174 passed under hostile signing configuration | local regression passed; native or live acceptance separate |
| REQ-AUDIT-SSH | SEC-1791735998967800 | Active socket then service restart; failure withholds marker; loopback banner and closed-port refusal tests; final SSH subset 123 passed | local regressions passed; native activation separate |
| REQ-AUDIT-HOST | SEC-1791735999672160 | Actual CLI and shell IP propagation; full vpnd suite 303 passed; isolated per-address ASN baseline | local regression passed; native or live acceptance separate |
| REQ-AUDIT-PORT | SEC-1791735999672160 | Default 8444, cohort override, explicit port and invalid-port refusal tests | local regression passed; native or live acceptance separate |
| REQ-AUDIT-QR | SEC-1791735999672160 | QR refresh and no-QR stale artifact removal tests; both synthetic page variants inspected in a browser | local regression passed; native or live acceptance separate |

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
