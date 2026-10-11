## Context

The audit at cf01f94a found sixteen repair cases described in proposal.md and
the audit-boundary-correctness delta. Work is limited to source fixes and a PR.

## Goals / Non-Goals

- Goal: enforce the existing identity, ownership, recovery and publication contracts.
- Goal: exercise each repaired trigger and relevant rejection or retry boundary.
- Non-goal: live infrastructure, credential changes, new transports or schema migration.

## Decisions

- Refresh requires the exact client name and existing prefix match; ambiguous state refuses.
- Runtime retirement declares exact metric-file owners. Root ancestry and other authority checks remain mandatory.
- Logrotate uses existing targeted generation recovery only when guarded; unguarded Xray retains direct recovery.
- IPv6 control allowances retain protocol and link constraints; strict default drop remains.
- Verification and watchdog share normalized AWG instance selection.
- Host-specific CLI diagnostics propagate explicit addresses; global checks must not claim host-specific evidence.
- Share resolves its effective listener through the canonical resolver and publishes QR references only when QR output is requested; stale owned QR files are removed safely.
- Approval generation publication and consumption use a stable private shared lock.
- New releases remain draft until complete verified assets exist. Ensure dispatch has a resolvable tag before build.
- Synthetic tests isolate their own Git configuration and explicit file group authority. Real repository hooks and signing stay enabled.
- Socket-activated bootstrap refreshes generated units and the active socket before declaring readiness.

## Contracts and ownership

- Runtime worker owns the five Ansible defects, their role/playbook files, local role notes and direct regressions/snapshots.
- Operator worker owns issuer, rotation, promotion/watcher, Make verification admission, scripts/CLAUDE.md and direct regressions.
- Infrastructure worker owns release installer/workflows, shared cloud-init, fixture isolation/group fixes and direct regressions/subtree notes.
- Primary owns vpnd host/share behavior, task/spec artifacts, vpnd notes/tests, root tests/CLAUDE.md and final integration.
- Shared files are serialized: primary merges additional scripts/CLAUDE.md notes after operator completion; Makefile belongs only to operator during implementation.
- No worker commits, stages other lanes, changes task lifecycle or edits another lane without coordination.

## Risks / Trade-offs

- Cross-layer recovery changes can affect live sessions; add targeted transition tests and retain separate live acceptance.
- Draft release tags must exist before dispatch; verify against the pinned action and workflow regression.
- Local macOS cannot establish Linux packet/systemd behavior alone; run available native tests and report any missing gates.
- Broad repair scope requires per-case evidence plus complete make check and independent review.

## Migration Plan

No secrets schema or public CLI migration is intended. Existing private lock files
may be safely hardened only after ownership/type admission. Regenerate recipient
bundles to adopt corrected URLs and QR state. Runtime changes take effect only in
a separately authorized deployment. Source rollback is a revert; runtime rollback
uses the existing reviewed deployment lifecycle. Run focused tests, snapshot-check,
make check, independent review and exact-source CI before claiming full source acceptance.
