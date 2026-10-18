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
| REQ-NPC-TUN | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include strict capture exclusions and malformed selectors | Passed locally |
| REQ-NPC-NAME | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include lossless IDNA and explicit A-label cases | Passed locally |
| REQ-NPC-RELAY | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include real TCP half-close, bounded buffers and authenticated empty UDP | Passed locally |
| REQ-NPC-RESOLVER | SEC-1792307142612713 | 49 resolver/runtime tests; interrupted apply replay; independent focused review APPROVE | Passed locally |
| REQ-NPC-DISCOVERY | SEC-1792317891777907 | 38 checkout-discovery tests; real large-input, byte-identity, filter-refusal and FIFO deadline cases; actual Make and selected-task commands | Passed locally |
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
- Complete gate on 801eca79 exited 2: 8108 tests and 45 subtests passed;
  228 native cases were deselected by the portable lane. Five cases could not
  find the official ansible-playbook entry point in the private virtualenv.
  Two checkout-discovery cases failed after the owned blocked process tree
  was interrupted. Shell and CLI stages did not run. No full-gate pass is claimed.

## CI integration corrections

Run 39109079489 on aa0c48d744cd7d750ad49916d4792511772e1b75 found three
unit failures. The existing assertions remain active.

- The fixed Terraform output contract now includes the NAT range in all five
  roots; unconstrained roots return an empty string. All three added provider
  mock assertions pass within 25 server cases.
- The split-hop enable guard now follows the sole lifecycle selector. A new
  native case retires the disabled role with an invalid NAT input; Linux CI
  must execute it. The focused contract/lifecycle/NAT suite passes 60 cases.
- Python 3.12.15 changed uppercase sharp-s codec behavior. Lowercase the DNS
  identity before encoding. All 156 client cases pass on both 3.12.13 and
  3.12.15, with no new deployed dependency.

Another 154 Tailnet/bootstrap and AWG provisioning tests pass. The complete
local gate ran with stdin bound to /dev/null. Incremental structured review is clean; security review of the delta is APPROVE.
The replacement CI run and final integrated source proof remain required.

The inherited PR #328 source a14c339ccf8db8bce10bce5da22380a813a41605 has
observed successful main CI run 39106128582. This does not replace the
required acceptance of the current source.

The exact ECH test fixture patch from 7ee95c34de14892d238a2ccc27c9b4189c791c79
is a temporary shared-source dependency for the local Darwin gate. It drains
synthetic ciphertext before emitting JSON and tests input above pipe capacity.
The owning security change retains this source; no alternate implementation is
created. Its final main integration remains required before source closure.

## Checkout metadata deadlock

The complete gate reproduced a workspace-status helper blocked beyond its
30-second Git deadline. Native samples show both Python input and Git output
blocked in writes. The helper invoked check-attr with the real tracked-path
list; no fleet or credential input was used. The primary checked the exact
owned process tree before stopping it. A second blocked helper required the
same cleanup. The resulting failed gate remains failed evidence.

SEC-1792317891777907 owns the minimal metadata transport correction. The
security audit session will reuse this exact source instead of implementing
another workaround. Filter refusal, path byte identity and bounded command
failure remain mandatory.

The correction is source commit 2c48e719f67a832d27445d36ad9ca16f5357471a.
The full discovery module passes 38 cases in 18.63 seconds. The real Make
discovery command completes in 0.239 seconds; selected-task JSON completes in
0.662 seconds. Security review is APPROVE; structured review is clean at 0.98.
All commit hooks pass. A replacement complete gate remains required.

The five transport preflight cases now pass in 4.02 seconds after the official
hash-locked ansible-core 2.21.5 wheel installs its entry point into the private
virtualenv. Dependency checks pass. No production admission code changed for
those environment failures.

## Additional native diagnostic

Run 39109079489 passes both new native NAT cases and the 166-case native suite.
Its later repeated AWG dual-stack goal fails an IPv6 DNS AAAA probe with an
upstream UDP checksum error. The empty-range NAT render is identical to the
baseline after blank-line normalization. No causal production change is
established. An isolated packet experiment will test a specific pinned-runtime
checksum hypothesis; it remains pending and no offload or guard is disabled.
