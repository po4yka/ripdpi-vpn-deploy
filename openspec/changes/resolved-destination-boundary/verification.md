---
task_id: SEC-1791617841911853
change: resolved-destination-boundary
commit_sha: 64c29eaa1b8b0f8cca61362d680a23d9b54043d6
local: required
local_evidence: complete affected suites plus the named native positive/failure cases after implementation
remote_ci: required
remote_ci_evidence: terminal exact-SHA protected-source checks for this new capability
dry_run: not_applicable
dry_run_evidence: source capability is exercised in isolated local/native runtime; no real inventory run is part of this task
staging: not_applicable
staging_evidence: source-only scope; isolated native behavior is required, and any external rollout is separately authorized
live: not_applicable
live_evidence: no production rollout is part of this source or disabled-default feature task
client: required
client_evidence: exact supported real client completes the named isolated protocol or TLS probe cases
artifact: required
artifact_evidence: rendered contracts and redacted requirement-specific exact-source artifacts after implementation
---

# Verification

## Requirement evidence

The policy/schema/rendering and resolution/dialing steps have observed evidence below. Complete lifecycle and final integration gates remain in progress. The approved WARP UDP redesign adds an isolated tunnel-only gateway and requires separate actual vendor proof; kernel/runtime fixtures cannot close that integration. Implementation is committed locally at the source revision above and merged with current main at `ead1e713`; no hosted, vendor or deployment acceptance is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RDB-POLICY | SEC-1791617852155511 | 141 complete focused kernel/schema/frontend/private-authority/policy tests passed; all 162 snapshots matched. Genuine REALITY, nginx TLS XHTTP, Hysteria and classifier native cases passed. Current final-kernel native file passed, proving public TCP/UDP, own web and remote SSH, zero forbidden contacts, destination-NAT rejection and retained policy after rejected late authority. | source cases passed |
| REQ-PROTO-RDB-POLICY | SEC-1791617853671017 | Complete current six-case native lane passed: REALITY/Vision, nginx TLS XHTTP, Hysteria, classifier destination-NAT isolation, common lifetime/quarantine behavior and live-control crash recovery; 6 passed in 487.87 seconds, zero skips. All 47 public source hashes still matched after execution. | source cases passed |
| REQ-PROTO-RDB-POLICY | SEC-1791617866332021 | The complete native frontend, classifier and kernel files count actual accepted traffic and zero forbidden receiver contacts. Current snapshots, template coverage and task contracts passed; the integrated full local gate and exact-SHA hosted checks remain required. | integration gates pending |
| REQ-PROTO-RDB-DIAL | SEC-1791617853671017 | Complete policy/private-reader/classifier portable suites: 85 passed in 7.61 seconds. Complete native common case and frontend matrices passed mixed/denied answers, fresh resolution and bound UDP destinations, with exact packet identity/count checks. | source cases passed |
| REQ-PROTO-RDB-DIAL | SEC-1791617866332021 | test_transport_destination_boundary.py and test_transport_normalizer_native.py cover mixed A/AAAA answers, changed answers on fresh bindings, re-admission of existing bound literals, fresh UDP destinations and exactly-once delivery. The integrated full local gate and exact-SHA hosted checks remain required. | integration gates pending |
| REQ-PROTO-RDB-PLUMBING | SEC-1791617852155511 | Genuine REALITY, XHTTP and Hysteria client cases passed their complete public/denied-destination matrices. Exact production prestart reproduction proved current normalizer/gateway activation, authenticated private probes and recovery after actual gateway SIGKILL. Private listeners and explicit JSON credential naming retain the unit security floor. | source cases passed |
| REQ-PROTO-RDB-PLUMBING | SEC-1791617861504003 | test_transport_frontend_boundary_native.py exercises genuine REALITY/Vision, nginx TLS XHTTP and Hysteria clients; test_transport_classifier_boundary_native.py proves distinct public interface paths and private/management refusal. Complete lifecycle and two-TUN acceptance remain required. | source cases passed; lifecycle pending |
| REQ-PROTO-RDB-FAILURE | SEC-1791617861504003 | Complete portable suites prove bounded malformed/authentication refusal and redacted private authority. The native kernel file proves rejected candidate preservation; complete runtime rollback and recovery remain required. | source cases passed; lifecycle pending |
| REQ-PROTO-RDB-FAILURE | SEC-1791617866332021 | Independent source reviews approved the controller capability, resolver publication and retained rollback contracts. Complete integrated local gates and terminal exact-SHA hosted checks remain required. | integration gates pending |

## Host preparation evidence

The host-only preparation at implementation HEAD `6202c7ec93c075b6b5fd3b40065204e4f59d9461` observed 163 matching template snapshots, 136 resolved variables across 259 template references, valid task contracts for 35 tasks and 129 steps, and a clean diff whitespace check. The complete agent-instruction, executable-coverage, Molecule-dependency and CI-dependency-selection files passed 75 tests in 8.35 seconds with zero skips. One syntax warning arose while parsing an existing script's invalid escape sequence; it did not fail those assertions. The complete transport-egress role file passed 32 tests in 0.45 seconds, and the complete synthetic SOPS roundtrip, transport credential and frontend admission files passed 38 tests in 5.98 seconds with genuine local tools and zero skips. These are preparation checks, not the full integrated gate or hosted acceptance. After integrating current main, independent review approved the seven shared paths and 145 complete lightweight integration tests passed; task contracts then covered 37 tasks and 141 steps.

The earlier five-case native receipt remains evidence for the 47 public source hashes captured at that execution. Subsequent controller `CAP_SETUID` retention, resolver snapshot context, terminal-blank-line cleanup and live-control recovery changes are covered by their separate checks and current-source reruns. The earlier receipt remains historical and does not establish acceptance of the final tree.

The earlier production-role rerun passed convergence, zero-change idempotence and genuine frontend TCP/UDP echo, then exposed an account-alias fixture that supplied the published UID-bearing config to input-only admission. The canonical builder repair retained the exact refusal-before-mutation assertion and passed independent review and all 33 role tests. The subsequent complete scenario passed dependency, syntax, create, prepare, check-mode, convergence, zero-change idempotence, verification and destruction. Verification observed actual UID-alias and UID-override rejection/recovery, autonomous normalizer-loss recovery, kernel-table-loss recovery, whole-route rollback preserving bytes/mode/group, public TCP/UDP afterward, and accepted immutable executable/asset preservation while a different public CLI pin remained installed.

The existing autonomous crash case closes probe controls before process loss. The added live-control regression demonstrated two separate failures before correction: two actual TCP `TIME-WAIT` records had absent UIDs and explicit zero inodes, causing `foreign-port-owner`, and one immediate restart independently failed `listener-unavailable`. TCP-listener-only `SO_REUSEADDR` passed the original 10-second readiness, 3-second TCP and 0.7-second UDP deadlines while the unchanged kernel audit still refused. The combined narrow owner-admission fix then passed with both old tuples retained, required owner admission, exactly one restart, fresh public TCP/UDP and zero forbidden contacts; 1 passed in 23.70 seconds with zero skips. The 47-file red, listener-only green and combined green receipts remain separate. All 45 portable kernel tests passed, including 17 new retired-versus-live authority cases. Independent review approved both corrections; UDP reuse/quarantine is unchanged. The complete current six-case lane subsequently passed in 487.87 seconds with zero skips, and all 47 captured public source hashes still matched afterward. Owned fixture namespaces, unit files and observer paths were all removed. The reviewed follow-up passes the complete pinned source gate; remaining role and hosted gates are recorded separately below.

## Additional WARP evidence

- Current-source two-TUN native case passed authenticated TCP/UDP through two actual tunnel interfaces, zero recipient plaintext frames on the underlay, tunnel-loss and stale-ifindex refusal, and recovery after fresh policy and gateway generation admission. All owned test containers were removed.
- The complete WARP namespace role scenario passed sole vendor service/state ownership, namespace-bound sandbox, non-mutating fresh check-mode, foreign-unit refusal, retirement and retained rollback. The fixture's vendor primitive proves isolation and lifecycle, not registered vendor forwarding.
- Actual registered Cloudflare WARP TCP and UDP forwarding: unverified; requires separate authorization and a disposable registered test environment. No provider action was executed while planning or inspecting the offline package.

## Adapter pairing evidence

The complete common native test proves continuous-quiet tuple quarantine, sustained late responses and same-destination reuse. Normalizer process death, paired gateway generation reset and autonomous owned frontend recovery require their separate complete lifecycle proof. The 240-second quiet margin is derived from the pinned mapping inactivity and sweep windows; the final native test below observes its reuse boundary, and the margin must not be shortened to make a test pass.

The final complete five-case lane passed accepted TCP/UDP beyond 305 seconds, the original 0.7-second UDP response deadline, refusal at 245 seconds, reuse at 280 seconds, and actual frontend/upstream socket inode retention and replacement. The tested public source aggregate SHA256 was `0b5be1814212a2487e6f56853e2aff9d178921038a611998b66b6f0c1084642b`; this is a 47-file content receipt, not a Git commit or vendor acceptance. Exact native runtime SHA256 values were Xray `8255dd939c34cf966cc91517b6324dd3c8d0bcf49ffac8beca049a38c46845ed` and Hysteria `8225c8380f1ae8122921d4986c2b70976e9c6e6f87a977e7d0498a813f4f3e37`.

Earlier failures were retained and diagnosed: genuine frontend log files needed production provisioning; repeated application TCP reads incorrectly inherited a shrinking handshake deadline; shared emulated guest scheduling delayed an exact UDP packet; and synchronous peer counter writes on overlay storage delayed its echo. The final fixture uses the genuine log provisioner, independent original application read budgets and private tmpfs observer state. Configurations and releases retain their original private storage. Production helper code, UDP deadlines, receiver assertions and the lifetime/quarantine durations were not weakened.

## Binding and active-stream evidence

Require exactly-once repeated named packets through one admitted binding, fresh-target/fresh-association resolution, public-to-private DNS changes preserving only the old validated public binding, bounded binding exhaustion and current policy rechecks. The common native helper test must sustain accepted TCP/UDP beyond 300 seconds; share that elapsed-time case with quarantine coverage rather than repeating it for every frontend. No per-datagram DNS transaction or unconditional five-minute active-stream cutoff is required.

The current six-case receipt has public-source aggregate SHA256 `8d2378b9889c66c7d8f7b26c1d9d6438c3793c09eba71e0c11e993bb1c626437`. The four runtime digests are unchanged from the earlier native receipt. This current content proof remains separate from the pending integrated gate and exact-SHA hosted checks.

## Startup synchronization follow-up

The first complete Xray consumer attempt failed strict process identity admission and cleaned up. Redacted snapshots observed a canonical gateway's root executor with full capabilities, then the expected runtime UID with empty capabilities; they did not retain a same-PID execution timeline. Credential-bearing units on the tested manager already used `exec`, so this is not evidence that the gateway defaulted to `simple`. The controller nevertheless inspected identity before joining the start job, and both frontend units lacked an explicit execution boundary.

The correction inspects owned metadata only before synchronous startup, then retains unchanged strict actual UID, active-state and PID admission. All four foreground runtime units explicitly use `Type=exec`; snapshots, status and authenticated readiness remain strict. Independent reviews approved this change; all 36 role tests and 163 snapshots passed. A mixed-source Hysteria run passed convergence with the new frontend boundary but had already staged older helper bytes; it was intentionally canceled during idempotence and successfully destroyed. It receives no final-source acceptance credit. Frozen-source full-stack and fresh complete Xray/Hysteria runs remain required.

## Complete pinned source gate

The integrated follow-up candidate passed `build-gate -- make check` with the pinned development requirements, anonymous disposable Docker context, a platform-owned temporary root and direct installed tool paths. The complete portable lane passed 6,157 tests and 22 subtests in 1,950.92 seconds, with zero skips; 134 native cases remain intentionally assigned to their separate lane. The current Python CLI lane passed all 297 tests in 55.49 seconds, and all 206 baseline transfer functions mapped to passing cases. Task contracts, Terraform validation and policies, secret scans, Ansible lint and syntax, workflow security, cloud-init, package reproducibility, dependency audit, schemas, template coverage, snapshots and runtime parser compatibility passed. Independent final source reviews approved the non-authored follow-up changes without actionable findings.

The final pinned Xray Molecule scenario passed all configured phases, including convergence, zero-change idempotence, verification and destruction, in 1,261.4 seconds. Hysteria, transport-egress, WARP and full-stack final scenarios are still running or queued serially. Exact-SHA hosted checks and registered vendor forwarding have not yet been observed.

Earlier full-suite failures remain historical: the non-platform temporary root inherited a foreign group, an inactive tool shim failed before SOPS execution, and stale contract fixtures omitted guarded inputs or selected superseded task phases. Corrected environment and reviewed fixtures retained the original security assertions. The complete-map staging profile now explicitly enables the mandatory guard; its exact-map assertion remains unchanged.
