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

This is a verification plan, not observed implementation evidence. No execution step is complete. The exact implementation SHA and evidence fields remain unset until that implementation exists and is tested. Validation of these planning documents cannot satisfy runtime acceptance.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RBO-COST | MON-1790835430228619 | Approved collector/observer admission and zero-new-paid-resource checks | Required; no deployment |
| REQ-RBO-BOUNDS | MON-1790835428068030 | Cgroup/load/WAL/disk-guard tests and matched VPN performance runs | Required; budgets unmeasured |
| REQ-RBO-PRIVATE | MON-1790835428600254 | Real mTLS positive/revoked/wrong-SAN cases, listener inventory and unchanged VPN vhosts | Required |
| REQ-RBO-WATCHDOG | MON-1790835429142513 | Kuma direct-push missing-signal/recovery drills, observer outage, redaction, rotation and encrypted backup/isolated restore | Required; product approved, host unverified |
| REQ-RBO-DELIVERY | MON-1790835429142513 | Actual relay send/edit receipts, stale-receipt and token-failure cases, independent-route human receipt | Required |
| REQ-RBO-EVIDENCE | MON-1790835429687617 | State-separation tests and authenticated external client verification | Required; no live client result |
| REQ-RBO-MIGRATION | MON-1790835427523974 | Obsolete-topology rejection, migrated callers, rollback drill and explicit cutover approval | Required |

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
