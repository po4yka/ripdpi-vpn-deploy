# TFR-1791469128152528: Select the actual Vultr Debian 13 image

## Objective

Provision the intended supported base image by its verified provider ID.

## Ownership

Vultr variables, examples, mock-provider tests and adjacent provider notes;
this task's issue, generated board and OpenSpec artifacts. One serialized writer.

## Execution

- [x] TFR-1791469302312711 Correct approved image identities and exercise accepted and refused Vultr plans #bug !high @item:TFR-1791469128152528
- [ ] TFR-1791469302916838 Verify accepted source and actual disposable Debian 13 SSH foundation #bug !high @item:TFR-1791469128152528

## Verification

Focused Vultr Terraform mock tests, Conftest policies, applicable hooks, exact-head
hosted CI, and the actual authorized replacement's OS and strict SSH foundation.
Mock plans do not count as live or client acceptance.
