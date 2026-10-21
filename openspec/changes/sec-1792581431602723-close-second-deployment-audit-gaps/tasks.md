# SEC-1792581431602723: Close second deployment audit secrets and lifecycle gaps

## Objective

Close the four defects from the second pre-deployment audit at `03033beb` and
keep every existing gate.

## Ownership

- vpnd lane: `vpnd/src/vpnd/commands/`, `vpnd/tests/test_deploy_lifecycle.py`,
  `vpnd/CLAUDE.md`.
- Vultr lane: `terraform/providers/vultr/` root, tests and notes.
- Play lane: `ansible/playbooks/` smoke-test, verify and security-verify,
  the shared env task, Makefile recipes, `tests/unit/test_operator_verb_scope.py`,
  `ansible/CLAUDE.md`.
- Hetzner lane: `terraform/providers/hetzner/` root, variables, examples,
  tests and notes; blue-green guidance.
- Primary owns planning, task and board writes, review and commits.

## Execution

- [x] SEC-1792581854245311 Keep vpnd plaintext cleanup active from decrypt until cleanup with signal regressions #bug !high @item:SEC-1792581431602723
- [x] SEC-1792581855014542 Refuse Vultr os_id changes before an in-place reinstall with lifecycle regressions #bug !high @item:SEC-1792581431602723
- [x] SEC-1792581856404337 Bind smoke-test verify and security-verify plays to the selected ENV with refusal regressions #bug !high @item:SEC-1792581431602723
- [ ] SEC-1792581857264775 Reuse an existing Hetzner project SSH key for additional environments with plan regressions #bug !high @item:SEC-1792581431602723
- [ ] SEC-1792581857974419 Pass focused and complete local checks plus independent review #bug !high @item:SEC-1792581431602723

## Verification

- Local: each new regression fails on the parent commit and passes after the
  fix; focused pytest and vpnd tests, `make tf-test`, `make vpnd-test`,
  `./taskctl validate`, and `make check` (Docker-dependent steps run in CI).
- Remote CI: a later PR records it.
- Dry-run/staging/live: not applicable; this change authorizes no deployment.
