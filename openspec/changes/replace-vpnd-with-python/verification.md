---
task_id: VPD-1791615284178957
change: replace-vpnd-with-python
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source/package migration preserves Make deployment targets and controller inputs; local subprocess regression tests exercise CLI orchestration without fleet configuration.
staging: not_applicable
staging_evidence: No rendered server configuration or protocol/runtime implementation changes; four-platform installed-artifact tests are required instead.
live: not_applicable
live_evidence: No production deployment or provider mutation is part of this task.
client: not_applicable
client_evidence: Client bundle and QR payload contracts are checked locally; authenticated VPN traffic and device acceptance are outside this unchanged protocol scope.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

All entries below are planned checks, not observed implementation results.
Populate exact source SHA, command outputs, test-transfer results and hosted
run URLs only after execution. No checkbox completion is implied by this file.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PYCLI-SURFACE | VPD-1791615721526525 | Full command/flag/default/env/parser rejection matrix through both entry points | required |
| REQ-PYCLI-PIPELINES | VPD-1791615723154686 | Positive/failure local Make transcripts, exact alias limits and Terraform wrapper tests | required |
| REQ-PYCLI-STATE | VPD-1791615722328162 | Registry TOML round-trip/private atomic save and context/version fixtures; update cases in VPD-1791615724808852 | required |
| REQ-PYCLI-ARTIFACTS | VPD-1791615723996375 | Recipient links/HTML/SVG/private outputs; complete doctor/docs tests in VPD-1791615724808852 | required |
| REQ-PYSAFE-EXPLAIN | VPD-1791615723154686 | All-command explain sentinels, host state byte comparison, unresolved inventory and outside-checkout cases | required |
| REQ-PYSAFE-PROCESSES | VPD-1791615722328162 | Real owned-descendant cancellation/reaping, foreground safety, dual-stream/error and redaction tests | required |
| REQ-PYSAFE-CLEANUP | VPD-1791615723154686 | Success/dry-run/middle failure/cleanup failure combinations preserve error precedence | required |
| REQ-PYSAFE-TRANSFER | VPD-1791615722328162 | Complete existing security requirement cases listed below and synthetic SOPS/Make boundary checks | required |
| REQ-PYMATRIX-SCHEMA | VPD-1791615725580652 | Inherited matrix/analysis cases and unchanged schema-3 report body | required |
| REQ-PYMATRIX-SCHEDULE | VPD-1791615725580652 | Real concurrent cells, monotonic/time bounds, overruns, ordering and process cleanup | required |
| REQ-PYMATRIX-DURABILITY | VPD-1791615725580652 | Actual local SIGINT/SIGTERM runs preserve private partial JSON/JSONL with 130/143 exits | required |
| REQ-PYDELIVERY-INSTALL | VPD-1791615726382311 | Four-platform wheel/resource/offline installation and failed upgrade tests with Rust unavailable | required |
| REQ-PYDELIVERY-TESTS | VPD-1791615727227192 | Complete source-function/assertion/parameter/property/seed/snapshot-to-passed-pytest manifest; zero omissions/skips | required |
| REQ-PYDELIVERY-INTEGRITY | VPD-1791615726382311 | Version/tag, hashes, provenance, packaged dependencies/SBOM and reproducible artifact gates | required |
| REQ-PYDELIVERY-RETIRE | VPD-1791615728004540 | Active consumer inventory and full Make/package CI with Cargo/rustc absent; historical/local files preserved | required |
| REQ-PYDELIVERY-ROLLBACK | VPD-1791615726382311 | Corrupt/interrupted install keeps previous complete version and byte-identical operator state | required |
| REQ-MANPAGE-SYNC | VPD-1791615724808852 | Parser-derived root/subcommand man pages and bash/zsh/fish/powershell/pwsh completion coverage | required |
| REQ-SHARE-BUNDLE-PERMS | VPD-1791615723996375 | Unique temp, fsync/rename, 0600/0700, unrelated-temp preservation and write-failure tests | required |

## Preserved main-spec regression obligations

These unchanged requirements are covered by REQ-PYSAFE-TRANSFER and the
command/artifact transfer requirements above; they are not new delta IDs.

| Existing requirement | Execution step | Planned evidence | Result |
|---|---|---|---|
| `REQ-MAKE-KV-CHARSET` | VPD-1791615722328162 | Baseline per-key positive/metacharacter/path/IP rejection tests, no spawn on refusal | required |
| `REQ-SECRETS-PATH-AUTHORITY` | VPD-1791615722328162 | Explicit common SECRETS_FILE through every consumer and no duplicate decrypt/fallback | required |
| `REQ-SECRETS-REDACTION-COVERAGE` | VPD-1791615724808852 | Resolved-path generated properties plus stdout/stderr/archive/prompt/clipboard assertions | required |
| `REQ-SECRETS-HARDEN-GATE` | VPD-1791615722328162 | Held-descriptor owner/type/mode, symlink/FIFO, read-only input, missing output and failed hardening | required |
| `REQ-SHARE-TOKEN-VALIDITY` | VPD-1791615723996375 | Empty/invalid token refusal from stdin and file, no generated outputs | required |
| `REQ-SHARE-HOST-RESOLUTION` | VPD-1791615723996375 | Missing-host refusal and configured subscription port/deep-link success | required |
| `REQ-JSON-FLAG-HONESTY` | VPD-1791615721526525 | Structured-output scopes and unsupported/duplicate/global JSON rejection | required |
| `REQ-CLIP-REQUIRES-AI` | VPD-1791615721526525 | Parse-time --clip dependency retained, clipboard behavior in VPD-1791615724808852 | required |
| `REQ-DOCTOR-RESILIENCE` | VPD-1791615724808852 | Failed diagnostic keeps remaining real local outputs/stderr and final nonzero status | required |

## Implementation acceptance gates

1. Refresh `test-inventory.md` against the chosen implementation baseline and
   establish a checked transfer manifest with actual assertions and pytest
   node IDs, not file-level equivalence. Preserve added upstream tests too.
2. Execute full `make vpnd-test vpnd-lint vpnd-parity-check`, generated
   properties/regression seeds and `make vpnd-mutants`. Mutation tooling or
   baseline failures remain failures; no empty run can satisfy the gate.
3. Execute `make vpnd-package-check vpnd-dependency-check` on all four supported
   surfaces. Compare two builds from identical source/locks and verify final
   artifact bytes, dependency closure, version, resources and install recovery.
4. Execute `build-gate -- make check` and `make task-check` on the exact source;
   obtain independent security review before retirement acceptance.
5. Record terminal successful protected-main required checks for the exact
   implementation SHA, including installed-artifact/platform checks. If push
   or publication is not authorized, leave remote_ci required and task open.

## Planning evidence

The plan was authored against baseline
`5365cbd4b33dff5b3d0be0e1f8c5cb2c9d17ac50`. Static discovery enumerated 206 Rust
test functions and ten direct Python consumer suites. No Rust/Python application
tests, builds, provider operations or installations were performed for migration
acceptance. Planning validation results are recorded after the artifact set is
complete; they cannot change the required implementation evidence states above.

Observed on 2026-10-10:

- `./taskctl openspec cli validate replace-vpnd-with-python --strict --json`:
  valid, zero issues.
- `./taskctl generate-board` and `./taskctl validate`: 17 tasks and 55 steps
  valid, migration progress 0/9.
- `env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make task-check`:
  passed with the same 17-task/55-step contract result.
- OpenSpec status reports proposal, specs, design, tasks and verification
  present and planning complete. Implementation acceptance remains required.
