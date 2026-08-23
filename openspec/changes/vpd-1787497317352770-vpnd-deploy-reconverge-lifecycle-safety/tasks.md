# VPD-1787497317352770: Guarantee secrets cleanup and scoped targeting on deploy paths

## Objective

Failed deploys still clean up plaintext secrets, limits are exact IPv4 targets, documented host resolution actually happens, and summaries stop printing secret paths.

## Ownership

- The primary agent owns vpnd/src/commands/{deploy,reconverge,doctor,probe,host}.rs, related tests, and this change's artifacts.

## Execution

- [ ] VPD-1787497373487307 Add failure-path cleanup execution to deploy and reconverge with failure-injection tests proving cleanup-after-failure and error precedence #bug !crit @item:VPD-1787497317352770
- [ ] VPD-1787497373490128 Validate registry ipv4 as an IPv4 literal before building --limit and reject pattern values with named records; unit test the rejection table #bug !high @item:VPD-1787497317352770
- [ ] VPD-1787497373493403 Resolve doctor/probe --host via a shared registry helper and replace summary path rows with placeholders; cover both in tests #bug !high @item:VPD-1787497317352770

## Verification

Use the exact gates and evidence categories in verification.md.
