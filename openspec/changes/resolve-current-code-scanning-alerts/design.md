## Context

GitHub reports eight open findings on `main` at
`bb889ed478d858e3606f60c8041e3c0d72bd8795`: CodeQL alerts 424 and 511–513
and Scorecard alerts 341–344. The Python findings are confined to existing
validation and cleanup paths. The Scorecard findings are caused by
`packages: write` and `security-events: write` at the top level of both
Molecule image publishing workflows.

## Goals / Non-Goals

- Goal: remove all eight causes in source without dismissals or scanner changes.
- Goal: preserve the exact typed failures, AWG validation side effect, image
  publication, Trivy failure policy, and SARIF upload.
- Goal: make future jobs in the two affected workflows read-only by default.
- Non-goal: change Tailnet promotion state, Terraform inputs, probe verdicts,
  image contents, action pins, or any secret and deployment contract.
- Non-goal: remediate previously dismissed findings outside alerts 341–344,
  424, and 511–513.

## Decisions

- Initialize cleanup descriptors to `None` before the guarded open and replace
  each `except (...): pass` with an `if fd is not None` cleanup expressed via
  `contextlib.suppress(OSError)`. This preserves best-effort cleanup while
  removing the implicit `UnboundLocalError` branch and making the ignored close
  error intentional. Logging was rejected because paths and exception strings
  add no recovery value after the canonical invalid-snapshot result is fixed.
- Keep each descriptor's existing ownership and close point. Do not introduce a
  shared descriptor abstraction or change successful-path reads and digests.
- Invoke `awg_probe_url(config)` without assigning its return value. The call is
  required for schema and endpoint validation; removing the call would weaken
  the probe, while renaming the variable would retain dead state.
- Change the top-level permissions of both affected workflows to
  `contents: read`. Add `contents: read`, `packages: write`, and
  `security-events: write` to the existing `publish` job because a job-level
  mapping replaces inherited permissions and checkout still needs repository
  contents. Splitting build and scan into separate jobs was rejected because it
  would add artifact/digest handoff complexity without reducing authority for
  the only job in either workflow.
- Add focused tests beside the existing Tailnet promotion and liveness tests,
  plus one YAML contract test for both publication workflows. The workflow test
  asserts a read-only top level, the exact publish-job permission map, and no
  second job inheriting write access.

## Contracts and ownership

- `scripts/tailnet-network-promotion.py` owns safe snapshot file access and the
  canonical `terraform-snapshot-invalid` failure category.
- `scripts/vpn-protocol-liveness.py` owns AWG configuration validation and probe
  verdicts; `awg_probe_url` remains the validation boundary.
- `.github/workflows/publish-molecule-debian13.yml` and
  `.github/workflows/publish-molecule-ubuntu2404.yml` own package publication,
  Trivy execution, and SARIF upload. Their trigger, action pins, image tags,
  scanner policy, and outputs stay unchanged.
- Tests under `tests/unit/` own local compatibility evidence. Hosted CodeQL and
  Scorecard own final alert-closure evidence for the exact pushed SHA.
- No Terraform root, Ansible role, cloud-init input, SOPS document, public CLI,
  network listener, or live host is changed or contacted.

## Risks / Trade-offs

- A descriptor-close failure could be hidden → it occurs only while returning a
  preselected canonical validation failure; tests inject both pre-open and
  close failures and assert the canonical result remains stable.
- Removing `parsed` could accidentally remove validation → retain the function
  call and add a focused test proving invalid AWG configuration still fails
  before namespace mutation.
- Moving permissions could make checkout, GHCR publication, or SARIF upload
  unauthorized → include all three exact job permissions, run actionlint and
  zizmor locally, and require the hosted publication workflow on an authorized
  revision before claiming runtime proof.
- Static tests cannot prove GitHub closes alerts → query alerts 341–344, 424,
  and 511–513 after hosted analysis of the exact implementation SHA; do not
  dismiss or suppress any finding.

## Migration Plan

1. Add failing focused tests for descriptor cleanup, AWG validation, and both
   workflow permission maps.
2. Apply the minimal Python and workflow changes, then run the focused tests,
   Python formatting/static checks, actionlint, zizmor, `make ci-fast`, and
   `make validate` through repository-supported entry points.
3. Review the exact diff for unchanged triggers, image publication steps,
   scanner policy, typed Python failures, and secret boundaries.
4. After separately authorized delivery, require successful hosted CodeQL and
   Scorecard analysis on the exact SHA and verify all eight alert states are
   `fixed`. Publication success is separate hosted evidence and is not inferred
   from YAML parsing.
5. Rollback is a focused revert of the Python and workflow changes. Because it
   would reopen the findings, rollback is an emergency compatibility action,
   not an acceptable completed state.
