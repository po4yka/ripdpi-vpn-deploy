---
task_id: SCR-1795086521848661
change: scr-1795086521848661-bundle-v3-generation-d4
commit_sha: f3ab9ad2
local: passed
local_evidence: Second security review fixes at b94e0398 pass the local checks in the section of that name at cba6b1e8. Implementation at f3ab9ad2. `tests/unit/test_bundle_v3_generation.py` (18 tests) plus the secrets schema and coverage tests exit 0 (176 passed); a focused run of 41 emit, client, recipient, bundle, secrets, audit, docs, governance and CI-selection files has 1009 passed and 16 errors, all in `test_device_lifecycle_probe_native.py`, which downloads the pinned Snell release from the network (environment gap, not a regression); `scripts/validate-secrets.py` and `scripts/check-secrets-coverage.py` exit 0; shellcheck on `scripts/rotate-cohort-token.sh` and `scripts/emit-bundle.sh` exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; `./taskctl openspec cli validate --strict` exit 0. A real sops 3.13.3 run against a throwaway age key generated a token, rotated it twice, kept unrelated keys and printed no token (`d4-real-sops-rotation.log`). `make check` was not run. Logs are in the session run directory runs-d2d4d5 (d4-*.log).
remote_ci: required
remote_ci_evidence: Not run; no push is authorized.
dry_run: required
dry_run_evidence: Not run; a rotation against the operator SOPS file needs explicit authorization.
staging: not_applicable
staging_evidence: Staging proof of the generated bundle is owned by D7.
live: not_applicable
live_evidence: Rolling v3 bundles to production is a separate operator decision.
client: required
client_evidence: Not run; RIPDPI R4 must consume a generated v3 bundle with endpoints and field_report.
artifact: required
artifact_evidence: Not produced; an example bundle at the verified SHA needs real operator secrets and liveness evidence, which this session may not read.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-GEN-V3 | SCR-1795086544436996 | `test_generator_emits_v3_with_health_and_field_report_that_validates` and `test_generator_without_health_input_or_enabled_reports_omits_both_blocks` run `scripts/emit-bundle.sh` and validate the output with `scripts/validate-bundle.py`; the v2 emission path was removed in D1 (`113ae3aa`) | passed (local, f3ab9ad2) |
| REQ-GEN-HEALTH | SCR-1795086565223483 | `test_health_follows_the_liveness_quorum_and_marks_missing_input_unknown` (healthy, down, degraded and unknown), `test_stale_absent_or_unmapped_input_is_unknown`, `test_unproven_cascade_leg_cannot_certify_an_endpoint` | passed (local, f3ab9ad2) |
| REQ-GEN-TTL | SCR-1795086565223483 | `test_health_ttl_above_the_maximum_fails_generation`, `test_generator_refuses_a_ttl_above_the_configured_maximum` | passed (local, f3ab9ad2) |
| REQ-GEN-FIELDREPORT | SCR-1795086581871015 | `test_disabled_field_reports_publish_no_block`, `test_enabled_field_reports_publish_only_the_client_fields`, `test_generator_without_health_input_or_enabled_reports_omits_both_blocks` | passed (local, f3ab9ad2) |
| REQ-GEN-COHORT-ROTATE | SCR-1795086600479731 | `test_rotation_keeps_one_previous_token_and_the_ingest_honours_the_overlap` (three rotations: the ingest accepts the current and previous token and rejects the dropped one; no token in output), `test_rotation_refuses_an_overlap_outside_its_bounds`, real sops run | passed (local, f3ab9ad2) |

## Security review

Scope: `git diff 9586ea31...f3ab9ad2` (generator, health module, rotation script, secrets schema and example, tests, docs). No staged, unstaged or untracked D4 files remained at review time. This checklist was run by the implementing agent; an independent review has not been recorded.

- Secrets in Git: pass. The example holds a placeholder token; test tokens are repeated characters; gitleaks passed in the commit hook.
- Secret schema: pass. `field_report` is declared in `secrets/schema.json` (strict object, token patterns, the previous token and its end instant required together, `endpoint` and `max_reports_per_day` required when `enabled`) and in the example; `scripts/validate-secrets.py` and `scripts/check-secrets-coverage.py` pass.
- Token handling: pass. The rotation script reads the decrypted document only through a pipe, keeps the old token in an unexported shell variable, writes every value through `sops set --value-stdin`, prints only the overlap end, and audits the file name only. Generator and health errors are categorical and carry no value.
- Per-device material: pass. One token per cohort by contract; nothing derives from a device identity.
- Layer boundaries, Terraform, exposure: not touched.
- Bypass markers: pass.

Findings, accepted and documented:

1. LOW: every bundle carries the current token, so a leaked bundle lets its holder skew reports until the next rotation. This is the contract design; D2 keeps an attempts floor and D5 compares with sentinel data.
2. LOW: `previous_cohort_token_valid_until` starts at rotation time. If the subscription host is deployed later than the overlap, clients still on the old token are refused early; the script prints the end instant and the next step.
3. LOW: health input paths come from the operator's own configuration file and are read on the operator machine only.

Verdict: APPROVE with these findings.

## Not done here

- Remote CI: no push is authorized.
- Dry run: a rotation against the operator SOPS file needs authorization.
- Client: RIPDPI R4 consumes a generated v3 bundle.
- Artifact: a generated example bundle at the verified SHA.

## Second security review (1a159bc1..0f3b138b)

An independent security review of the whole field-analytics range returned REQUEST CHANGES. The findings that this change owns are fixed below, each in its own commit with a regression test that fails before the fix. Verdict after the fixes: APPROVE for local evidence; staging, remote CI and Molecule stay open as listed above.

- Finding 11, fixed in b94e0398: `scripts/rotate-cohort-token.sh` replaced a previous token whose overlap was still open. It now refuses while `previous_cohort_token_valid_until` is in the future or unreadable, unless `FORCE=1`; `docs/reference/secrets.md` says so. `test_rotation_refuses_to_drop_a_previous_token_inside_its_overlap` fails before; the three-rotation test passes `FORCE=1` on its third run.
- Finding 5 also hardens this change's output check: `validate-bundle.py` now anchors patterns at end of input (8ed78023).

At cba6b1e8 (logs in the session run directory runs-secfix-d7, verify-*.log): focused pytest of 17 files (contract, ingest, rotation, exporters, relay render, alert rules with promtool 3.15.1, observability contract, agent render, retention, secrets schema, audit hooks, agent instructions, governance, docs index, journald, operator) exit 0, 895 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and hysteria exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract fixture validates and every negative fixture is rejected exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1 to D5 and D7; `./taskctl validate` exit 0. Each fix commit carries a regression test that failed on the code before it (red runs in the same directory). `make molecule-test` and `make check` were not run.
