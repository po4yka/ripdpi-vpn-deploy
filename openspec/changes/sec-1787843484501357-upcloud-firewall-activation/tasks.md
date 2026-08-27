# SEC-1787843484501357: Preserve DNS while enforcing the provider firewall

## Objective

Require active UpCloud enforcement with narrowly scoped DNS reply rules.

## Ownership

The primary agent owns Terraform source, tests, task state, and integration.
The reviewer is read-only. Production operations are excluded from this change.

## Execution

- [x] SEC-1787848592308718 Encode explicit activation and narrow DNS reply policy with failing-then-passing UpCloud mock regressions #bug !high @item:SEC-1787843484501357
- [ ] SEC-1787848592326717 Validate source and document safe activation ordering with independent review and hosted CI #bug !high @item:SEC-1787843484501357
- [ ] SEC-1787848592344772 Review an authorized live plan and verify exact-source activation without replacement or connectivity loss #bug !high @item:SEC-1787843484501357

## Verification

Mock-provider tests, Terraform formatting/validation, make validate, task checks,
and hosted CI precede any separately authorized live plan or apply.
