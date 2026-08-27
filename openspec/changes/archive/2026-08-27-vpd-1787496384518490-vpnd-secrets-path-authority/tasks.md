# VPD-1787496384518490: Make vpnd the single authority for the decrypted secrets path and redaction

## Objective

One resolved secrets path everywhere: make receives it explicitly, doctor redacts it on every export surface, hardening failures are fatal, and the permission gate reads what it stats.

## Ownership

- The primary agent owns `vpnd/src/config.rs`, `vpnd/src/runner/make.rs`, `vpnd/src/commands/{doctor,share,preflight,reconverge}.rs`, `vpnd/src/secrets.rs`, their tests, and this change's artifacts.

## Execution

- [x] VPD-1787497013454189 Thread SECRETS_FILE through make::target/target_with for decrypt and consuming targets; add resolution-matrix tests (XDG set/unset) proving no double-decrypt #bug !high @item:VPD-1787496384518490
- [x] VPD-1787497013472302 Derive doctor redaction from the resolved path, apply it to the --ai prompt path, and extend proptest/doctor_bundle tests to non-/tmp shapes #bug !high @item:VPD-1787496384518490
- [x] VPD-1787497013490086 Make secure_secrets_file fallible and propagate at all three call sites with a test for the read-only-parent failure #bug !high @item:VPD-1787496384518490
- [x] VPD-1787497013509056 Switch secrets/token gates to open-once fstat reads with symlink and mode rejection tests #bug !high @item:VPD-1787496384518490

## Verification

Use the exact gates and evidence categories in verification.md.
