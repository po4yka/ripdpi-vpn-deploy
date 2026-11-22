# OPS-1795327950629406: Create the private ops repository and map the operator kit onto it

## Objective

A private ops repository holds every non-secret operator input needed to run the public Make targets, pins the public repository by full SHA, and has a validator that rejects plaintext secrets; every operator kit item has one recorded authority.

## Ownership

`docs/how-to/local-operator-kit.md`, `docs/reference/ops-repository.md`, `docs/README.md` (index row), `templates/ops-repo/**`, `scripts/validate-ops-repo.py`, `tests/unit/test_validate_ops_repo.py`. The live step owns only the new private repository. No shared-file lane conflict: W1 touches no `Makefile` or `mise.toml`. Own the Make, inventory renderer and deploy controller path changes.

## Execution

- [ ] OPS-1795328275356745 Document the ops repository contract and the kit mapping onto the ops repository and B2 #feature !high @item:OPS-1795327950629406
- [ ] OPS-1795328289814121 Add the ops repository template with the public SHA pin and a layout validator with tests and wire external inputs through Make and the deploy controller with two-checkout tests #feature !high @item:OPS-1795327950629406
- [ ] OPS-1795328305307912 Create the private repository and prove the required-reviewer gate before importing the non-secret kit material (authorized live step) #feature !high @item:OPS-1795327950629406

## Verification

Local: `python3 -m pytest tests/unit/test_validate_ops_repo.py`, `make docs-check`, `./taskctl validate`. Remote CI: the public PR checks. Live (authorized): validator and gitleaks pass in the new private repository; the MacBook comparison of `make inventory` output between kit and ops clone is recorded as a receipt in the ops repository. Run an authorized staging dry-run with the external inventory and compare host selection to the kit.
