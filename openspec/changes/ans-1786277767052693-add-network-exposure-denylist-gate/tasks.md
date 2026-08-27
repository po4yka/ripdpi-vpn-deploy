# ANS-1786277767052693: Implement a disabled-by-default network exposure denylist gate

## Objective

Deliver the validated, redacted, non-mutating review path and disabled-default Ansible integration described by the linked portfolio task and delta specification.

## Ownership

- Own a dedicated role, placeholder fixtures, focused unit/Molecule tests, and operator documentation.
- Serialize edits to shared group variables, the site playbook, firewall templates, and any secrets schema.

## Execution

- [x] ANS-1786277767052018 Define feed metadata and directional policy schemas with placeholder-only fixtures !high #feature @item:ANS-1786277767052693
- [x] ANS-1786277767052243 Implement fail-closed validation and disabled-default Ansible integration !high #feature @item:ANS-1786277767052693 @blocked_by:ANS-1786277767052018
- [x] ANS-1786277767052707 Add redacted dry-run, log-only, canary, expiry, and rollback behavior !high #feature @item:ANS-1786277767052693 @blocked_by:ANS-1786277767052243
- [ ] TST-1786277767052610 Prove disabled render parity, invalid-input failure, redaction, idempotence, and rollback !high #feature @item:ANS-1786277767052693 @blocked_by:ANS-1786277767052707
- [ ] DOC-1786277767052241 Document reviewed artifact refresh, promotion criteria, traffic scope, and no hidden apply path !high #feature @item:ANS-1786277767052693 @blocked_by:TST-1786277767052610

## Verification

Use the exact gates and evidence categories in `verification.md`. Completion of these checkboxes advances the portfolio record at most to `review`.
