---
task_id: VPD-1787496384518490
change: vpd-1787496384518490-vpnd-secrets-path-authority
commit_sha: bbc346415f412ab49f296db3927ff0fbefdaa8e0
local: blocked
local_evidence: '2026-08-27: cargo test passed 164 tests and cargo clippy --all-targets -D warnings passed; BATS decrypt 5/5 and shellcheck passed. Atomic file-open and held-descriptor permission hardening remain unimplemented pending approval for a direct rustix dependency.'
remote_ci: blocked
remote_ci_evidence: No hosted CI run for this implementation SHA; Linux-specific permission tests remain unverified.
dry_run: not_applicable
dry_run_evidence: no Terraform surface
staging: not_applicable
staging_evidence: covered by local tests and CI cargo suite
live: blocked
live_evidence: No real macOS share with operator SOPS secrets was run. The subprocess no-XDG/double-decrypt test uses explicit command doubles and is local evidence only.
client: not_applicable
client_evidence: recipient bundles unaffected
artifact: not_applicable
artifact_evidence: no artifact contracts affected
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SECRETS-PATH-AUTHORITY | VPD-1787497013454189 | Resolution-matrix tests + a live macOS run of share without XDG_RUNTIME_DIR showing single decrypt | Pending |
| REQ-SECRETS-REDACTION-COVERAGE | VPD-1787497013472302 | doctor_bundle/proptest coverage asserting redaction of resolved paths in bundle AND ai prompt | Pending |
| REQ-SECRETS-HARDEN-GATE | VPD-1787497013490086 | Test injecting chmod failure asserts nonzero exit at each call site | Pending |
| REQ-SECRETS-HARDEN-GATE | VPD-1787497013509056 | Gate tests reject symlink-swap and bad-mode files opened through the held handle | Pending |

## Unresolved review findings

- `Secrets::load` and token loading still separate lstat from open, allowing a symlink swap; token ownership is not checked.
- `secure_secrets_file` still chmods by path and silently accepts a missing file.
- Fix both with non-following, nonblocking open, metadata checks and chmod/read on the held descriptor. Direct `rustix` dependency approval is pending; no new dependency has been added.

## 2026-08-27 review

The original implementation was reopened after review found executable defects.
Local regressions do not substitute for the dry-run, staging, live, or hosted-CI categories above.
No archive or terminal closure is authorized by this evidence record.

### Shared local checks on the reviewed source

- `python3 -m pytest tests/unit -q`: 995 passed, 2 existing skips; one honeypot thread shutdown warning. The warning was reproduced only when the test fixture closes its listener while a daemon accept thread is running; it was not observed before cleanup. The stale collected-count documentation was corrected before this successful run.
- `bats tests/bats/`: 55 passed.
- `make tf-test`: 79 provider mock tests passed.
- `make snapshot-check`: 102 templates matched.
- `make validate`, actionlint, shellcheck, cargo-deny and Rust 1.88 MSRV check passed. YAML lint has one existing workflow line-length warning.
- Render, AWG version floor, Xray guards, secrets coverage, deploy-profile, example secrets schema and bundle schema checks passed.
- `make check` did not pass: its Docker cloud-init step lost the Colima connection. Per-role Molecule did not run. These checks must be rerun in a working container environment.
