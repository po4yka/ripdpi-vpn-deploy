# TST-1787850553468536: Deliver authenticated fleet probes and passive inspection

## Objective

Deliver passive fleet reads and a separately invoked four-profile client probe.
Implementation is present; source validation and independent review precede
publication. External acceptance remains a separate open execution step.

## Ownership

Primary owns Makefile, inspector, liveness installer/runner/evaluator, matrix
curl adapter, configuration contract, docs, and their tests in this worktree.
The backup restore template and its contract tests belong to the bounded cleanup
slice. Shared files are serialized. Other agents review without editing. No provider,
server firewall, production SSH, backup retention, or unrelated task changes.
The backup configuration delta owns the dedicated playbook, shared backup
configuration tasks, Make target, and related tests/docs in
`codex/backup-configure-20260828`; it does not own inventory-worker changes.

## Execution

- [x] TST-1787850885266502 Implement passive scoped SSH inspection with redacted freshness evidence and no-repair tests #feature !high @item:TST-1787850553468536
- [x] TST-1787850896670736 Implement curl path isolation in sentinel and matrix adapters with real loopback bypass regressions #feature !high @item:TST-1787850553468536
- [x] TST-1787850897343789 Implement pinned Xray XHTTP onboarding with real emitter and runtime parser checks #feature !high @item:TST-1787850553468536
- [x] TST-1787850897969705 Implement dedicated client and explicit AWG target validation with private key handoff tests #feature !high @item:TST-1787850553468536
- [x] TST-1787850898631764 Implement transactional sentinel installation and bounded probe cleanup with failure tests #feature !high @item:TST-1787850553468536
- [ ] TST-1787850899238844 Run local gates and approved external four-protocol acceptance with exact source and runtime evidence #feature !high @item:TST-1787850553468536

## Verification

Tests-first extensions to the existing liveness/matrix suites, new passive
collector tests, real pinned client parser checks, `make validate`, `make ci-fast`,
independent review, and actual external traffic for all four transports. Heavy
checks use `build-gate --`. Hosted CI and live/client acceptance are separate
evidence categories. No installation or scheduling is implied by planning PASS.
- [x] TST-1787851685101244 Fix restore cleanup ownership with existing-target and failed-restore regressions #bug !high @item:TST-1787850553468536
- [x] TST-1787916690652478 Implement a configuration-only offsite backup command with quiescence and real regression tests #feature !high @item:TST-1787850553468536
- [ ] TST-1787916691156561 Verify approved initial offsite copy and isolated remote restore without retention pruning #feature !high @item:TST-1787850553468536
