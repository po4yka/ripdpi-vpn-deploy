# ANS-1787422293187845: Decommit the production decoy domain from group_vars

## Objective

The committed tree no longer carries the production decoy identity: cohort
profiles pin `public_site_canonical_url` to the neutral placeholder, the real
origin flows through the validated `ANSIBLE_EXTRA_VARS_FILE` override, and
rotation is a secrets-plus-local-file operation that never touches git.

## Ownership

- The primary agent owns `ansible/group_vars/vpn-p1-web.yml`,
  `ansible/group_vars/vpn-p2-udp.yml`,
  `scripts/validate-ansible-extra-vars.py`,
  `tests/unit/test_public_site_contract.py`,
  `tests/unit/test_validate_ansible_extra_vars.py`,
  `docs/DEPLOY-PROFILES.md`,
  `docs/REALITY-TARGET-RESEARCH-2026-07-12.md`, and this change's artifacts.
- No role templates, rendered artifacts, or secrets schema keys change; the
  converge-time role asserts remain the fail-closed backstop.

## Execution

- [x] ANS-1787422768124258 Replace the committed decoy domain with the neutral placeholder in both cohort profiles and redact the registered domain from the committed REALITY target research note #bug !high @item:ANS-1787422293187845
- [x] ANS-1787422768125988 Allowlist `public_site_canonical_url` in scripts/validate-ansible-extra-vars.py with strict https-origin validation and extend tests/unit/test_validate_ansible_extra_vars.py for accepted and rejected shapes #feat !high @item:ANS-1787422293187845
- [x] ANS-1787422768126654 Add a contract test pinning every committed group_vars profile to the placeholder origin so a registered domain cannot re-enter version control #test !high @item:ANS-1787422293187845
- [x] ANS-1787422768127223 Document the decoy-origin override workflow in docs/DEPLOY-PROFILES.md including mode-0600 file handling and the fail-closed assert behavior #docs !high @item:ANS-1787422293187845
- [x] ANS-1787422768128553 Run named gates: focused pytest files, full pytest tests/unit, make validate #test !high @item:ANS-1787422293187845

- [x] ANS-1787458582373507 Remediate PR review: redact the measured domain as an explicit placeholder that preserves historical observations, add mkdir for the ignored override directory, pass the override to the documented dry run, and list every secret that rotates with the origin #docs !high @item:ANS-1787422293187845

## Verification

Use the exact gates and evidence categories in `verification.md`.
