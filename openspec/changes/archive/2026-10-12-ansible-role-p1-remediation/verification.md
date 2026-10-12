---
task_id: SEC-1791545689674403
change: ansible-role-p1-remediation
commit_sha: "cf01f94a640913412f3316b5cb288881639712ce"
local: passed
local_evidence: Full build-gated make check passed with 5599 Python tests, 22 subtests, 56 Bats tests and 205 Rust release tests; final make validate and 19 watchdog fixture regressions passed. Native owned-VM LoadCredential delivery verified authorization, title and body with the unchanged sender.
remote_ci: "passed"
remote_ci_evidence: "Protected-main CI run 38134843683 completed successfully on exact integrated source cf01f94a640913412f3316b5cb288881639712ce; all jobs succeeded, including portable, native, role, failure and full-stack checks. Scorecard, CodeQL and release-please completed successfully on the same source."
dry_run: not_applicable
dry_run_evidence: Source remediation only; no real inventory or SSH controller mutation.
staging: not_applicable
staging_evidence: This PR does not own a provider rollout or live notification.
live: not_applicable
live_evidence: Production deployment is outside the requested source PR.
client: not_applicable
client_evidence: Local transport/runtime regressions are not external client acceptance.
artifact: passed
artifact_evidence: PR 282 contains the reviewed source and regressions; independent host and receiver reviewers approve the final runtime changes and scoped fixture prerequisite. Review status preserves separate source-PR and deployment acceptance.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-P1-XRAY | SEC-1791545814181293 | Safe log setup, actual Ansible normal/check argv, rotation/geodata regressions and native Xray Molecule | passed |
| REQ-P1-SUBSCRIPTION | SEC-1791545814181293 | Missing-state restart, verbose bearer redaction, explicit 0600 authority under umask 022 and native subscription Molecule | passed |
| REQ-P1-BACKUP | SEC-1791545814181293 | 18 real local restic profile/input regressions plus native backup Molecule | passed |
| REQ-P1-RECEIVER | SEC-1791545814693187 | Real loopback TLS admission/deadline and durable generation/replay rollback regressions; 128 receiver/pipeline/collector tests | passed |
| REQ-P1-WATCHDOG | SEC-1791545815210908 | Stalled destination, process metadata privacy, native loaded-credential delivery and canonical Debian failed-probe alert capture | passed |
| REQ-P1-EXISTING | SEC-1791545815774612 | Existing resolver and isolated collector activation regressions on current main | passed |
| REQ-P1-XRAY | SEC-1791545816326788 | Full local gates and independent security review | passed |
| REQ-P1-SUBSCRIPTION | SEC-1791545816326788 | Exact-source CI, CodeQL, Markdown and instruction workflows all completed successfully | passed |

## Scope and integration boundaries

- Nine audit paths required implementation; resolver ownership and collector CRL/TLS activation were already repaired on the selected main revision and verified rather than duplicated.
- The receiver remains retained source, not an activated monitoring topology. Schema-1/unbound private state requires explicit owner-authorized retirement; no automatic migration or replay-counter weakening is provided.
- Xray rotation and geodata activation deliberately use a controlled active-service restart, with a brief interruption to existing connections.
- The Docker fixture's private runtime mount prevented systemd credential publication from its helper namespace. Both owned-container scenarios now inspect and prepare shared runtime propagation before convergence; production units, image pins, credential guards and actual capture assertions stay intact.
- Local emulated Molecule service activation was unavailable; direct native owned-VM delivery and exact-source Debian CI supply the separately named runtime proof. Registry download failures are infrastructure retrieval failures, not role convergence evidence.
- No production, provider, SSH inventory, real secret, authenticated external-client or human-receipt action is claimed.

## Closure reconciliation (2026-10-11)

The preceding sections retain their historical source and environment boundaries. The earlier verification SHA was `2c3a311d256ae95faea8bf8049145473886b32d4`. The accepted integrated source for this closure is `cf01f94a640913412f3316b5cb288881639712ce`; protected-main CI run `38134843683` completed with every job successful. This supersedes earlier pending PR/hosted-check observations without claiming a new deployment. Runtime and source files are unchanged by the closure increment.
