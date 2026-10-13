---
task_id: ANS-1791617913525586
change: runtime-acceptance-transaction
commit_sha: 8e58941a16f2784599fd5cc89e8ada62231966d3
local: passed
local_evidence: Frozen source 8e58941a passed the complete build-gated make -j4 check with 6714 portable tests, 22 subtests, 57 Bats cases, 303 CLI tests, 215 Terraform cases, 59 policy tests, 163 snapshots and all validation, lint and parity checks. Focused queue and private validation-unit regressions and independent review passed.
remote_ci: passed
remote_ci_evidence: Frozen source 8e58941a completed 93 successful checks and one neutral optional scan, with no failed or pending results. Native transport acceptance passed all four complete cases in 1905.24 seconds without skips; native runtime, sender normal and failure/recovery, full-stack, contract-sync and all required contexts passed. The separate derived CodeQL result is successful.
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is included.
staging: not_applicable
staging_evidence: Isolated native source acceptance does not establish an external staging rollout.
live: not_applicable
live_evidence: No production deployment or real notification is authorized or claimed.
client: passed
client_evidence: Pinned native Xray and Hysteria clients completed actual protocol forwarding to the owned HTTPS canary after adoption, retry, compensation and process-death recovery. This is isolated client acceptance, not physical-device or live-fleet evidence.
artifact: passed
artifact_evidence: Rendered snapshots, task and OpenSpec contracts passed at the frozen source. Native cases verify exact executable, configuration, private parameters, TLS and asset identities, retained receipts and validation-lease cleanup. Diagnostics remain categorical and redacted.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RTA-CANDIDATE | ANS-1791617918944560 | Portable candidate authority regressions and complete native Xray/Hysteria cases cover verified acquisition followed by parser, asset, TLS, credential and sandbox refusals. | passed |
| REQ-PROTO-RTA-ADOPTION | ANS-1791617919627692 | Complete native upgrades, occupied socket and active-but-broken forwarding cases require the exact loaded executable and an actual client HTTPS response. Unchanged retries retain accepted identity. | passed |
| REQ-PROTO-RTA-RECOVERY | ANS-1791617918944560 | Real publisher SIGKILL phases, first-adoption recovery, retirement compensation, operator rollback, validation-lease SIGKILL cleanup and receipt/previous-selector identity regressions passed. | passed |
| REQ-PROTO-RTA-AUTHORITY | ANS-1791617918944560 | No-follow, private storage, foreign journal, hardlink, lock and privacy regressions passed; native normal/check-mode cases passed. Hysteria validation units are created and claimed as root-owned 0600; recorded public units refuse before cleanup. | passed |
| REQ-PROTO-RTA-QUEUE | ANS-1791866736401446 | Bounded private snapshot, in-place compensation preserving the queue root, interruption recovery and exact historical sample delivery passed in the real pinned sender scenario at the frozen source. | passed |

## Source and isolated native acceptance

- Exact-source hosted acceptance is complete at `8e58941a16f2784599fd5cc89e8ada62231966d3`. Both native lanes, sender lifecycle scenarios and the required aggregate passed. Native transport acceptance ran all four selected cases without skips.
- Queue admission retains existing ownership, mount, link, count and physical byte limits. Canonical bounded native atomic staging files are accepted. Active-writer identity changes retry only within the existing readiness deadline; quiescent capture remains strict. Focused queue regressions passed under umask 077, including successful preservation and invalid name, counter, size and foreign-authority failures.
- Independent specification and standards/security review approved the source and follow-up fixes without actionable P0-P2 findings. The 39 CodeQL file-descriptor warnings were reviewed: borrowed transaction handles and immediately ExitStack-registered ancestor handles retain explicit context-managed ownership. No confirmed descriptor leak was found. The security finding for a public ephemeral validation unit was fixed and the final derived check succeeded.
- No local enabled-sender Molecule pass is claimed. Earlier local emulation or image-download attempts failed before final acceptance; the positive sender proof comes from the completed exact-source hosted scenario. No assertion, retry bound, native forwarding requirement or quality gate was weakened.

## Local environment

The full gate ran through mise and the machine-wide build gate. Terraform used a temporary supported filesystem mirror of installed providers with lockfile=readonly and unchanged tracked locks. Existing native SOPS 3.13.2 and age 1.3.1 were placed ahead of inactive shims inside the mise environment; hosted CI uses SOPS 3.13.3. No global trust, tool configuration or validation gate was changed. Earlier network or shim failures are not passing runs.

## Acceptance limits

Source checks and disposable native clients do not establish provider, staging, live-fleet, physical-device or human notification acceptance. The measured late-history resource-admission work remains open under the separate monitoring rollout contract. No deployment or real Telegram message was sent.
