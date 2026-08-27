---
task_id: "SEC-1787496747898735"
change: "sec-1787496747898735-secrets-perimeter-hardening"
commit_sha: "984b4528b634b4b48fa74fac0b4cbb22b8b7b887"
local: "passed"
local_evidence: "Full build-gate -- make -j1 check passed under umask 077: 1024 Python tests passed, 1 existing live-scanner placeholder skipped; 55 BATS; 173 Rust release tests; 79 Terraform mocks; 102 snapshots. Release clippy, Rust 1.88 MSRV, cargo deny, Docker cloud-init schema, make validate, lint/render/schema gates passed. Separate Rust debug suite: 173 passed."
remote_ci: "passed"
remote_ci_evidence: "PR #108, exact implementation SHA 984b4528b634b4b48fa74fac0b4cbb22b8b7b887: CI run 33069634871 completed success; 62 successful checks and one neutral Trivy SARIF report, with both image scan jobs successful. All required checks and expanded hosted Molecule scenarios passed. This is PR evidence; protected main merge remains a delivery step."
dry_run: "blocked"
dry_run_evidence: "Real strict secrets precheck passed, but SSH to all three inventory hosts timed out and Tailscale requires reauthentication. No full fleet playbook dry-run completed."
staging: "not_applicable"
staging_evidence: "No separate staging environment is configured; hosted Molecule covers role controls. Required fleet security-verify check-mode acceptance remains blocked under dry_run."
live: "blocked"
live_evidence: "No fleet convergence or live traffic/service acceptance ran: management access is unavailable. Local amd64 systemd containers on this arm64 Mac also fail pidfd_open with ENOSYS before roles execute; hosted amd64 Molecule is the runtime test lane, not live fleet proof."
client: "not_applicable"
client_evidence: "No client emitter changed; required live vhost header curl verification remains blocked under live."
artifact: "not_applicable"
artifact_evidence: "no build artifacts produced by this change"
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

### Final checks on the reviewed implementation

- `build-gate -- make -j1 check` passed under restrictive umask 077: Python 1024 passed, 1 existing unconditional live-scanner placeholder skipped; BATS 55 passed; Rust release 173 passed; Terraform mocks 79 passed; 102 snapshots matched.
- Release clippy, Rust 1.88 locked MSRV, cargo deny, cloud-init schema in Docker, and all render/schema/lint gates passed. `make validate` also passed after the final role edit. Rust debug independently passed 173 tests.
- [Hosted CI run 33069634871](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/33069634871) passed on `984b4528b634b4b48fa74fac0b4cbb22b8b7b887`. PR #108 has 62 successful checks and one neutral Trivy SARIF report; both image scan jobs succeeded. Expanded Molecule scenarios executed on hosted amd64 Linux.
- Earlier umask, role runtime, fixture, and container validation failures are superseded by these successful reruns. Local amd64 systemd Molecule on this arm64 Mac remains unavailable (`pidfd_open` ENOSYS); hosted Molecule is the observed role-runtime evidence, not production evidence.
- Existing cargo-deny duplicate-dependency warnings and one workflow line-length warning remain. The skipped live scanner test is not counted as acceptance.

## Remaining acceptance blockers

Implementation and local/hosted regression gates passed. Archive and terminal closure remain blocked by the dry-run, staging (where required), and live categories above. SSH to all three configured production hosts timed out; this Mac requires Tailscale reauthentication. No production deployment ran.
