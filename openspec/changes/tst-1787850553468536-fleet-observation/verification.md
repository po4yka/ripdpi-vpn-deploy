---
task_id: TST-1787850553468536
change: tst-1787850553468536-fleet-observation
commit_sha: null
local: not_applicable
local_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
staging: not_applicable
staging_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
live: not_applicable
live_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
client: not_applicable
client_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
artifact: not_applicable
artifact_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OBS-PASSIVE | TST-1787850885266502 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-SSH | TST-1787850885266502 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-EVIDENCE | TST-1787850885266502 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-RESTORE | TST-1787851685101244 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-BACKUP-CONFIG | TST-1787916690652478 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-BACKUP-QUIESCENCE | TST-1787916690652478 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-OFFSITE-PROOF | TST-1787916691156561 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-PATH | TST-1787850896670736 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-XHTTP | TST-1787850897343789 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-IDENTITY | TST-1787850897969705 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-LIFECYCLE | TST-1787850898631764 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-DISPOSABLE-EXECUTOR | TST-1787850899238844 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-ROLLOUT | TST-1787850898631764 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-ACCEPTANCE | TST-1787850899238844 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |

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

## Disposable executor configuration regression (2026-09-04)

- An actual Colima 0.10.3 prepare refused with `executor-config` before
  manifest publication. Its owned profile was deleted; Docker context remained
  unchanged. No credentials, bindings or traffic probes were installed.
- Colima stores `portForwarder` at the top level of its configuration. The
  validator and its fixture incorrectly used `network.portForwarder`. Matching
  the real layout reproduced the refusal in the existing positive test; the
  corrected lookup passes while absent, SSH and gRPC forwarding still refuse,
  even with a nested `none` lookalike. Other isolation predicates are unchanged.
- Executor and Make suites: 46 PASS. This is source regression evidence;
  successful real executor preparation and external protocol acceptance remain
  separate gates.
- The next actual preparation passed configuration validation but refused at
  `executor-status`, again deleting the owned profile without manifest or
  credential publication. Colima's `status --json` describes driver/socket
  details; named lifecycle state comes from `list --json`. Preparation/live
  validation and de-onboarding now share exact-name NDJSON selection, reject
  missing/duplicate/invalid records, and require Running for live use.
- Corrected executor/Make/promotion suites: 104 PASS. Read-only parsing of the
  installed CLI's named Stopped record and existing private configuration passed;
  this does not credit a running executor or any guest traffic.
- Actual canonical preparation on source `5b8a9dff0e51739514c004667142180b4bf8fba5`
  completed with exit 0; a subsequent canonical live revalidation passed. Real
  configuration, exact named Running state, no mounts, systemd PID1, passwordless
  sudo and matching root marker all passed. Manifest mode was 0600; Docker
  context/config hashes were unchanged. Expiry was 21:06:20 UTC, below the
  original 21:06:50 UTC cap; it was not renewed. Result artifact SHA-256:
  `5932777ffcbca8e9ede20e068d5429c781127ecb8a6607654276f6ee02a65397`. The executor remains allocated for the approved one-shot
  run; this proves preparation only, not client tool installation, credentials,
  protocol traffic, de-onboarding, production or recurring acceptance.
