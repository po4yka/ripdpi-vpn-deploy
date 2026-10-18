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
| REQ-NPC-UDP-CHECKSUM | SEC-1792321613767971 | Baseline/current packet proof; strict source correction, build-identity tests and corrected real-packet regression | Passed corrected isolated proof; integrated CI pending |
| REQ-NPC-EVIDENCE | SEC-1792307143659844 | Full gate, source ledger, reviews, coordinated fixes and protected merge | Pending |

## Coordination

PR #328 at a14c339ccf8db8bce10bce5da22380a813a41605 supplies the native
SAN and validity checks. Task SEC-1792306834441683 supplies Hysteria redirect
and its transit regression through PR #334, merged as
365b08b680963d1bdd8c879b005467e24913b482. Its tested head had all protected
contexts successful. Normal integration 2344d5ed retains both sets of shared
notes and regenerates the task board. All merge hooks pass. The focused NAT,
firewall, Hysteria and resolver integration suite passes 126 cases in 111.71
seconds. This does not replace final integrated complete-gate and CI evidence.

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
baseline after blank-line normalization. The isolated experiment now confirms a pre-existing pinned-runtime defect on
both policies. For each policy all three source-port 37737 datagrams fail and
all three adjacent 37738 controls pass. Decrypted server TUN captures have
checksum 0000, independently computed zero, and CSUMNOTREADY=false; the wire
representation must be ffff. The upstream increments Udp6InCsumErrors once
per failed datagram. Client TUN captures retain the expected partial seed.
Linux 7.0.14-linuxkit arm64, Go 1.27.1, GCC 13.3.0 and nftables 1.0.9 are
recorded with source and artifact digests. This establishes the runtime defect,
but the original CI source port was not captured, so exact CI attribution
remains unproved. No offload, checksum validation or packet guard is disabled.

The correction now has 75 passing source-admission, native-build identity and
source-candidate cases, plus 74 passing role, consumer and lifecycle contracts.
The strict filesystem regressions first exposed writable-file and directory
admission gaps in the new helper; these were corrected without relaxing the
receipt authority. A separate native-consumer rerun passes 28 cases after the
Go test asset and all three overlay invocations are present. The corrected
exact-pin Go and packet evidence below completes that isolated proof.

The earlier exact head 9dcf9329508c006f7fbd9fe574bd3a0002040aa9 completes CI
run 39118640694 with 98 successful contexts and one neutral context. It predates
the checksum correction and does not certify that correction or final source.

The current source correction passes independent security review (APPROVE) and
structured review with no accepted P0 findings, confidence 0.98. The runner
collection/selection suite passes 21 cases. The actual baseline and candidate
Git trees both pass strict application, unchanged repeated application and
postimage verification; no compiler or native acceptance is claimed by that
source-admission check.

## Offline sentinel and diagnostic integration

A bounded builder inventory covers the server role and all four other source
builders in scripts, Ansible, workflows and integration fixtures. The offline
sentinel installer was an additional uncorrected path. Its response also omitted
the input map already required by the caller. That path now uses the same source
correction and immutable input identity. Both standalone readers verify that
identity through the trusted installed helper and keep their strict input schema.

The installer and role suite passes 79 cases in 11.53 seconds; focused
ansible-lint passes. The two complete reader modules pass 236 cases in 48.92
seconds. Independent focused security reviews approve both changes. The native
publication fixture now passes its actual acquired Go directory to configure;
three portable renderer/publication-input cases pass in 3.05 seconds.

The exact code-only diagnostic patch af31772dd017fa15b35b7e386fa125693075ea3b
belongs to the coordinated security session. It preserves packet assertions,
retries and deadlines while publishing only a strict categorical failed-probe
summary. The integrated runner keeps this change and the checksum suite/engine
identity additions. The combined diagnostic and publication-input suite passes
84 cases with fail-on-skip in 4.31 seconds. The owning independent privacy and
structured P0-P2 reviews approve the diagnostic patch. Historical CI failure
attribution remains unproved; the new summary improves the next exact-source run.

## Native host ownership boundary

The checksum helper rejects the runner-owned checkout when the native host
consumer switches to root. This is a deterministic source admission conflict,
not a reproduced packet failure. CI now copies the completed public checkout
and artifacts into an owned directory under /opt. Root tests use that copy;
the original checkout and the strict source owner policy remain intact.
The staging regressions execute the actual shell, preserve source inodes and
symlinks, remove a failed copy and refuse cleanup outside the owned directory.

The executable coverage and tooling cache modules pass 13 cases. The complete
transport semantics module passes 70 cases after its build ordering assertion
includes correction, checksum tests, forced build and publication. Actionlint,
offline Zizmor, focused Ruff and diff whitespace checks pass. Full native host
execution remains a required exact-head CI gate.

## Corrected exact-pin Go and packet proof

The isolated Linux experiment exits zero for both public source commits:
2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf and
b5928efb6ca19f0153958460c3d141f04abc5c2e. Each baseline fails exactly the
eight expected computed-zero UDP leaves; each corrected tree passes all 28
leaves with no skips. Each tree then passes the production overlay check, a
forced build and strict immutable publication under correction digest
94a67434677bec1a122fd0f415f9b86a3382725ded84e6a5fdf09fe02c324987.
The core correction inputs match source commit 85149fa4; the later offline
producer and root CI staging remain covered by their separate regressions.

The experiment selects each published corrected binary explicitly. Each pin
passes six UDP6 probes through each of the two recorded baseline/current NAT
policies: 24 replies in total. Server TUN AUXDATA has six complete requests
per pin/policy, ffff for the zero-producing tuple and fffe for its adjacent
control, CSUMNOTREADY=false and valid independently computed checksums. All
upstream, server and client UDP6 checksum error deltas remain zero. The payload
is a DNS-shaped query and the responder echoes it. This proves UDP transport;
the new CI regression separately requires actual AAAA DNS answers.

The baseline-pin binary SHA256 is
948bafa2f849ab8b3ee4eee6c3bdd7e79bbaef57cab4367f643a47318a5578a5;
the candidate-pin binary SHA256 is
8b4adcc31e1a1789c256a936fac50c36e3e1fc337be602e29b3d9aecda7010f9.
The retained artifact manifest SHA256 is
1b5d2687c74cf433053c4a873a8a8aadd64e90a92fba18e74fbf7d04c1b38ce0.
The experiment uses Linux 7.0.14-linuxkit arm64, pinned Go 1.27.1 and nftables
1.0.9, with two CPUs and 2 GiB RAM. Its exact owned container is removed after
the proof; packet captures and public provenance remain retained. The earlier
attempt failed the copied-file owner guard after its Go check and is not a
packet pass. The successful attempt fixes only ownership of its copied public
inputs. No source owner check, offload or packet guard is relaxed.

Independent review approves the root CI staging delta; its actual-shell
regressions pass. The complete follow-up structured review is clean at 0.97,
and all hooks pass on 65f4c365. Final integrated full-gate and exact-head CI
evidence remain required before source merge.
