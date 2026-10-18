---
task_id: SEC-1792307003680932
change: network-protocol-correctness
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source-only repair; no private inventory or infrastructure transaction.
staging: not_applicable
staging_evidence: No rollout is requested.
live: not_applicable
live_evidence: No live host or provider acceptance is claimed.
client: not_applicable
client_evidence: Physical Android attribution and runtime kill-switch proof remain outside source acceptance.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NPC-EDGE | SEC-1792307138300077 | 71 UpCloud Terraform tests, 108 network tests, real AWG IPv4/IPv6 and split-hop IPv4 TCP/UDP packets through rendered nftables | Passed locally |
| REQ-NPC-HSTS | SEC-1792307138300077 | Public-site topology matrix in 108 network tests; reviewed nginx snapshot | Passed locally |
| REQ-NPC-CERT | SEC-1792307139966331 | 48 certificate/caller tests and 204 controller/backup tests | Passed locally |
| REQ-NPC-TUN | SEC-1792307141621739 | 153 client boundary tests include strict capture exclusions and malformed selectors | Passed locally |
| REQ-NPC-NAME | SEC-1792307141621739 | 153 client boundary tests include lossless IDNA and explicit A-label cases | Passed locally |
| REQ-NPC-RELAY | SEC-1792307141621739 | 153 client boundary tests include real TCP half-close, bounded buffers and authenticated empty UDP | Passed locally |
| REQ-NPC-RESOLVER | SEC-1792307142612713 | 49 resolver/runtime tests; interrupted apply replay; independent focused review APPROVE | Passed locally |
| REQ-NPC-EVIDENCE | SEC-1792307143659844 | Full gate, source ledger, reviews, coordinated fixes and protected merge | Pending |

## Coordination

PR #328 at a14c339ccf8db8bce10bce5da22380a813a41605 supplies the native
SAN and validity checks. Task SEC-1792306834441683 owns Hysteria redirect and
its transit regression; its accepted merge remains required for the audit ledger.

## Residual risks

Split-hop strict reverse-path filtering and Android package DNS attribution
remain conditional audit risks. Their runtime failure has not been established.
The source change does not claim production networking, browser, or device proof.

## Local evidence detail

- Python 3.12.13 runs the portable tests. The resolver sequence executes
  relocated Ansible tasks against temporary files; service calls are recorded.
- The native NAT probes use Linux Python 3.12.3, nftables 1.0.9 and iproute2
  6.1.0 in isolated network and mount namespaces. The production templates are
  rendered with pinned Ansible. AWG covers both address families; split-hop
  covers IPv4. Both TCP and UDP use original client ports 3074 and 62000.
  A provider filter rejects return ports outside 32768-60999 before guest DNAT.
  The tests also check the actual split-hop nft JSON shape and refused SSH.
- Reviewed template snapshots pass for 164 templates.
- The two inventory Base64 CRLF substitutions reuse PR #329 exactly while
  integration is pending. Their source belongs to that PR.
- Inventory and observability topology tests: 83 passed after reuse of the
  exact PR #329 substitutions.
- Structured review: no accepted actionable findings. Security review: APPROVE.
- The complete local gate is queued behind another active build. Exact-head
  hosted CI and source merge remain pending. No runtime acceptance is claimed.
