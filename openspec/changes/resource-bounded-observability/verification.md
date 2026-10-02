---
task_id: MON-1790835036464962
change: resource-bounded-observability
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

Implementation and local verification are in progress. The observations below
are local source/runtime evidence, not live deployment or human-delivery proof.
Required evidence fields remain unset until their complete gates pass. The
contract/operator migration step is complete with its positive and obsolete-input
tests; other steps and the overall feature remain open.

## Sender replacement observations (2026-10-01)

- The pinned vmagent runtime recovered exact pre-restart sample identities and
  timestamps at the real Prometheus collector after both a clean restart and
  SIGKILL during an outage. Observed queue allocation was 65,536 and 110,592
  bytes respectively. These are process-restart tests, not host power-loss or
  fsync durability proof.
- The complete unfiltered alternate arm64 Linux runtime invocation passed
  (596 tasks, 18 changes, zero failures). Actual-filesystem pressure stopped
  ingestion in 5.03 seconds and the durable latch rejected a manual restart;
  the public nginx PID and TLS listener remained unchanged. Native queue
  saturation persisted 1,077,841,731 bytes, exceeding twice the effective queue
  capacity, with a measured physical peak of 1,006,788,608 bytes below the 2 GiB
  admission allowance. Native eviction reported 1,048 blocks / 574,098,462 bytes;
  the original sender PID survived within its 192 MiB / 10% CPU slice. This is
  local process/filesystem proof, not ten-node load, matched VPN performance,
  live host admission or canonical Molecule acceptance.
- The production staging queue-metrics program ran unchanged in the isolated
  Linux container: all ten required native metrics existed with exactly one
  series each. Initial drop/error counters were zero and real sent blocks
  advanced. Strict native config parsing required moving unsupported YAML
  label-length settings into whole-series-rejection runtime flags; the bounds
  were preserved, not disabled.
- Delivery-loss rules now cover native queue/HTTP discards and label-limit
  rejections. Real promtool cases cover individual and simultaneously present
  counters, including zero and nonzero mixtures. An initially discovered
  duplicate-labelset expression error was corrected with independently
  evaluated counters; their byte, block and row units are never added.
- Independent source security re-review approved the replacement and its
  follow-up parser/rule corrections. The latter review observed 80 agent and
  alerting tests, all 147 snapshots and whitespace validation passing.
- The complete `make -j2 check` passed through the machine-wide build gate:
  4,979 portable Python tests and 20 subtests passed, with the four separate
  native-runtime tests deselected by the normal portable contract. All 55 Bats
  tests, release Clippy, Rust tests, lint, schemas, Terraform mock-provider
  tests and snapshot checks passed. A preceding full run loaded two obsolete
  sender assertions before the native parser correction; both were corrected
  and the full run repeated successfully. A transient registry timeout also
  cleared on the bounded retry without changing gates or pins.
- The subsequently reviewed separate vmagent install root and final
  pre-activation capacity recheck passed 53 agent/resource tests independently.
  The historical runtime root remains intact for rollback. Actual failed-
  activation evidence follows; canonical Molecule acceptance remains blocked.
- The exact canonical Molecule image was subsequently pulled successfully,
  but its only platform is amd64 and the authorized local VM is arm64 without
  usable emulation for this image. A direct shell invocation returned
  `exec /bin/sh: exec format error`; canonical role scenarios failed in prepare,
  not in role convergence. The earlier manifest/registry errors are no longer
  the blocker. Owned test containers were removed. No image pin, VM setting,
  emulation registration or production configuration was changed.
- A real failed-cutover test reproduced a false-positive readiness result:
  an unrelated process serving HTTP 200 on the candidate port was accepted
  after the candidate restart. Readiness now binds the listener socket inode
  to the actual systemd MainPID and executable, checking unchanged process
  identity before and after proxy-free HTTP. The unchanged predecessor-runtime
  test then passed: exact prior unit, configuration generation and executable
  were restored, with retained WAL and queue identities. The complete alternate
  arm64 agent invocation then passed 400 tasks with 46 changes, zero failures
  and four expected rescues. Both real Prometheus-to-vmagent and vmagent-to-vmagent
  failed activations restored the captured unit SHA, generation, running
  executable, historical binary SHA/link and WAL/queue inode identities.
  The latter test first waited for nonzero persisted pending bytes and zero
  in-memory blocks; pending bytes remained nonzero after rollback. This proves
  activation rollback and retained pending data, while exact historical-sample
  replay is established by the separate restart/SIGKILL tests above.
- The alternate agent-disabled scenario passed prepare, converge and verify
  with a final cumulative recap of 22 tasks, 8 changes and zero failures. It removed owned
  vmagent runtime entries while retaining the historical runtime, credentials,
  configuration, WAL, queue and unrelated producer file.
- A separate no-op enabled convergence passed 104 tasks with zero changes and
  zero failures after both rollback cases. Owned test containers and temporary
  inventories were removed; shared VM settings, Docker images and unrelated
  configuration were untouched.
- After the final readiness change, 64 agent/resource/documentation-governance
  tests passed; a separate operator/staging/alerting run passed all 204 tests.
  Independent review observed 213 combined focused tests passing and all 147
  snapshots matching. Collection is now 4,992 tests, including 4,887 unit tests.
  These are post-change targeted checks, not a second full repository run.
- All applicable final staged pre-commit hooks passed, including secret
  scanning, Ansible/YAML lint, task contracts, secret coverage and snapshots.

## Earlier local results before sender replacement (2026-10-01)

- The operator explicitly approved replacing only Prometheus Agent with vmagent,
  including a bounded disk queue of at least 500 MiB. The implementation target
  is 512 MiB; collector, Kuma, private mTLS and the 192 MiB / 10% CPU agent slice
  remain unchanged. This approval is not restart/resource proof or permission
  for real-host deployment. The failed predecessor observation below is retained.
- **Predecessor runtime failure:** the actual Prometheus Agent 3.14.0 lost delivery of
  pre-restart backlog during a 70-second collector outage plus agent restart.
  The unchanged historical-sample assertion failed with
  `wal_backlog_not_recovered`, while fresh post-restart samples arrived.
  The pinned WAL reader filters samples older than its restart timestamp;
  retention duration cannot repair that behavior. No sender replacement,
  patched binary, relaxed assertion or deployment is approved by this result.
  The resource/WAL execution step and rollout remain open.
- The separate disk-pressure diagnostic used actual allocated blocks and
  stopped ingestion in 4.03 seconds; the durable latch refused restart.
  The public nginx process and HTTP/TLS listeners remained unchanged and the
  agent stayed active. This invocation explicitly omitted the already-failing
  `wal-recovery` phase: 27 tasks passed, not the complete runtime gate. It does
  not prove ten-node load, burst-rate admission or matched VPN performance.
- The actual pinned arm64 Kuma 2.5.5 image ran twelve monitors within its
  512 MiB / 0.25 CPU configuration. Nine ordinary node monitors detected missing
  pushes at 121.088–121.416 seconds, the pipeline monitor at 120.998 seconds,
  a never-started monitor at 120.096 seconds, and delivery at 540.925 seconds.
  The harness checked actual upstream JSON acknowledgement, unknown-token
  rejection, authenticated monitor persistence across restart, and quiesced
  archive/age encryption followed by authenticated reads from an isolated
  restored instance with no network or published ports. This exercises the
  upstream application, not full production-role backup/restore convergence,
  secondary Telegram delivery, human receipt, or observer-host independence.
- Real OpenSSL IP-SAN, wrong-IP, scoped certificate revocation, and SOPS/age
  round-trip checks passed in the local PKI suite (11 tests). Contract tests
  cover obsolete topology rejection, exact monitor/sender bindings and
  secret-authority uniqueness. Mocked service/API tests remain source evidence.
- The local Linux disabled-observer scenario passed prepare, converge, a
  zero-change second converge and verify. An active backup's real restart
  finalizer ran before the final observer stop; owned timers remained disabled
  and the unrelated fixture service stayed active. The production archive
  extractor passed under exact `CAP_CHOWN|CAP_DAC_READ_SEARCH`, with no
  `CAP_DAC_OVERRIDE`, including rejection of writes after ownership handoff.
  This does not claim enabled observer-role deployment or a production backup.
- Source security re-review approved the current implementation after fixing
  restore ownership, backup/disable serialization, complete relay labels and
  exact enrolled-node coverage. The reviewer observed 195 focused tests plus
  four executable coverage-guard regressions. Runtime failure/recovery gates
  remain independently required; source approval does not override them.
- All 147 templates rendered; secret coverage, example-secret and bundle
  schema validation, deployment-profile constraints and actual sing-box/Xray
  liveness-profile parsers passed. Terraform mock-provider tests, 45 Conftest
  assertions, shell/YAML lint, cargo-deny and the Rust 1.88 MSRV check passed.
  The final full portable pytest run observed 4943 passes, one stale documented
  test-count failure, four intentionally deselected native-runtime tests and
  20 passing subtests. The documented count was corrected to 4948 total / 4843
  unit tests; both documentation-governance tests then passed separately.
  This is not a single all-green full-suite run. The earlier 41 failures were
  corrected: stale role-wiring checks, the encrypted synthetic fixture,
  explicit certificate key identifiers and local SOPS executable selection.
  All 55 Bats tests, release-mode Rust tests and release Clippy passed.
  All applicable staged pre-commit hooks passed, including gitleaks, Ansible
  and shell lint, task contracts, secret schema/coverage and snapshots.
- The canonical `make check` attempt is not green: the pinned cloud-init
  amd64 test container failed while installing its Python packages. An isolated
  reproduction with the same pinned image exposed a Python subprocess SIGSEGV
  under local ARM emulation. No image pin or assertion was relaxed.
- The canonical pinned Debian Molecule image returned an unavailable manifest.
  Separate local Linux runtime checks use a verified arm64 systemd image;
  they do not replace or claim success for the canonical Molecule image gate.
  No VM capacity, provider resources or production configuration was changed.

## Requirement evidence

### Publication and deployment preflight (2026-10-01)

- Implementation revision `276b39f09d42a110eef8ea1876523d3240ac4dc6`
  was published and its remote branch identity verified. Hosted CI run
  `36873679819` detected the expected topology V2 / client-vendored V1 mismatch
  and HIGH OpenSSL findings in the older Molecule base images. The existing
  scan-clean image updates from main revision `8ab18771` are being integrated;
  reverting the new topology or suppressing findings is not an acceptable fix.
- The existing independent arm64 observer is reachable over pinned-key SSH,
  with approximately 14.7 GiB available memory and 427.9 GiB free on its
  separate local filesystem. Docker is active and the two required ports are
  unused. It is not yet admitted: nginx and age are absent, and no qualifying
  existing root-private backup directory was found on the separate filesystem.
- All three existing VPN nodes timed out on strict SSH over both public and
  Tailnet transports. The controller's current public address does not match
  the inventory SSH allowlists. One provider independently rejected the API
  request due to its IP allowlist; another confirmed its existing node is
  running. Reachable public TCP/443 on two nodes is not authenticated VPN proof.
- No live service, access rule, credential, host capacity or paid resource was
  changed by these read-only checks. Host admission, private monitoring routes,
  human delivery and the full cross-repository gate remain required before
  deployment or cutover.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RBO-COST | MON-1790835430228619 | Approved collector/observer admission and zero-new-paid-resource checks | Required; no deployment |
| REQ-RBO-BOUNDS | MON-1790835428068030 | Cgroup/load/queue/disk-guard tests and matched VPN performance runs | Local restart replay, queue saturation and filesystem latch passed; ten-node load and VPN performance remain unverified |
| REQ-RBO-PRIVATE | MON-1790835428600254 | Real mTLS positive/revoked/wrong-SAN cases, listener inventory and unchanged VPN vhosts | Partial local ingestion and rejection proof; full gate remains required |
| REQ-RBO-WATCHDOG | MON-1790835429142513 | Kuma direct-push missing-signal/recovery drills, observer outage, redaction, rotation and encrypted backup/isolated restore | Local application timing/restart/restore passed; production helper and host unverified |
| REQ-RBO-DELIVERY | MON-1790835429142513 | Actual relay send/edit receipts, stale-receipt and token-failure cases, independent-route human receipt | Required |
| REQ-RBO-EVIDENCE | MON-1790835429687617 | State-separation tests and authenticated external client verification | Required; no live client result |
| REQ-RBO-MIGRATION | MON-1790835427523974 | Obsolete-topology rejection, migrated callers, rollback drill and explicit cutover approval | Contract/operator step and local agent activation rollback passed; full rollback gate and live cutover remain required |

## Exact gates for implementation

- Local targeted checks: `mise exec -- python3 -m pytest tests/unit/test_observability_contract.py tests/unit/test_observability_topology.py tests/unit/test_observability_agent_render.py tests/unit/test_observability_control_plane_render.py tests/unit/test_observability_telegram_delivery.py tests/unit/test_observability_operator.py tests/unit/test_secrets_schema.py tests/unit/test_secrets_coverage.py`. Extend these and add focused resource/heartbeat tests; existing green tests alone do not cover new behavior.
- Role checks: `build-gate -- make molecule-test ROLE=observability_control_plane` and `build-gate -- make molecule-test ROLE=observability_agent`; add an executable co-hosting scenario exercising the private ingress and shared VPN nginx configuration. After implementing the new role, run `build-gate -- make molecule-test ROLE=observability_kuma` and a real pinned-container push/notification/restore scenario; mocks alone do not accept upstream behavior.
- Integration gates: `build-gate -- make snapshot-check`, `build-gate -- make check`, and `make task-check`. If vpnd changes, add `build-gate -- make vpnd-test vpnd-clippy`. Do not bypass local hooks or substitute unrelated checks.
- Hosted CI: exact implementation SHA and terminal required workflow results after publication is authorized. Local green is not remote CI proof.
- Dry-run: credential-free render plus an explicitly authorized check-mode run against the admitted host; check mode alone cannot prove cgroup, TLS, filesystem, or runtime safety.
- Staging: local disposable Linux runtime with real service processes, mTLS, representative ingestion, resource pressure, and reversible failures. Include the pinned Kuma image, actual push acknowledgement and missing-signal timing, never-started monitors, restart persistence, and isolated database restore with notifications disabled. Do not purchase dedicated staging VPS nodes. Local staging is not evidence of provider-path or real Telegram delivery.
- Live: approved collector and independent observer admission, no new paid resources, actual push-monitor configuration, private UI/ingress separation, failure/recovery transitions and human secondary-bot receipts, collector/agent/observer limits, filesystem latch, credential rotation, encrypted backup/restore, and monitoring-only rollback. Confirm a stopped observer reports external-coverage loss through the surviving primary route. Fault injections require explicit target/action scope; loss of the private path is not proof of VPN protocol failure.
- Client: three matched baseline/enabled authenticated VPN performance runs meeting design.md thresholds, plus the existing external-client reachability contract. A local self-dial or healthy exporter cannot satisfy this category.
- Artifact: redacted exact-SHA configuration, listener/resource snapshots, timestamps, API acceptance and human receipt separately, and cost/quota/cutover record. Never include provider host identity, secret URLs, tokens, decrypted secrets, or raw client payloads.

## Completion boundary

Archive and feature completion are forbidden while required evidence remains absent. Product choice is approved; missing exact-host authority, private connectivity, backup storage, credential authority or capacity is a named blocker, not a passed gate. The old dedicated-staging task remains open unless explicitly transitioned through taskctl; this replacement does not accept or erase its uncompleted obligations.
