# CIC-1792911952227614: Apply layered repository rules and release protection

## Objective

Apply all seven approved improvements and retain only the owner PR-only CI bypass.

## Ownership

Primary: `.github/`, `scripts/configure-repository.py`, matching tests, CONTRIBUTING, and policy/release/testing runbooks. Task records are serialized through taskctl. No parallel writers.

## Execution

- [x] CIC-1792912060113090 Implement and verify layered rulesets release integrity dependency updates and squash merging #feature !high @item:CIC-1792911952227614

## Verification

Targeted pytest, workflow/YAML lint, `build-gate -- make check`, remote policy readback and an empty second plan. Open a PR without merging. No infrastructure or device acceptance is in scope.
