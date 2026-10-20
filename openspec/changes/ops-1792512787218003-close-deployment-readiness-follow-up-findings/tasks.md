# OPS-1792512787218003: Close deployment readiness follow-up findings

## Objective

Close the operator-path and host-boundary findings from the pre-deployment
audit that `ANS-1792499727513191` left out, and keep every existing gate.

## Ownership

- Review lane: `scripts/blue-green.sh`, `vpnd/src/vpnd/commands/deploy.py`,
  `vpnd/src/vpnd/commands/reconverge.py`, their tests and notes.
- Environment lane: Makefile blue-green, promote-spare and watch-spare recipes,
  `scripts/deploy-controller.py`, `docs/RUNBOOK-rollback.md`, tests.
- Secret hygiene lane: `scripts/destroy.sh`, `docs/RUNBOOK-deploy.md`, tests.
- Host lane: `amneziawg`, `real-vps-awg-nat`, `firewall` and `nginx-xhttp`
  roles, Hetzner/Vultr/Scaleway variables, examples, Terraform tests, snapshots.
- Primary owns planning, task and board writes, review and commits.

## Execution

- [x] OPS-1792514260026468 Require review after blue-green and vpnd plans and dry-runs with prompt regressions #bug !high @item:OPS-1792512787218003
- [x] OPS-1792514260874788 Honor BLUE_ENV in blue-green and warm-spare Make recipes with conflict regressions #bug !high @item:OPS-1792512787218003
- [x] OPS-1792514261666762 Refuse deploy selections whose inventory env differs from ENV before secrets #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514262478677 Refuse an empty destroy hostname and remove the saved destroy plan on every exit #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514263378823 Clean decrypted secrets on failed re-deploy preflight and every deploy-block exit #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514264261067 Build AWG and sentinel Go sources with GOTOOLCHAIN=local and drop sentinel resolvconf #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514265195751 Admit only Debian 13 and Ubuntu 24.04 provider images and refuse older firewall hosts #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514266159002 Keep bearer paths out of nginx-xhttp redirect and Snell logs #bug !high @item:OPS-1792512787218003
- [ ] OPS-1792514267045582 Pass focused and complete local checks plus independent review #bug !high @item:OPS-1792512787218003

## Verification

- Local: each new regression fails on the parent commit and passes after the
  fix; focused pytest and vpnd tests, `make tf-test`, `make snapshot-check`,
  `./taskctl validate`, and `make check`.
- Remote CI: not requested in this change; a later PR records it.
- Dry-run/staging/live: not applicable; this change authorizes no deployment.
