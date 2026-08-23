# SEC-1787497526094023: Validate make variable values against make expansion metacharacters

## Objective

One choke point validates every make variable value; nothing that can execute or unquote inside a recipe shell reaches a spawned invocation.

## Ownership

- The primary agent owns vpnd/src/runner/make.rs, its call sites in commands/, related tests, and this change's artifacts.

## Execution

- [ ] SEC-1787497526525445 Implement the per-key allowlist validator in the make runner and wire it into target_with with abort-before-spawn errors #bug !high @item:SEC-1787497526094023
- [ ] SEC-1787497526527350 Add acceptance/rejection table tests per key (CLIENT, HOST, TARGET_ID, MATRIX_CONFIG, PLAN, ENV, PROVIDER) and audit each call site for the right key class #bug !high @item:SEC-1787497526094023

## Verification

Use the exact gates and evidence categories in verification.md.
