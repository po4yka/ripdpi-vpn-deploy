---
task_id: SEC-1792307003680932
change: network-protocol-correctness
commit_sha: bc849f60a7422682c8f21826807ceee792ab9953
local: passed
local_evidence: Complete make check on 69ba5de4, tree 254121d7, passed with 8660 portable cases, 45 subtests, 65 BATS and 322 vpnd tests; earlier source evidence remains below.
remote_ci: passed
remote_ci_evidence: Historical main f4e094c7 CI 39150921761 failed. Corrective PR 338 source 69ba5de4 passes CI 39210543551 and four companion workflows. Protected merge bc849f60 has the exact tested tree; its own CI 39216524425 attempt 1 completes successfully with all 92 jobs, all nine required checks and all five workflows successful. Its 45 actual canonical cases pass.
dry_run: not_applicable
dry_run_evidence: Source-only repair; no private inventory or infrastructure transaction.
staging: not_applicable
staging_evidence: No rollout is requested.
live: not_applicable
live_evidence: No live host or provider acceptance is claimed.
client: not_applicable
client_evidence: Physical Android attribution and runtime kill-switch proof remain outside source acceptance.
artifact: passed
artifact_evidence: Source 69ba5de4 passes 45 canonical cases, complete local gate and hosted CI. Actual main bc849f60 artifacts 12171151026, 12171516343 and 12170944370 pass all 45 cases with exact source, successful cleanup and matching engine identity; complete main CI 39216524425 passes. Historical failures and exact-pin digests remain below.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NPC-EDGE | SEC-1792307138300077 | 71 UpCloud Terraform tests, 108 network tests, real AWG IPv4/IPv6 and split-hop IPv4 TCP/UDP packets through rendered nftables; scope: Passed locally | passed |
| REQ-NPC-HSTS | SEC-1792307138300077 | Public-site topology matrix in 108 network tests; reviewed nginx snapshot; scope: Passed locally | passed |
| REQ-NPC-CERT | SEC-1792307139966331 | 48 certificate/caller tests and 204 controller/backup tests; scope: Passed locally | passed |
| REQ-NPC-TUN | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include strict capture exclusions and malformed selectors; scope: Passed locally | passed |
| REQ-NPC-NAME | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include lossless IDNA and explicit A-label cases; scope: Passed locally | passed |
| REQ-NPC-RELAY | SEC-1792307141621739 | 156 client boundary tests on Python 3.12.13 and 3.12.15 include real TCP half-close, bounded buffers and authenticated empty UDP; scope: Passed locally | passed |
| REQ-NPC-RESOLVER | SEC-1792307142612713 | 49 resolver/runtime tests; interrupted apply replay; independent focused review APPROVE; scope: Passed locally | passed |
| REQ-NPC-DISCOVERY | SEC-1792317891777907 | 38 checkout-discovery tests; real large-input, byte-identity, filter-refusal and FIFO deadline cases; actual Make and selected-task commands; scope: Passed locally | passed |
| REQ-NPC-UDP-CHECKSUM | SEC-1792321613767971 | Baseline/current packet proof; strict source correction, build-identity tests and corrected real-packet regression; scope: Passed isolated proof, source PR CI and actual main bc849f60 CI 39216524425 | passed |
| REQ-NPC-SOCKS-READINESS | SEC-1792307143659844 | `test_native_socks_readiness.py` and `test_four_transport_runner.py`: real TCP fragmented 05/00 replies, EOF/version/method/deadline refusals and strict failed-case diagnostics; 148 focused cases passed, followed by the exact-tree complete local gate and actual main bc849f60 CI 39216524425 | passed |
| REQ-NPC-EVIDENCE | SEC-1792307143659844 | Complete local gate, final integration, protected PRs 333 and 338, and exact merged-source main CI below; scope: Source acceptance passed on actual main bc849f60 | passed |

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

## Native SOCKS readiness correction

The former readiness helper treated TCP as a message transport. A real local
socket test accepts a valid two-byte SOCKS5 reply in one write, but refuses the same
reply when the second byte arrives 100 milliseconds later. The regression is
red before the correction. Local correction ef911bd4 accumulates exactly two
bytes within the existing ten-second deadline and retains fail-closed EOF,
version and method checks. PR #331 retains this source as 49ca2ace. Separate
corrective PR #338 integrates the original correction and its explicit error
return as bc849f60 on f4e094c7. Its own complete main CI passes. The focused readiness and runner
modules pass 148 cases in 15.71 seconds. Focused Ruff, compilation and
whitespace checks pass. All normal commit hooks pass.

Independent protocol and privacy review approves the change. Only failed
hopping cases can publish the strict five-field categorical readiness summary;
addresses, unit names and raw process output are excluded. Original traffic,
firewall and source-identity assertions remain active. This is a confirmed
readiness defect, but it is not the established cause of the historical main
CI failure. Corrective integrated PR CI and actual-main CI pass on their exact sources.

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
- The two inventory Base64 CRLF substitutions reuse accepted PR #329 exactly.
  Their source belongs to that PR.
- Inventory and observability topology tests: 83 passed after reuse of the
  exact PR #329 substitutions.
- Structured review: no accepted actionable findings. Security review: APPROVE.
- Complete gate on 801eca79 exited 2: 8108 tests and 45 subtests passed;
  228 native cases were deselected by the portable lane. Five cases could not
  find the official ansible-playbook entry point in the private virtualenv.
  Two checkout-discovery cases failed after the owned blocked process tree
  was interrupted. Shell and CLI stages did not run. This attempt did not pass the complete gate.

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
The final integrated source evidence is recorded below.

The inherited PR #328 source a14c339ccf8db8bce10bce5da22380a813a41605 has
observed successful main CI run 39106128582. This does not replace the
final exact-source acceptance recorded below.

The exact ECH test fixture patch from 7ee95c34de14892d238a2ccc27c9b4189c791c79
was reused for the local Darwin gate. It drains
synthetic ciphertext before emitting JSON and tests input above pipe capacity.
Accepted PR #332 retains this source; no alternate implementation is created.
The final integrated evidence below includes that accepted source.

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
All commit hooks pass. The later complete gate is recorded below.

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
execution is covered by the later exact-source CI results below.

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
The observed artifact manifest SHA256 is
1b5d2687c74cf433053c4a873a8a8aadd64e90a92fba18e74fbf7d04c1b38ce0.
The experiment uses Linux 7.0.14-linuxkit arm64, pinned Go 1.27.1 and nftables
1.0.9, with two CPUs and 2 GiB RAM. Its exact owned container is removed after
the proof. The original local packet captures and manifest files are unavailable
after the interruption; their observed digests and results remain recorded
here. The earlier
attempt failed the copied-file owner guard after its Go check and is not a
packet pass. The successful attempt fixes only ownership of its copied public
inputs. No source owner check, offload or packet guard is relaxed.

Independent review approves the root CI staging delta; its actual-shell
regressions pass. The complete follow-up structured review is clean at 0.97,
and all hooks pass on 65f4c365. The final integrated gate and exact-head CI results are recorded below.

## Source checks and main acceptance

Evidence applies to each named source and environment. Earlier failed and
cancelled attempts remain historical failures, not acceptance of a later tree.

| Source | Observed evidence | Scope |
|---|---|---|
| 30ed3d8d, tree b045ed8b | Complete local make check exits zero: 8396 portable tests plus 45 subtests, 65 BATS cases, 322 vpnd tests, all lint and transfer checks; ci-fast OK | Frozen production correction source; 230 native cases are deselected by the portable lane |
| d3263f51, tree 0d74578c | CI 39137803368 completes successfully with all 92 jobs successful | Prior integrated source; not a substitute for the final source run |
| d3263f51 native core | Job 117705928467 passes 18 completion, 10 lifecycle and 2 hopping cases; artifact 12140604853 verifies exact merge parents and tree, both corrected engine identities and cleanup | 30 actual native cases, including computed-zero real AAAA DNS and canonical warm adoption |
| bf15bca9, tree 7034ae4b | 334 combined targeted cases pass with fail-on-skip in 117.38 seconds; all normal hooks pass | Accepted adjacent metadata integration and two test import cleanups; no new complete local gate is claimed |
| bf15bca9 final native core | Job 117731362149 passes all 30 cases; artifact 12144455509 binds the exact merge parents and source tree 7034ae4b, both corrected engine identities and clean cleanup | Final computed-zero real AAAA DNS and warm adoption acceptance |
| bf15bca9 final PR source | CI 39146510843 completes successfully | Exact final source PR checks |
| f4e094c7a69b3b066d4c1562c20fe2a429376929 | Actual protected PR 333 squash merge; CI 39150921761 failed in hopping readiness | This source did not pass main acceptance |
| bc849f60a7422682c8f21826807ceee792ab9953, tree 254121d7 | Protected PR 338 squash merge; own CI 39216524425 attempt 1 completes with all 92 jobs successful; all nine required checks and all five workflows succeed | Final source acceptance; all 45 canonical native cases pass on this exact main source |

Final artifact 12144455509 result SHA256 is
764f45eb9e45d377363c6607102ef96a44566955aa5a8143740413778cccba05.
Earlier artifact 12140604853 result SHA256 is
323ed323b2b78648951e887661cde3b47fd19ad6e2cfdab9d1712446c2e84c50.
The four production source-correction assets are byte-identical between the
packet-proved inputs, 30ed3d8d and the final source. The merged PR #333 source
tree matches the tested PR source tree. Source merge does not deploy a node.

Two test fixtures needed corrections during CI. Commit d92f8ec3 separates nft
block terminators; actual nft 1.0.9 rejects the old input and accepts the new
input. Commit debde78a replaces AWG source aliases with canonical Git roots
shared by parent and child. The production verifier accepts the canonical root
and refuses the alias. The regression is red before the fix; 80 focused cases
pass after it. Source owner, pin and receipt guards, packet assertions and
transport deadlines remain active. The two final CodeQL import notes are fixed
in dbfeefaf without changing packet code or assertions.

Independent security reviews approve the production and CI deltas. Structured
reviews accept no blocking findings. The earlier documentation review predates
the readiness defect recorded above. The remaining runtime and client risks
listed above remain unverified; no deployment or private fleet access was used.

## Merged-source main CI failure

Actual source f4e094c7 runs CI 39150921761. Its native core job
117744254720 fails only the IPv6 hopping case at SOCKS listener readiness
following client restart during repeated retirement. The packet driver has not
started. Completion passes 18 cases, including computed-zero real AAAA DNS;
lifecycle passes all 10 cases and IPv4 hopping passes. Artifact 12145707771
binds exact source f4e094c7 and records successful cleanup without differences.
Its result SHA256 is
2e9ddc84a2059ba15ca9cb8d37fa2445bf016490de78a21555a32c05d372c7ea.
The complete run is terminal failure: 90 jobs succeed; this core job and the
required-check aggregate fail. The other native and recovery lanes succeed.

The failed child does not retain a readiness reason in that artifact or job log.
The daemon, TCP framing and network causes cannot be distinguished from this
record. A separate actual local TCP experiment confirms a readiness helper
defect: contiguous SOCKS 05 00 succeeds, while the same response split into
05 then 00 is refused. That experiment does not reproduce or attribute the
historical CI failure. That checkpoint required a correction and finite
diagnostics. Readiness deadlines, refusals and network guards remain active.
Final source acceptance uses corrective protected-main commit bc849f60 and its
own successful CI; the failed result for f4e094c7 remains unchanged.

## Corrective diagnostic candidate

PR #331 candidate e415ec41ad6afaf0da2735bf5c5d3b04d6be2a0a runs CI
39156237467. Its native core job 117760059751 fails one of 32 cases;
completion passes 18 cases, lifecycle passes 10 and hopping passes three of
four. Both IPv4 and IPv6 SOCKS hopping cases pass on this candidate. That
result does not establish the cause of the historical f4e094c7 failure.

Artifact 12147219733 binds the exact merge parents and tree 5f0ebad3, all
32 expected case IDs, successful cleanup and no differences. The sole failure
is DHCPv6 bootstrap readiness before multicast sending. Its closed diagnostic
has stage `exit` and authority mismatch zero: the input route lookup returns
nonzero. The command stderr is not retained, so the exact kernel or CLI cause
remains unknown. This is not evidence of a packet or firewall failure. The
candidate is not accepted; the sole DHCPv6 owner investigates the smallest
causal proof before another source correction or native run.

The later diagnostic candidate 1a3a627ebd0c257a1e28caecab6ceeacd425fd99
runs CI 39196976196. Core job 117881775746 again passes 31 of 32 cases and
fails only the same DHCPv6 receiver before multicast sending. Artifact
12163221331 records successful cleanup without differences; outer resource
removal succeeds.

The six fixed stderr categories do not match this failure, so readiness remains
`exit` with authority mismatch zero. Source inspection confirms that this stage
requires a real nonzero exit from the child `ip`; it is not a parent fallback
for an early Python failure. The exact command error remains unknown. Both
symbolic `udp` and numeric `17` succeed in a separate local comparison on the
exact CI image, so that comparison does not explain the CI failure and does not
justify a numeric protocol change. The actual embedded receiver and its
arguments, environment and executable authority need further comparison.
This diagnostic candidate is not accepted.

Candidate 86ffdad7013d7e60eb752b931f762eb4b619df2e runs CI 39202116288.
Core job 117897145543 fails the early canonical DHCPv6 preflight. The full
canonical suites remain empty; this is not a completed 32-case core run.
The separate diagnostic records return code 2 from the verified system `ip`
and the 36-byte stderr `RTNETLINK answers: Message too long` followed by a
newline. The failure precedes multicast sending. Cleanup succeeds without
differences, and the owned container is removed successfully.

This netlink command error is not evidence of a data-plane MTU failure or
firewall packet loss. The exact kernel/iproute2 path and the suitability of
the query for local DHCPv6 delivery require causal verification before repair.
The diagnostic candidate is not accepted.

## Corrective receiver readiness candidate

Candidate 899c6308bf1ad84576b78889f93fc8a24e4945b0, tree
bd8cc1d8898b9e83c32eb9248983abeea52f504e, removes the multicast input
route query. That query can select multicast forwarding rather than local
delivery and return EMSGSIZE when no forwarding interface exists. The local
kernel lacks CONFIG_IPV6_MROUTE, so its successful query did not prove the
affected CI path. The receiver now verifies the socket device binding and
exact joined interface/group membership before READY. It retains all 18
packet assertions, sender behavior, deadlines and cleanup. The unused route
diagnostic and artifact machinery is removed.

The focused portable suite passes 374 cases. Independent source review and
structured review report no blocking findings; normal hooks pass. A first
local multicast probe returns no payload and remains unexplained. A later
bounded comparison uses fresh namespaces and sockets for each arm: both the
default route and explicit local-route arms receive the actual multicast
payload. No explicit route repair is added, and the later comparison does
not explain the earlier null result.

CI 39205012239 fails in core job 117906019336 at the early positive
multicast packet assertion. The receiver readiness check passes; the expected
first payload is absent. Full canonical core suites remain empty. Cleanup and
owned-container removal pass. The fresh manifest contains all 47 required
cases, but collection is not execution. This candidate is not accepted.

The first complete local attempt exits 2 after 61.445 seconds, before unit
tests. Terraform cannot complete the UpCloud 5.45.0 darwin_arm64 provider
protocol handshake; the provider writes no protocol header. This attempt
does not pass. A bounded local-tool investigation retains the frozen source
and does not use provider credentials or change infrastructure.

The coordinating sessions stop further candidate retries for this task at
that finite checkpoint. PR #331 retains its separate deployment-reliability
and DHCPv6 work without acceptance. The coordinating sessions chose to publish the existing SOCKS readiness
correction alone on f4e094c7, with its own complete local gate, source CI
and actual-main acceptance. The resulting PR #338 evidence follows below.
No second implementation is made.

## Separate SOCKS correction acceptance

PR #338 publishes ef911bd482c855f51b46ebe1dc96315f06591802, tree
6c69afc043a80d07b3e0ed210c0482387e5a2929, with parent f4e094c7.
Only the six readiness helper, regression and instruction paths change. The
four production checksum-correction assets are unchanged. Its CI 39205902851
core job 117908612097 passes all 30 cases: 18 completion, 10 lifecycle and
both hopping families. Artifact 12165999379 binds virtual source
2c60caa5bdaf6a3855cf9c4bac3abbcfe43f34ff, parents f4e094c7 and ef911bd4,
and tree 6c69afc0. Cleanup succeeds without differences. The result SHA256 is
e069bb9d3fe2a7e7a86552139983eba39462ab41da2ae9f71f77792a21ecc226.
Both exact AWG pins retain correction identity 94a67434. This is prior-source
evidence; the final head below requires its own checks.

The local gate uses a short owned mode-0700 TMPDIR because the same provider
binary cannot open its Unix socket under an overly long temporary path.
The first two attempts fail on public provider-download timeouts, first in
validation and then in Terraform mock-test initialization. Neither attempt
passes. The next attempt uses existing public provider installations with
unchanged lockfiles and standard Terraform checksum verification. Source,
tests and security gates are unchanged.

That next local attempt is interrupted after three failures, 3386 passes and
230 native deselections in 989.10 seconds. It is not a complete gate pass.
The nginx fixture passes after its temporary-directory group matches the
effective group. Both lock fixtures still fail with that repair. A synthetic
child under the fixture HOME reproduces a missing attrs import: the package
exists only in user-site, which the fixture HOME hides. A fresh private
virtualenv installs the unchanged hash-locked requirements and passes pip
check with user-site disabled. All three fixtures and the 148 readiness/runner
cases then pass together: 151 passed in 16.18 seconds. No guard is relaxed.

CodeQL note 1317 identifies an empty exception handler in the optional unit
state diagnostic. Normal follow-up commit
69ba5de4e5e767c38ade02da1b86c17cc121ada5 returns the same fixed `unknown`
state explicitly instead of falling through to that return. Independent review
confirms equivalent behavior; all normal hooks pass. Final source tree
254121d74ef679d12bca5348f486146f3eddbe87 runs fresh CI 39210543551 and a
fresh complete local gate using the private environment. Final-source checks
and actual protected-main acceptance passed as recorded below.

That first final-head local attempt passes all 220 provider mock tests,
18 bootstrap cases and 59 policy checks, then fails yamllint because the
private virtualenv was placed inside the checkout. Third-party package
templates are scanned as repository YAML. The dependency files move outside
the checkout; their contents and logical entry-point prefix stay unchanged.
The original lint configuration then passes, as do the three fixture cases.
A fresh complete gate runs on the same unchanged source. Fresh CodeQL run
39210543459 passes and the PR merge ref has no open code-scanning alerts.

Fresh final-source core job 117922889444 in CI 39210543551 passes all 30
cases: 18 completion, 10 lifecycle and both hopping families. Artifact
12167304967 binds virtual source d69238e05060c86d0924a63794aea42e017a39fc,
parents f4e094c7 and 69ba5de4, and exact final tree 254121d7. Both exact AWG
pins retain correction identity 94a67434. Cleanup succeeds without
differences. Its result SHA256 is
e4a798e73ba700d3d4aa3341fb3207e8e95f99c9ac9b733758ee056463611232.
The complete local gate, hosted CI and actual-main acceptance results follow
below.

The same virtual source also passes both recovery plans: eight cases in
artifact 12168557992 and seven in artifact 12168790447. Both record successful
cleanup without differences. Their result SHA256 values are, respectively,
a75a1c17e870d93bd40048cf1aeace6a57fccb7c5ac15622ab94a4bc1ae9722f and
28cbf5044fc13afde9a98773043b497f459f581181bbb52b8c673d1c5e78b250.
All 45 cases across the three canonical plans pass. Actual-main acceptance is
recorded separately below.

The fresh complete local `make -j1 check` on 69ba5de4, exact tree 254121d7,
exits zero with `ci-fast: OK`. It passes 8660 portable cases and 45 subtests
in 2632.69 seconds; 230 native cases are deliberately deselected by that lane.
All 65 BATS and 322 vpnd cases pass, as do 220 provider mock cases,
18 bootstrap cases, 59 policy checks, all lint, snapshots, schema and package
checks. The vpnd transfer accounts for all 206 baseline functions. The source
worktree is clean. The complete log SHA256 is
b0611a7f918a64870a987cd007b6f01dfca93d5d7836b8f52db341ac713a5ebb.
The private hash-locked environment remains outside the checkout, with its
original entry-point prefix, user-site disabled and an owned canonical short
temporary directory. Earlier failed attempts remain failed.

CI 39210543551 completes successfully on final source 69ba5de4. All 38 jobs
are terminal: 19 selected jobs succeed and 19 unaffected jobs use the normal
dependency-selector skip. All 45 canonical native cases execute and pass.
The four companion workflows also succeed. The final PR rollup has 25
successful and 19 skipped contexts, no unfinished or failed context, and no
open CodeQL alert.

Normal protected squash merge of PR #338 creates
bc849f60a7422682c8f21826807ceee792ab9953 with parent f4e094c7 and exact
tested tree 254121d74ef679d12bca5348f486146f3eddbe87. Its diff from tested
source 69ba5de4 is empty. No admin override, force push or branch deletion is
used. Its own complete main CI passes as recorded below; the historical
f4e094c7 failure is not relabelled. Source acceptance is complete; task lifecycle
records are updated separately.

## Corrective main evidence

Actual main bc849f60 core job 117941600464 passes all 30 cases in CI
39216524425: 18 completion, 10 lifecycle and both hopping families.
Artifact 12171151026 binds exact source
bc849f60a7422682c8f21826807ceee792ab9953. The computed-zero real AAAA DNS,
IPv4/IPv6 repeated retirement and warm adoption cases pass. Both pinned Go
commits and correction identity 94a67434 match. Cleanup succeeds without
differences. The result SHA256 is
313afdaca1e853d1d805561c3dab485aa6879ff1de8991df95ae4c5e1e890cb3.
Independent acceptance review verifies these fields. This core result is
separate from the complete main CI and companion workflows recorded below.

Independent review also verifies both recovery artifacts on exact actual
source bc849f60. Artifact 12171516343 passes all eight recovery-1 cases;
its result SHA256 is
84068018c46145f058b9b8320c4dc5982d0c00f618993c1239c862a847b19ee4.
Artifact 12170944370 passes all seven recovery-2 cases; its result SHA256 is
dbbad1244bf48c22e4f258109cf762539acdd76fb4c9878cddfb887ee00204c5.
Both record successful cleanup without differences and the correct pins and
correction identity. Thus all 45 canonical cases pass on actual main.
The native runtime integration job 117941600418 and required-check aggregate
also succeed.

Complete main CI 39216524425 attempt 1 finishes with conclusion SUCCESS on
exact source bc849f60a7422682c8f21826807ceee792ab9953, parent f4e094c7
and tree 254121d74ef679d12bca5348f486146f3eddbe87. All 92 jobs succeed;
no job is unfinished, skipped or failed. All nine required checks succeed,
including the aggregate. All five workflows succeed: CI 39216524425,
CodeQL 39216524252, REALITY 39216524392, release 39216524108 and
scorecard 39216524385. Combined with the exact-tree complete local gate,
source PR checks and 45 actual-main canonical cases above, this establishes
final source acceptance on bc849f60.

The historical f4e094c7 failure and the failed PR #331 diagnostic candidates
remain failed evidence. The cause of the historical SOCKS failure and the
earlier local multicast null result remain unexplained. PR #331 owns its separate
unaccepted DHCPv6 work. No deployment, private fleet access, sentinel
convergence, live route, browser or physical-client acceptance is claimed.

## Post-review contract clarification

An additive documentation follow-up after review 8aa6cbda and terminal record
adca1393 states REQ-NPC-SOCKS-READINESS explicitly in the archived delta and
main specification. The accepted implementation, regressions and source proof
on bc849f60 predate this clarification. The new row maps that existing proof;
it does not claim a new runtime change or a new test run. The issue, execution,
lifecycle receipts and accepted commit_sha remain unchanged.
