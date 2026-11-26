# SCR-1795705796387934: Carry a per-entry allowlist-regime survivability label in the client bundle

## Objective

Each transport entry of the client bundle carries a label (yes, no, unknown) that says whether its transport class can pass under an allowlist regime. The client stops spending attempts on entries that cannot pass.

## Ownership

`contract/`, `scripts/` bundle files, `docs/reference/ripdpi-bundle.md`. Serialized after D4. One writer.

## Verification

Planning: `./taskctl validate`, strict OpenSpec validation and `make docs-check`. Implementation: the narrow tests of the touched area, then `make check`. Client (po4yka/RIPDPI#DAT-1795704964813672) reads the label and skips a no entry under a detected regime.

## Execution

- [ ] SCR-1795705817694863 Decide v3 amendment or version bump, then change the schema and validator with negative fixtures #feature @item:SCR-1795705796387934
- [ ] SCR-1795705839786234 Add the class table and emit the label with tests for UDP, TLS-over-TCP and unlisted classes #feature @item:SCR-1795705796387934
- [ ] SCR-1795705867085474 Update docs/reference/ripdpi-bundle.md and sync the vendored copy with the client copy (po4yka/RIPDPI#DAT-1795704964813672) #feature @item:SCR-1795705796387934
