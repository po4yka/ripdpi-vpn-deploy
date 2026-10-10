# SEC-1791545689674403: Repair critical Ansible role audit security and availability paths

## Objective

Repair or verify all eleven critical audit paths and prepare a source PR with
positive local behavior, independent review and exact-source CI evidence.

## Ownership

- Host worker: `ansible/roles/{xray,monitoring,geodata,backup,subscription-host}/`
  and their directly associated unit/Molecule regressions. Baseline resolver
  may be read and verified, but only change it if a remaining P1 cause is proven.
- Receiver worker: `ansible/roles/observability_deadman/` and
  `tests/unit/test_observability_deadman.py`, new receiver safety regressions,
  and the exact generation fixture caller in `test_observability_deadman_pipeline.py`; read/verify existing collector
  authority activation. No retired monitoring topology is enabled.
- Primary: `ansible/roles/watchdog/`, watchdog unit tests and new notifier
  tests, its credential-bearing caller in `ansible/playbooks/verify.yml`; all
  OpenSpec/task files, fixture shared lanes, snapshots and final gates.
- Shared lanes: root serializes `tests/snapshot/`, `scripts/template_render.py`,
  schema/example inputs and any CI changes. Workers request these changes;
  they never overwrite concurrent edits, stage files or commit.

## Execution

- [x] SEC-1791545814181293 Repair Xray log lifecycle, backup profile inputs and subscription authority #bug !crit @item:SEC-1791545689674403
- [x] SEC-1791545814693187 Harden retained dead-man TLS acceptance and generation-bound replay #bug !crit @item:SEC-1791545689674403
- [x] SEC-1791545815210908 Bound watchdog notification duration and protect sender credentials #bug !crit @item:SEC-1791545689674403
- [x] SEC-1791545815774612 Verify existing DNS and collector revocation repairs and all role regressions #bug !crit @item:SEC-1791545689674403
- [x] SEC-1791545816326788 Complete independent security review, full checks and exact-source PR evidence #bug !crit @item:SEC-1791545689674403

## Verification

Focused behavior/failure tests and available affected-role Molecule; intended
snapshot review/check; full build-gated `make check`; independent security
review; exact-source PR CI. Source-only scope: no remote dry-run, provider,
staging/live rollout, authenticated client or human notification acceptance.
