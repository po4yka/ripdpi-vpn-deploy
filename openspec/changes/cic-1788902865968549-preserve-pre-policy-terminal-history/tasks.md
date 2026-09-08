# CIC-1788902865968549: Preserve pre-policy terminal history validation

## Objective

Version committed-review enforcement so pre-activation terminal history remains
valid and every post-activation transition stays fail-closed.

## Ownership

Primary owns `tools/tasking/project.json`, `scripts/tasks/taskctl.py`, its task
contract documentation and tests, and this change's portfolio and OpenSpec
artifacts. Shared task files are updated serially through `taskctl`.

## Execution

- [x] CIC-1788902865976092 Define the historical policy contract and verification boundary #bug @item:CIC-1788902865968549
- [x] CIC-1788902886972517 Version committed-review enforcement across historical terminal transitions #bug @item:CIC-1788902865968549

## Verification

Local taskctl regressions and base-aware validation are required. Hosted CI,
code review, and security review must pass on the exact protected PR head.
Runtime, provider, staging, live, client, and artifact evidence are not
applicable because the change affects only repository task lifecycle behavior.
- [x] CIC-1788905312419658 Prevent post-activation policy downgrade and satisfy required OpenSpec review #bug !high @item:CIC-1788902865968549
- [x] CIC-1788906708701940 Keep unversioned peers strict and constrain legacy done sources #bug !high @item:CIC-1788902865968549
