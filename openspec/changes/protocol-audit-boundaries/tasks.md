# SEC-1792301529650686: Repair protocol identity and delivery audit boundaries

## Objective

Repair all eight confirmed audit findings and retain the current safety gates.

## Ownership

- Proxy worker owns VLESS UUID admission, Snell/Trojan templates and their tests
  and role notes. It owns transport_semantics.py cohort changes first.
- UDP worker owns AWG address admission, binding regressions and AWG notes.
  It waits for proxy release before editing transport_semantics.py.
- Delivery worker owns client_payload.py, subscription.conf.j2, vpnd share URLs,
  their tests, subscription-host notes and vpnd notes.
- Primary owns certificate preflight/tests, shared scripts/tests/Ansible notes,
  snapshots, all planning/task/board writes, review, commits and GitHub actions.
- Workers never stage, commit, run task lifecycle commands or revert other work.

## Execution

- [ ] SEC-1792301639236422 Protect every subscription vhost outcome and add native logging regressions #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301639972825 Generate served sing-box import and QR targets with delivery regressions #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301641075453 Reject pinned Xray authentication UUID aliases with identity regressions #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301641874277 Reject AWG peer claims covering any instance server address #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301642634281 Preserve Snell and Trojan credential bytes in all JSON consumers #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301643438614 Refuse unsupported RIPDPI Hysteria hopping before publication #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301644239886 Verify exact certificate SAN coverage with negative wildcard regressions #bug !high @item:SEC-1792301529650686
- [x] SEC-1792301645045399 Retain Hysteria extension metadata for every emitted host #bug !high @item:SEC-1792301529650686
- [ ] SEC-1792301645900459 Pass focused and complete local checks plus security and structured review #bug !high @item:SEC-1792301529650686
- [ ] SEC-1792301646714747 Pass PR CI merge the reviewed source and verify all required main checks #bug !high @item:SEC-1792301529650686

## Verification

- Local: failing boundary controls, focused pytest and vpnd tests, snapshots,
  task validation, shell checks, complete make check and security review.
- Remote CI: complete PR run, then every protected-main context on its exact SHA.
- Client/artifact: synthetic recipient contracts, real local nginx/backend and
  pinned-engine acceptance through the existing hosted native lanes.
- Dry-run/staging/live: not applicable; this change authorizes no deployment.
