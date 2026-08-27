---
task_id: "VPD-1787496384518490"
change: "vpd-1787496384518490-vpnd-secrets-path-authority"
commit_sha: "bbc346415f412ab49f296db3927ff0fbefdaa8e0"
local: "blocked"
local_evidence: "2026-08-27: Rust debug/release each passed 173 tests, clippy/MSRV/deny passed; make validate and cloud-init schema passed. Full make check found two existing AWG installer fresh-directory failures under umask 077; root-cause correction and a complete rerun are pending."
remote_ci: "blocked"
remote_ci_evidence: "PR #108 is published. Expanded hosted Molecule coverage exposed runtime and scenario defects; final required-check success and main merge are still pending."
dry_run: "not_applicable"
dry_run_evidence: "no Terraform surface"
staging: "not_applicable"
staging_evidence: "covered by local tests and CI cargo suite"
live: "passed"
live_evidence: "2026-08-27: real operator SOPS and Terraform state, macOS without XDG_RUNTIME_DIR, source 33d30da. Two vpnd share invocations made exactly one real SOPS call via a pass-through counter; runtime mode 0600 and private bundle files verified. Official sing-box 1.13.16 accepted the actual payload. Unpublished local token only; no recipient issuance or network delivery claimed. Both plaintext runtime files were removed with make clean."
client: "not_applicable"
client_evidence: "recipient bundles unaffected"
artifact: "not_applicable"
artifact_evidence: "no artifact contracts affected"
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SECRETS-PATH-AUTHORITY | VPD-1787497013454189 | Resolution-matrix tests + a live macOS run of share without XDG_RUNTIME_DIR showing single decrypt | Passed |
| REQ-SECRETS-REDACTION-COVERAGE | VPD-1787497013472302 | doctor_bundle/proptest coverage asserting redaction of resolved paths in bundle AND ai prompt | Passed |
| REQ-SECRETS-HARDEN-GATE | VPD-1787497013490086 | Test injecting chmod failure asserts nonzero exit at each call site | Passed |
| REQ-SECRETS-HARDEN-GATE | VPD-1787497013509056 | Gate tests reject symlink-swap and bad-mode files opened through the held handle | Passed |

## 2026-08-27 review

The original implementation was reopened after review found executable defects.
Local regressions do not substitute for the dry-run, staging, live, or hosted-CI categories above.
Archive and terminal closure remain blocked until all required evidence is complete.

### Shared local checks on the reviewed source

- `python3 -m pytest tests/unit -q`: 995 passed, 2 existing skips; one honeypot thread shutdown warning. The warning was reproduced only when the test fixture closes its listener while a daemon accept thread is running; it was not observed before cleanup. The stale collected-count documentation was corrected before this successful run.
- `bats tests/bats/`: 55 passed.
- `make tf-test`: 79 provider mock tests passed.
- `make snapshot-check`: 102 templates matched.
- `make validate`, actionlint, shellcheck, cargo-deny and Rust 1.88 MSRV check passed. YAML lint has one existing workflow line-length warning.
- Render, AWG version floor, Xray guards, secrets coverage, deploy-profile, example secrets schema and bundle schema checks passed.
- `make check` did not pass: its Docker cloud-init step lost the Colima connection. Per-role Molecule did not run. These checks must be rerun in a working container environment.

## Resumed acceptance

- Atomic no-follow/nonblocking descriptor gates now cover secrets, tokens, and chmod. Missing/unsafe inputs and real fd chmod failure abort every caller.
- Make emission reuses the same protected plaintext; actual Make/emitter regression tests and a real SOPS share confirm one decrypt. The official parser passed both fixture and operator-generated payloads.
- The remaining global local/hosted checks above still prevent archival.
