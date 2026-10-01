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

## Observed local results (2026-10-01)

- **Open runtime blocker:** the actual Prometheus Agent 3.14.0 lost delivery of
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

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RBO-COST | MON-1790835430228619 | Approved collector/observer admission and zero-new-paid-resource checks | Required; no deployment |
| REQ-RBO-BOUNDS | MON-1790835428068030 | Cgroup/load/WAL/disk-guard tests and matched VPN performance runs | Partial local cgroup proof; restart backlog failed; VPN performance unverified |
| REQ-RBO-PRIVATE | MON-1790835428600254 | Real mTLS positive/revoked/wrong-SAN cases, listener inventory and unchanged VPN vhosts | Partial local ingestion and rejection proof; full gate remains required |
| REQ-RBO-WATCHDOG | MON-1790835429142513 | Kuma direct-push missing-signal/recovery drills, observer outage, redaction, rotation and encrypted backup/isolated restore | Local application timing/restart/restore passed; production helper and host unverified |
| REQ-RBO-DELIVERY | MON-1790835429142513 | Actual relay send/edit receipts, stale-receipt and token-failure cases, independent-route human receipt | Required |
| REQ-RBO-EVIDENCE | MON-1790835429687617 | State-separation tests and authenticated external client verification | Required; no live client result |
| REQ-RBO-MIGRATION | MON-1790835427523974 | Obsolete-topology rejection, migrated callers, rollback drill and explicit cutover approval | Contract/operator step passed; rollback and cutover remain required |

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
