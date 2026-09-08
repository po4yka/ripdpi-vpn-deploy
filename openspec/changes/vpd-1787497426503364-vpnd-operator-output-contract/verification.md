---
task_id: VPD-1787497426503364
change: vpd-1787497426503364-vpnd-operator-output-contract
commit_sha: null
local: required
local_evidence: "cargo fmt --check, cargo clippy --all-features --all-targets -- -D warnings, cargo test: 24 test binaries, 207 tests, 0 failures on the review commit"
remote_ci: required
remote_ci_evidence: ""
dry_run: not_applicable
dry_run_evidence: no Terraform surface
staging: not_applicable
staging_evidence: covered by local tests and CI cargo suite
live: not_applicable
live_evidence: no deployed-state dependency
client: not_applicable
client_evidence: client-facing emitters unaffected
artifact: not_applicable
artifact_evidence: man page is build output, no artifact contracts
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-MANPAGE-SYNC | VPD-1787497435906087 | vpnd/tests/man_page.rs renders every page from the real Cli::command(), walks the full command tree asserting every visible long flag reaches its page, and pins the values the deleted build.rs replica drifted on (4h probe-matrix duration default, share --token-stdin/--token-file) | passed |
| REQ-JSON-FLAG-HONESTY | VPD-1787497435909140 | --json is scoped to the subcommands that implement it: host list emits a JSON array (empty and non-empty), host show a compact record, probe-matrix a machine-readable run summary with the report path; cli.rs tests assert parse-time rejection for every unsupported invocation (doctor, deploy, update, pre-subcommand placement), host_crud.rs pins list/show emission and the unchanged pretty human mode, probe_matrix.rs json_summary unit test pins the summary shape | passed |
| REQ-CLIP-REQUIRES-AI | VPD-1787497435912334 | vpnd/src/cli.rs tests assert a parse-time error naming --ai for doctor --clip alone and a successful parse carrying both flags when --ai precedes --clip | passed |
| REQ-DOCTOR-RESILIENCE | VPD-1787497435914528 | vpnd/tests/doctor_resilience.rs (successor to doctor_bundle for step semantics) drives the real binary against make doubles: a mid-run failure keeps all six sections in step order, marks the failed step, captures its stderr, exits nonzero with a failure summary, --bundle preserves the same evidence, and a healthy run exits zero; render_step_section unit tests pin section shape | passed |
