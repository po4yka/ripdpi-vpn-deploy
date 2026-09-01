---
task_id: TST-1787850553468536
change: tst-1787850553468536-fleet-observation
commit_sha: 5f32a28b2fb3b789493e9b691c0ec8a9b26331bf
local: passed
local_evidence: "Final configuration candidate based on main 7da8b74: serialized build-gate -- make check exited 0. Python: 1524 passed, 1 skipped in 486.86 seconds. Bats: 55 passed. Rust: 169 release tests and strict release Clippy passed. Task/OpenSpec, four-provider Terraform validation/mocks, Conftest policy, cloud-init schema, production Ansible lint/syntax, gitleaks, render/snapshots, secret/bundle schemas and real pinned liveness parsers passed."
remote_ci: passed
remote_ci_evidence: "Exact-main CI 33357404456 passed 51/51 on 5f32a28b2fb3b789493e9b691c0ec8a9b26331bf, including molecule (backup) job 99382076199, pytest, and required contract gates."
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

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OBS-PASSIVE | TST-1787850885266502 | `test_fleet_inspection.py`: allowlisted commands, no repair/upload/provider calls; 35 tests passed | Local regression passed; no deployed host run |
| REQ-OBS-SSH | TST-1787850885266502 | Same suite: isolated SSH options, identity/port pins, explicit subset and malformed inventory rejection | Local regression passed; no new host-key trust |
| REQ-OBS-EVIDENCE | TST-1787850885266502 | Same suite: no-follow/FIFO/size guards, stale/future markers, malformed manifest and redacted projection | Local regression passed; unknown remains unknown |
| REQ-OBS-RESTORE | TST-1787851685101244 | `test_backup_restore_drill_contract.py`: 22 tests, including existing target/symlink preservation, cleanup and atomic marker failures | Local regression passed; no new restore or offsite proof |
| REQ-OBS-BACKUP-CONFIG | TST-1787916690652478 | Source commit `2009b6f694e326fa1f6d99333da497544b115cdd`; real restic config decryption, private intake, literal Make data, exact target, debug redaction, and exact-main CI `33357404456` | Local and hosted source validation passed; no target configuration run |
| REQ-OBS-BACKUP-QUIESCENCE | TST-1787916690652478 | Disabled/inactive/no-job checks, exclusive lock, persistent recovery, three-file rollback, incomplete-rollback retention, and Linux `molecule (backup)` job `99382076199` | Linux systemd/package/idempotence and non-execution validation passed; no backup, prune, sync, timer start, or restore ran |
| REQ-OBS-OFFSITE-PROOF | TST-1787916691156561 | Approved initial copy followed by actual remote-only isolated restore | Pending production-owner execution; configuration tests are not remote proof |
| REQ-OBS-PATH | TST-1787850896670736 | Sentinel and matrix tests use real loopback HTTPS with curlrc/proxy/NO_PROXY poisoning | Local loopback passed; not external VPN traffic |
| REQ-OBS-XHTTP | TST-1787850897343789 | `check-liveness-profile-compatibility.py`: canonical emitters and real sing-box 1.13.16 / Xray 26.3.27 parsers passed; materializer suite 54 passed | Local parser evidence; no external traffic claim |
| REQ-OBS-IDENTITY | TST-1787850897969705 | Installer/materializer regressions: explicit host/instance, key derivation match, revoked client and other-client exclusion, one private decryption | Local regression passed; no real client installation |
| REQ-OBS-LIFECYCLE | TST-1787850898631764 | Runtime/matrix suite 91 passed, including creation-time interruption, owned-resource cleanup, occupied listener and unobserved-network regressions; final serialized ci-fast passed | Local/loopback evidence only; no external VPN traffic |
| REQ-OBS-DISPOSABLE-EXECUTOR | TST-1787850899238844 | `test_disposable_liveness_executor.py` plus installer/evaluator regressions: exact no-mount profile, root marker, private cross-binding, no-host-SSH routing, short-I/O and lock cleanup, dedicated single-sentinel refusal, guarded provider-absence de-onboarding and exact retry | Focused local source validation passed; no VM start, credential transfer, provider action or external traffic |
| REQ-OBS-ROLLOUT | TST-1787850898631764 | Real filesystem generation/receiver tests; atomic candidate/job, typed receipt, rollback size bound; deadline integration four suites 199 passed | Local regression passed; no remote installation or power-loss claim |
| REQ-OBS-ACCEPTANCE | TST-1787850899238844 | Exact-source external four-profile run with runtime and path provenance | Pending reachable approved sentinel and dedicated AWG material |

## Evidence boundaries

- The final local gate includes controller environment/inventory isolation and
  the exact production Ansible variable loader. Exact-SHA hosted CI and Linux
  Molecule remain required; the local gate does not establish host acceptance.
- Implementation and local regression evidence are present. Exact-source hosted
  CI, deployment and traffic acceptance remain separate evidence categories.
- Real-vantage prerequisites: reachable approved sentinel, pinned clients, and
  dedicated active AWG private key. An offline sentinel or a revoked recovery
  key cannot satisfy them. Coordination previously approved one temporary
  staging VPS (target EUR 5, absolute total cap EUR 7, at most 48 hours) with
  provider-price verification, guarded cleanup and single-owner provisioning.
  That resource was subsequently guarded-destroyed and the authorization was
  consumed; no staging target is currently authorized, and creating another one
  requires fresh action-time confirmation.
- The former Raspberry Pi executor has been retired and is not a prerequisite.
  The approved replacement design for the one-shot acceptance run is a
  disposable systemd-capable Linux VM on the operator-owned Mac whose traffic
  exits through the current consumer uplink. Source now enforces the required
  non-default-profile/no-mount/no-port preflight, binds private executor evidence
  to the accepted report, and de-onboards the configuration, local assignment,
  dedicated client identity and exact profile only after bound guarded provider
  absence. Focused tests cover drift/refusal, report mismatch, route selection,
  SOPS/local cleanup ordering and retryable exact deletion. No VM was started and
  no credential transferred by this source change. A later approved run proves only the
  observed external consumer-uplink vantage; it is not independent physical-
  hardware, recurring, filtered-path quorum, or Android evidence. No replacement
  VM has been started or configured in this planning update.
- Dry-run means canonical candidate rendering/parsing and isolated installer
  orchestration tests without contacting a host, not `make dry-run` or Ansible
  check mode; those are not passive inspection. No live installer run occurred.
- Staging means isolated process/network-namespace lifecycle and rollback proof
  on an approved target, with no production route/firewall disruption.
- Live means passive collection against selected deployed nodes. Client means
  real external authenticated traffic, separately recorded per transport.
- Artifact evidence must bind the installed runner/profile generation and
  redacted report to exact source. Unit fixtures cannot stand in for that proof.
- Offsite destination is not configured. Existing local restore results, if
  obtained separately, do not close the offsite-backup requirement.
- The earlier arm64-Colima backup Molecule attempt failed before role
  convergence. Exact-main hosted Linux Molecule subsequently passed and closes
  only the configuration source gate. No production configuration, initial
  offsite copy, retention action, or remote restore was performed.

## Independent review

- Separate reviewers inspected installer/generation and runtime/evaluator paths.
  Confirmed findings were reproduced before fixes: unreadable oversized rollback
  state, nested deadline mismatch, failed-command version banners, premature
  network evidence, and partially created namespace cleanup.
- Final targeted reviews found no additional blocking issue. The configuration
  delta additionally fixed debug-before-Ansible ordering and verified real
  local repository decryption before any target configuration write. Its full
  local gate passed; exact-SHA hosted CI remains required. Local tests are not
  a substitute for external acceptance.
