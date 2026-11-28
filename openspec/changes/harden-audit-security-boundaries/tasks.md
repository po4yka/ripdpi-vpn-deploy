# SEC-1795866391476569: Enforce deployment security boundaries

## Objective

Resolve all findings from the attached deployment audit.

## Ownership

Ansible roles and group variables, secret tooling and schema, client payload, provider policies and their tests.

## Execution

- [x] SEC-1795866483462088 Repair and verify deployment audit security boundaries #bug !high @item:SEC-1795866391476569

## Verification

Run the relevant unit tests, snapshots, native HTTP test, Conftest and `make check`. Obtain hosted CI for the pull request.
