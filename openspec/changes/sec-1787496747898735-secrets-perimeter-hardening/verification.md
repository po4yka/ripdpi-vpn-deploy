---
task_id: "SEC-1787496747898735"
change: "sec-1787496747898735-secrets-perimeter-hardening"
commit_sha: "bbc346415f412ab49f296db3927ff0fbefdaa8e0"
local: "blocked"
local_evidence: "2026-08-27: Rust debug/release each passed 173 tests, clippy/MSRV/deny passed; make validate and cloud-init schema passed. Full make check found two existing AWG installer fresh-directory failures under umask 077; root-cause correction and a complete rerun are pending."
remote_ci: "blocked"
remote_ci_evidence: "PR #108 is published. Expanded hosted Molecule coverage exposed runtime and scenario defects; final required-check success and main merge are still pending."
dry_run: "blocked"
dry_run_evidence: "Real strict secrets precheck passed, but SSH to all three inventory hosts timed out and Tailscale requires reauthentication. No full fleet playbook dry-run completed."
staging: "not_applicable"
staging_evidence: "no separate staging environment exists; CI molecule convergence and check-mode security-verify cover the controls"
live: "blocked"
live_evidence: "No fleet convergence or live traffic/service acceptance ran: management access is unavailable. Local amd64 systemd containers on this arm64 Mac also fail pidfd_open with ENOSYS before roles execute; hosted amd64 Molecule is the runtime test lane, not live fleet proof."
client: "not_applicable"
client_evidence: "no client emitter changed; vhost headers verified via live curl under live gate"
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
