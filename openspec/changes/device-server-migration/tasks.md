# OPS-1792673523985723: Migrate devices during server replacement

## Objective

Prepare usable replacement credentials, preserve every active subscription URL,
resume interrupted delivery and require explicit per-device path acceptance.

## Ownership

- Primary: migration controller/receipt modules, `scripts/blue-green.sh`, Makefile,
  `secrets/schema.json`, `contract/device-migration*`, controller tests, docs,
  shared CLAUDE guidance and all server task/spec lifecycle files.
- operations_audit: `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2`
  and `tests/unit/test_subscription_migration.py`; after runtime validation,
  `scripts/device_migration_credentials.py` and its dedicated unit tests;
  existing runtime tests only
  when directly required by the new API. Shared guidance changes go to primary.
- transport_audit: all client implementation/planning paths in the separate
  RIPDPI worktree; public contract is agreed with primary before either writer.
- No worker commits, pushes or changes shared task lifecycle independently.

## Execution

## Verification

Complete targeted suites, real local publisher and encrypted transaction tests,
four-baseline client path tests, receipt vectors, required local gates and
protected PR/main checks. Live/staging/physical-device deployment is out of scope.
- [x] OPS-1792674210176785 Implement exact private migration planning and target device credential preparation with encrypted transaction regressions #feature !high @item:OPS-1792673523985723
- [x] OPS-1792674211571053 Implement bounded publisher snapshot and idempotent CAS transfer rollback with real runtime tests #feature !high @item:OPS-1792673523985723
- [x] OPS-1792674212965582 Deliver resumable publication and blue-green retirement gating with integration regressions #feature !high @item:OPS-1792673523985723
- [ ] OPS-1792674215498584 Deliver shared receipt contract and integrate paired four-transport client export acceptance #feature !high @item:OPS-1792673523985723
- [x] OPS-1792674228402400 Verify the complete feature locally and through protected PR and exact-main CI with independent review #feature !high @item:OPS-1792673523985723
