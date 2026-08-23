# VPD-1787497426503364: Align vpnd operator output contract: man page, json flag, clip flag, doctor resilience

## Objective

Documented surface equals actual surface, and doctor diagnostics are complete and failure-tolerant.

## Ownership

- The primary agent owns vpnd/build.rs, vpnd/src/cli.rs, vpnd/src/commands/{doctor,host}.rs, vpnd/src/runner/process.rs, vpnd/tests/{completions_snapshot,doctor_bundle}.rs, and this change's artifacts.

## Execution

- [ ] VPD-1787497435906087 Generate the man page from the real clap Command with a parity gate replacing the build.rs replica #bug @item:VPD-1787497426503364
- [ ] VPD-1787497435909140 Decide and implement --json: emit JSON for host list/show and probe-matrix report path, or remove the flag; help text and tests updated either way #bug @item:VPD-1787497426503364
- [ ] VPD-1787497435912334 Declare clap requires(ai) for --clip and add the misuse-error test #bug !low @item:VPD-1787497426503364
- [ ] VPD-1787497435914528 Make doctor capture stderr, continue past failed steps, mark them, and exit nonzero on failures; extend doctor_bundle tests #bug !high @item:VPD-1787497426503364

## Verification

Use the exact gates and evidence categories in verification.md.
