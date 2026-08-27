---
task_id: SEC-1787496747898735
change: sec-1787496747898735-secrets-perimeter-hardening
commit_sha: bbc346415f412ab49f296db3927ff0fbefdaa8e0
local: blocked
local_evidence: '2026-08-27: 79 focused security/transport regressions passed, 102 snapshots passed, make validate passed. ICMP assertions passed in an extracted local Ansible check-mode fixture. Full make check stopped when Colima disconnected; required Molecule/systemd runtime scenarios did not execute.'
remote_ci: blocked
remote_ci_evidence: No hosted CI run for this implementation SHA; protected-main PR delivery is pending authorization.
dry_run: blocked
dry_run_evidence: Fleet-wide check mode, including secret-render log inspection, has not run; operator access authorization is pending.
staging: not_applicable
staging_evidence: no separate staging environment exists; CI molecule convergence and check-mode security-verify cover the controls
live: blocked
live_evidence: No node convergence, deployed-header curl, NDP smoke, or actual timer firing observed. These remain required.
client: not_applicable
client_evidence: no client emitter changed; vhost headers verified via live curl under live gate
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SECRET-RENDER-SILENT | SEC-1787496118906943 | verbose dry-run capture showing redacted dns-morph render task | pending |
| REQ-ROOT-UNIT-FLOOR | SEC-1787496118906423 | systemd-analyze verify + molecule run of both units | pending |
| REQ-ICMP-SHAPED | SEC-1787496118907048 | rendered ruleset assertion + security-verify check + NDP smoke | pending |
| REQ-TIMER-ONLY-SCHEDULING | SEC-1787496118907149 | list-timers output; absence of cron.daily file post-converge | pending |
| REQ-MANDATORY-REPO-PIN | SEC-1787496118907052 | negative converge with empty pin failing closed | pending |
| REQ-VHOST-HEADER-PARITY | SEC-1787496118906540 | curl -I header diff vs public-site vhost | pending |
| REQ-RATELIMIT-SINGLE-LAYER | SEC-1787496118906790 | inventory of enforcement layers matching synced docs | pending |

## Gates

- Local: molecule per touched role, shellcheck, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: full-inventory `make dry-run` including security-verify in check mode.
- Live: one node re-converged; headers curl-verified; timer observed firing once.

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
