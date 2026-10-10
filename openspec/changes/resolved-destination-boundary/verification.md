---
task_id: SEC-1791617841911853
change: resolved-destination-boundary
commit_sha: null
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

The policy/schema/rendering and resolution/dialing steps have observed current-tree evidence below. Complete lifecycle and final integration gates remain in progress. The approved WARP UDP redesign adds an isolated tunnel-only gateway and requires separate actual vendor proof; kernel/runtime fixtures cannot close that integration. The implementation is not yet committed, and no hosted, vendor or deployment acceptance is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RDB-POLICY | SEC-1791617852155511 | 141 complete focused kernel/schema/frontend/private-authority/policy tests passed; all 162 snapshots matched. Genuine REALITY, nginx TLS XHTTP, Hysteria and classifier native cases passed. Current final-kernel native file passed, proving public TCP/UDP, own web and remote SSH, zero forbidden contacts, destination-NAT rejection and retained policy after rejected late authority. | source cases passed |
| REQ-PROTO-RDB-POLICY | SEC-1791617853671017 | Complete five-case native lane passed: REALITY/Vision, nginx TLS XHTTP, Hysteria, classifier destination-NAT isolation and common lifetime/quarantine behavior; 5 passed in 479.02 seconds, zero skips. All 47 public source hashes still matched after execution. | source cases passed |
| REQ-PROTO-RDB-POLICY | SEC-1791617866332021 | The complete native frontend, classifier and kernel files count actual accepted traffic and zero forbidden receiver contacts. Current snapshots, template coverage and task contracts passed; the integrated full local gate and exact-SHA hosted checks remain required. | integration gates pending |
| REQ-PROTO-RDB-DIAL | SEC-1791617853671017 | Complete policy/private-reader/classifier portable suites: 85 passed in 7.61 seconds. Complete native common case and frontend matrices passed mixed/denied answers, fresh resolution and bound UDP destinations, with exact packet identity/count checks. | source cases passed |
| REQ-PROTO-RDB-DIAL | SEC-1791617866332021 | test_transport_destination_boundary.py and test_transport_normalizer_native.py cover mixed A/AAAA answers, changed answers on fresh bindings, re-admission of existing bound literals, fresh UDP destinations and exactly-once delivery. The integrated full local gate and exact-SHA hosted checks remain required. | integration gates pending |
| REQ-PROTO-RDB-PLUMBING | SEC-1791617852155511 | Genuine REALITY, XHTTP and Hysteria client cases passed their complete public/denied-destination matrices. Exact production prestart reproduction proved current normalizer/gateway activation, authenticated private probes and recovery after actual gateway SIGKILL. Private listeners and explicit JSON credential naming retain the unit security floor. | source cases passed |
| REQ-PROTO-RDB-PLUMBING | SEC-1791617861504003 | test_transport_frontend_boundary_native.py exercises genuine REALITY/Vision, nginx TLS XHTTP and Hysteria clients; test_transport_classifier_boundary_native.py proves distinct public interface paths and private/management refusal. Complete lifecycle and two-TUN acceptance remain required. | source cases passed; lifecycle pending |
| REQ-PROTO-RDB-FAILURE | SEC-1791617861504003 | Complete portable suites prove bounded malformed/authentication refusal and redacted private authority. The native kernel file proves rejected candidate preservation; complete runtime rollback and recovery remain required. | source cases passed; lifecycle pending |
| REQ-PROTO-RDB-FAILURE | SEC-1791617866332021 | Independent source reviews approved the controller capability, resolver publication and retained rollback contracts. Complete integrated local gates and terminal exact-SHA hosted checks remain required. | integration gates pending |

## Current host preparation

The host-only preparation at implementation HEAD `6202c7ec93c075b6b5fd3b40065204e4f59d9461` observed 163 matching template snapshots, 136 resolved variables across 259 template references, valid task contracts for 35 tasks and 129 steps, and a clean diff whitespace check. The complete agent-instruction, executable-coverage, Molecule-dependency and CI-dependency-selection files passed 75 tests in 8.35 seconds with zero skips. One syntax warning arose while parsing an existing script's invalid escape sequence; it did not fail those assertions. The complete transport-egress role file passed 32 tests in 0.45 seconds, and the complete synthetic SOPS roundtrip, transport credential and frontend admission files passed 38 tests in 5.98 seconds with genuine local tools and zero skips. These are current worktree checks, not the full integrated gate or hosted acceptance.

The earlier five-case native receipt remains the evidence for the 47 public source hashes captured at that execution. Subsequent controller `CAP_SETUID` retention and resolver snapshot-context changes alter `generation.service.j2` and `template_render.py`; the other 45 source hashes still match. The controller correction has independent source approval and its own genuine-unit proof. It does not retroactively change the earlier native receipt or establish complete lifecycle acceptance.

The complete production-role rerun passed convergence, zero-change idempotence and genuine frontend TCP/UDP echo. Its later account-alias fixture incorrectly supplied the published UID-bearing config to input-only admission and was rejected before reaching the identity guard; destruction succeeded. The fixture now builds the non-UID input through the canonical builder and retains the exact refusal-before-mutation assertion. Independent review approved this fixture repair, and all 33 role tests passed, including actual builder/validator acceptance and rejection. Complete lifecycle acceptance still requires the rerun through verification and destruction.

## Additional WARP evidence

- Exact-runtime native TCP/UDP through the owned namespace gateway, mixed answers, changed destinations, reconnect, tunnel disappearance, and zero plaintext underlay packets: required.
- Sole vendor service/state ownership, namespace-bound unit, non-mutating fresh check-mode, refusal of unowned state, retirement and retained rollback: required.
- Actual registered Cloudflare WARP TCP and UDP forwarding: unverified; requires separate authorization and a disposable registered test environment. No provider action was executed while planning or inspecting the offline package.

## Adapter pairing evidence

The complete common native test proves continuous-quiet tuple quarantine, sustained late responses and same-destination reuse. Normalizer process death, paired gateway generation reset and autonomous owned frontend recovery require their separate complete lifecycle proof. The 240-second quiet margin is derived from the pinned mapping inactivity and sweep windows; the final native test below observes its reuse boundary, and the margin must not be shortened to make a test pass.

The final complete five-case lane passed accepted TCP/UDP beyond 305 seconds, the original 0.7-second UDP response deadline, refusal at 245 seconds, reuse at 280 seconds, and actual frontend/upstream socket inode retention and replacement. The tested public source aggregate SHA256 was `0b5be1814212a2487e6f56853e2aff9d178921038a611998b66b6f0c1084642b`; this is a 47-file content receipt, not a Git commit or vendor acceptance. Exact native runtime SHA256 values were Xray `8255dd939c34cf966cc91517b6324dd3c8d0bcf49ffac8beca049a38c46845ed` and Hysteria `8225c8380f1ae8122921d4986c2b70976e9c6e6f87a977e7d0498a813f4f3e37`.

Earlier failures were retained and diagnosed: genuine frontend log files needed production provisioning; repeated application TCP reads incorrectly inherited a shrinking handshake deadline; shared emulated guest scheduling delayed an exact UDP packet; and synchronous peer counter writes on overlay storage delayed its echo. The final fixture uses the genuine log provisioner, independent original application read budgets and private tmpfs observer state. Configurations and releases retain their original private storage. Production helper code, UDP deadlines, receiver assertions and the lifetime/quarantine durations were not weakened.

## Binding and active-stream evidence

Require exactly-once repeated named packets through one admitted binding, fresh-target/fresh-association resolution, public-to-private DNS changes preserving only the old validated public binding, bounded binding exhaustion and current policy rechecks. The common native helper test must sustain accepted TCP/UDP beyond 300 seconds; share that elapsed-time case with quarantine coverage rather than repeating it for every frontend. No per-datagram DNS transaction or unconditional five-minute active-stream cutoff is required.
