---
task_id: "MON-1791618056169855"
change: "topology-authenticated-probes"
commit_sha: "c4c4d55c55dba02df299c7af349b93fabe841b67"
local: "required"
local_evidence: "native topology 7 passed; watchdog 17 passed; render contracts 31 passed; lifecycle 14 passed; executable coverage 6 passed; cohort smoke 1 passed; 164 snapshots match; full make check retry queued with exact sing-box 1.14.3"
remote_ci: "required"
remote_ci_evidence: "PR 316 exact final source checks running; initial CI exposed caller/fixture and missing-toggle defects fixed by d78e36b5, 5a453b53 and c4c4d55c; no terminal all-green claim"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "exact pinned Xray and Hysteria clients plus real source-built AWG passed isolated native topology cases; existing real Hysteria hopping/upgrade acceptance passed (1 case, 657.31 seconds)"
artifact: "required"
artifact_evidence: "committed native and renderer contracts exercise private configurations and categorical failures; closure remains gated by required validation and AWG prerequisite"
---

# Verification

## Requirement evidence

Source capability under review: `c4c4d55c55dba02df299c7af349b93fabe841b67`.
The source tree at `405f69d9` also passed all seven topology native cases without skips in 140.00 seconds. The later omitted-toggle correction has 35 passing renderer/watchdog cases and unchanged canonical snapshots; its final exact-source hosted native lane remains required. Hysteria hopping evidence was observed on the initial implementation `b961e63620cf1face0e678369e27be88b04b9278`. Subsequent fixes isolate disabled XHTTP render inputs, retain canonical transport defaults throughout watchdog selection/config/credentials/deadlines, and update affected test callers; 86 listener/renderer/SOPS, 33 shape, 22 profile-default and 35 final renderer/watchdog regressions passed. The final three omitted-toggle cases compare actual renders and role lifecycle conditions against canonical defaults; subscription-only suppression remains enforced.
Later task/evidence-only commits do not change that runtime source boundary.

| Requirement | Execution step | Observed evidence | Result |
|---|---|---|---|
| REQ-PROTO-PROBE-TOPOLOGY | MON-1791618060162436 | `test_topology_authenticated_probes.py`, watchdog and smoke regressions cover cohort-only REALITY, XHTTP-only/Hysteria-only verification, separate XHTTP frontend/backend failures and shared owner recovery. Real two-instance AWG encrypted traffic and per-device revocation passed in `make test-topology-authenticated-probes`. | targeted checks passed |
| REQ-PROTO-PROBE-AUTH | MON-1791618061120158 | New native target: 7 passed, no skips. Real pinned Xray/Hysteria deliver controlled requests; wrong UUID/password/SAN/trust and mismatched Salamander fail while direct controls succeed. AWG native binding cases use exact source-built daemons and real encrypted traffic. | targeted checks passed |
| REQ-PROTO-PROBE-OWNERSHIP | MON-1791618061120158 | Watchdog suite: 17 passed. Foreign sockets, shared recovery ownership, durable pre-action budgets, notification/state boundaries and SIGKILL kernel lock release are executable. Actual Hysteria client first delivers traffic, then SIGSTOP forces bounded failure and TERM/KILL cleanup. Lifecycle/state/notification suites: 14 passed. Two-cohort smoke cleanup: 1 passed. | targeted checks passed |
| REQ-PROTO-PROBE-EVIDENCE | MON-1791618062766877 | Native AWG warm-adoption test observes new ELF inode/PID and unit sandbox adoption, then unchanged convergence retains PID. Existing real Hysteria hopping/upgrade acceptance passed: 1 case, 657.31 seconds, with actual multiple-port traffic and unrelated UDP control. Renderer/watchdog contracts: 31 passed; executable CI coverage: 6 passed; snapshots: 164 matched. | native checks passed; full gates pending |

## Remaining gates and dependency

- `build-gate -- make check` completed validation but failed CI parity because the local sing-box was 1.13.16 rather than required 1.14.3. A checksum-verified 1.14.3 binary passed canonical emitter/parser compatibility; a complete retry with that temporary tool path is queued. An earlier attempt failed on a trailing empty line in the moved smoke include; that defect was fixed and the source commit's hooks passed.
- The next full local aggregate reached three provider test groups (69, 50 and 53 passes), then failed Scaleway registry discovery because the selected IPv6 route was unavailable. Exact cached providers passed a checksum-enforced readonly initialization through a temporary filesystem mirror; the complete aggregate retry is queued.
- The generic native lane in the combined local lab failed: 87 passed, 26 failed, 19 setup errors and 6 skipped. The combined lab lacks generic-lane binaries/provider prerequisites; remaining broad-lane failures were not fully diagnosed. No aggregate success is claimed. Its fresh configured exact-source hosted lane must pass; the seven-case topology target and six-case AWG target are separate successful evidence.
- A further complete local aggregate failed in the Docker cloud-init schema fallback because Ubuntu APT endpoints timed out. Host HTTPS to Ubuntu succeeded, while all six tested Ubuntu IPv4 endpoints were unreachable from the default Docker bridge. No TLS or package gate was bypassed. The complete portable unit suite is separately gate-queued.
- Exact-source PR CI must reach a terminal successful state. No queued or running check counts as success.
- The first combined affected-suite run had 134 passes and one watchdog fixture startup race. The corrected watchdog suite passed all 17 cases; the earlier run is not reported as a full affected-suite pass.
- `ANS-1791618048083304` remains doing on the integrated main branch. Its required arm64 emulator/native-core IPv4/IPv6 TCP/UDP/DNS acceptance across MTUs and reconnects is not established by these Linux probe tests. The owner authorized completing this prerequisite in the current session. The canonical dependency remains intact; task closure and promotion must wait for its observed acceptance.
- No real inventory, operator credential, production host, fleet deployment or real notification receipt was exercised. Isolated synthetic native evidence does not establish those outcomes.


## Exact-source hosted native acceptance (2026-10-16)

CI run 38908725450 native runtime integration passed on
`c3b108120d314fb2ce24a05c7eaf41e11a364621`: 138 generic native cases,
2 XHTTP endpoint cases, all 7 topology cases (145.67 seconds) and all 6 AWG
dual-stack cases (90.36 seconds), without selected skips. This supersedes the
missing configured generic-lane proof while preserving the failed local lab
result above. The real warm unit continues to enforce `ProtectHome=yes`; its
fixture now stages exact tools outside the CI source checkout. The complete
workflow and local source/client gates remain pending. The combined local
batch timed out after 3600 seconds waiting for a slot (exit 75) without running
tests, then was requeued through the same gate without a wait timeout.
