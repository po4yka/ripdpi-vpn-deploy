# ANS-1791461761742804: Pass first subscription host dry-run

## Objective

Complete the first subscription-host dry-run while preserving real activation.

## Ownership

Primary writer owns ansible/roles/subscription-host/tasks/main.yml, handlers/main.yml, its CLAUDE.md, focused tests and these artifacts. Preserve other work and serialize live source/inventory changes.

## Execution

- [x] ANS-1791461940464917 Defer only planned absent subscription service activation during first check mode #bug !high @item:ANS-1791461761742804
- [ ] ANS-1791461941073032 Verify fresh and loaded service guards then complete real P1 dry-run and deployment #bug !high @item:ANS-1791461761742804

## Verification

Focused guard tests, Ansible lint/syntax and snapshots; real role convergence; terminal exact-source CI; actual fresh P1 dry-run, deploy/verify/security and authenticated XHTTP. Required evidence stays open until observed.
