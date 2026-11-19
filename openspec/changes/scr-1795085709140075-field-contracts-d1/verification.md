---
task_id: SCR-1795085709140075
change: scr-1795085709140075-field-contracts-d1
commit_sha: e29d801c
local: passed
local_evidence: Independent network-hint review: contract and design updates in a79d6e0d and 9a506f2d pass the local checks at 9a506f2d in the section of that name. Network-source and network-hint amendment: At 57891014 (logs in the session run directory runs-nethint): focused pytest of 14 files (ingest, contract, bundle generation, secrets schema, alert rules with promtool, control-plane and agent render, fleet rotation, acceptance, agent instructions, docs index, governance, sing-box round trip, audit hooks) exit 0, 776 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and observability_agent exit 0; yamllint on the same roles exit 0; `make shellcheck` exit 0; `scripts/check-templates-render.py` exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract golden validates and every report, hint and bundle negative is rejected for its named reason; `./taskctl openspec cli validate --strict` exit 0 for D1 and D2; `./taskctl validate` exit 0. `test_typed_role_guard_capture_times_out_and_reaps_owned_process` failed once inside a long run and passed alone (timing-sensitive, unrelated). `make molecule-test` and `make check` were not run. Second security review fixes at 8ed78023 and 820ffaab pass the local checks in the section of that name at cba6b1e8. At 207bb881, `python3 -m pytest tests/unit/test_bundle_schema.py tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_xhttp_alternate_profiles.py tests/unit/test_docs_index.py tests/unit/test_agent_instructions.py tests/unit/test_client_payload_recipient_boundaries.py tests/unit/test_device_migration_receipt.py tests/unit/test_client_drift.py` exit 0 (460 passed); every contract fixture validated by its validator (6 accepted, 31 negatives rejected); `make snapshot-check` exit 0; `make docs-check` exit 0; `./taskctl openspec cli validate scr-1795085709140075-field-contracts-d1 --strict --no-interactive` exit 0; `./taskctl validate` exit 0. The full `tests/unit` run had 161 failures and 54 errors, all in privileged or host-runtime tests; the same tests fail identically on a clean export of the base revision. `make check` was not run, because its unit stage carries those local host failures.
remote_ci: required
remote_ci_evidence: Not run; no push is authorized. The contract-sync workflow will fail until RIPDPI R2 vendors the new and changed contract files.
dry_run: not_applicable
dry_run_evidence: No deploy controller or rendered deployment input changes.
staging: not_applicable
staging_evidence: Contract-only change; staging proof is owned by D7.
live: not_applicable
live_evidence: Contract-only change; no live system is affected.
client: required
client_evidence: Pending RIPDPI R2, which vendors the schemas and fixtures byte-identically and runs the golden and negative fixtures, including the network-hint contract and the sim golden.
artifact: required
artifact_evidence: Pending the verified merge SHA. Canonical files at e29d801c: contract/client-field-report.schema.json, contract/client-network-hint.schema.json and contract/ripdpi-bundle.schema.json, with the goldens and the report-*, hint-* and neg-* negatives.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REPORT-SHAPE | SCR-1795085965580974 | `test_report_golden_validates_via_cli` and the `report-extra-*` cases of `test_report_negative_fixture_is_rejected_for_its_reason` (root, window, client, network, bucket) | passed (local, 207bb881) |
| REQ-REPORT-BUCKET | SCR-1795085995858987 | `report-failure-without-stage`, `report-success-with-stage`, `report-unknown-failure-stage`, `report-histogram-extra-bound` and `report-histogram-sum-mismatch` rejected for their named reasons | passed (local, 207bb881) |
| REQ-REPORT-PRIVACY | SCR-1795085995858987 | `report-server-ref-ipv4` (203.0.113.7), `report-server-ref-ipv6`, `report-server-ref-hostname` (node.example.org), `report-start-not-hour` (10:15:00Z) and `report-start-seconds` rejected; diagnostics do not echo values | passed (local, 207bb881) |
| REQ-REPORT-MINBUCKET | SCR-1795085995858987 | `report-attempts-below-5` rejected on `minimum` at `/buckets/2/attempts`; suppression rule stated in `docs/reference/ripdpi-bundle.md` | passed (local, 207bb881) |
| REQ-BUNDLE-V3 | SCR-1795086029049140 | `test_v2_golden_rejected_on_schema_version_only`, `neg-schema-version-2`, `neg-field-report-http-endpoint`, `neg-field-report-hint-http-endpoint`, `test_field_report_endpoint_requires_plain_https`, `test_enabled_field_reports_publish_only_the_client_fields`, `test_golden_full_validates_via_cli` | passed (local, 207bb881) |
| REQ-REPORT-NETWORK-SOURCE | SCR-1795103564806941 | `test_report_golden_validates_via_cli[server-hint]` and `[sim]`; `report-missing-source`, `report-unknown-source`, `report-sim-without-operator`, `report-sim-with-asn`, `report-sim-on-wifi`, `report-server-hint-without-asn`, `report-server-hint-with-operator`, `report-none-with-asn` and `report-none-with-operator` rejected for their named reasons | passed (local, network-source amendment) |
| REQ-REPORT-OPERATOR | SCR-1795103564806941 | `report-extra-operator-property`, `report-operator-mcc-two-digits`, `report-operator-mnc-four-digits`, `report-operator-mnc-trailing-newline` and `report-operator-mcc-number` rejected for their named reasons | passed (local, network-source amendment) |
| REQ-NETWORK-HINT | SCR-1795103564806941 | `test_hint_schema_version_pin_and_golden`, `test_every_hint_negative_fixture_has_a_reason`, `test_hint_negative_fixture_is_rejected_for_its_reason` (six `hint-*` fixtures); client fetch rule in `docs/reference/ripdpi-bundle.md` | passed (local, network-source amendment) |
| REQ-BUNDLE-HEALTH-TTL | SCR-1795086060772476 | `contract/ripdpi-bundle.health-expired.json` with `test_expired_health_fixture_is_the_expiry_case` and `test_expired_health_rule_is_documented` | passed (local, 207bb881) |

## Second security review (1a159bc1..0f3b138b)

An independent security review of the whole field-analytics range returned REQUEST CHANGES. The findings that this change owns are fixed below, each in its own commit with a regression test that fails before the fix. Verdict after the fixes: APPROVE for local evidence; staging, remote CI and Molecule stay open as listed above.

- Finding 5, fixed in 8ed78023: `scripts/validate-bundle.py` used the plain Draft 2020-12 validator, so `$` in a bundle pattern also matched before a trailing newline. It now reuses the field-report validator with the ECMA-262 end anchor; `contract/negative/neg-field-report-token-trailing-newline.json` passed before and is rejected after (`test_negative_fixture_is_rejected`).
- Finding 7, fixed in 820ffaab: Draft 2020-12 counts `64500.0` as an integer, so a float ASN passed and became the label `"64500.0"`. The shared validator now admits only a JSON integer for `integer`; `contract/negative/report-asn-float.json` passed before and is rejected after (`test_report_negative_fixture_is_rejected_for_its_reason`). Both new fixtures are client-vendored.

At cba6b1e8 (logs in the session run directory runs-secfix-d7, verify-*.log): focused pytest of 17 files (contract, ingest, rotation, exporters, relay render, alert rules with promtool 3.15.1, observability contract, agent render, retention, secrets schema, audit hooks, agent instructions, governance, docs index, journald, operator) exit 0, 895 passed; `ansible-lint --offline` on subscription-host, observability_control_plane and hysteria exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; every contract fixture validates and every negative fixture is rejected exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1 to D5 and D7; `./taskctl validate` exit 0. Each fix commit carries a regression test that failed on the code before it (red runs in the same directory). `make molecule-test` and `make check` were not run.

## Independent network-hint review (1074de8d..60a05950)

The independent review's findings that touch this contract are recorded here; the code fixes belong to D2 and D5 (see their verification files).

- M2: the accepted risk of fetching the hint outside the tunnel, with the operator mitigation (a separate subscription-only host for `network_hint_endpoint`) and the client mitigation (RIPDPI R3 adds jitter), is in `design.md` (9a506f2d). The server now answers `204` for a request from a fleet node's public address.
- L5, client contract change in `docs/reference/ripdpi-bundle.md` (a79d6e0d): the public report and hint routes answer an unknown cohort token with the vhost's uniform `404`, no longer `401`; any hint answer other than `200` means no hint, and a report answered `404` is discarded until a new bundle. A dataset that fails to load makes the hint route answer `404`. RIPDPI R3 must follow this contract; the client is not implemented yet, so no shipped client depends on `401`.

At 9a506f2d (logs in the session run directory runs-nethint-fix, verify-*.log): focused pytest of 15 files (ingest, alert rules with promtool 3.15.1, peer exporters, bundle schema and generation, acceptance, rotation, observability contract, control-plane and agent render, secrets coverage and schema, agent instructions, governance, docs index) exit 0, 824 passed; `ansible-lint --offline` on subscription-host, observability_control_plane, hysteria and amneziawg exit 0; yamllint on the same roles exit 0; shellcheck exit 0; `check-templates-render.py` exit 0; `check-secrets-coverage.py` exit 0; `make snapshot-check` exit 0; `make docs-check` exit 0; the golden field reports validate exit 0; `./taskctl openspec cli validate --strict` exit 0 for D1, D2 and D5; `./taskctl validate` exit 0. `make molecule-test` and `make check` were not run.

## Re-review of 60a05950..6a03765e

The code fixes are recorded in the D2 verification file. Changes to this contract and design:

- L5, `docs/reference/ripdpi-bundle.md` (b9347724): a method other than the route's own also gets the uniform `404`; `400`, `413` and `429` stay distinguishable, accepted because both paths are published in every bundle.
- N3, `design.md` and `docs/reference/ripdpi-bundle.md` (5a9177eb): the fleet-address `204` covers each inventory host's `vpn_service_address`, any address in the /64 of its `server_ipv6`, and `honeypot_listen_addr`; an exit outside the inventory relies on the client rule. `make docs-check` and OpenSpec strict pass (logs in the session run directory runs-rereview-fix).
