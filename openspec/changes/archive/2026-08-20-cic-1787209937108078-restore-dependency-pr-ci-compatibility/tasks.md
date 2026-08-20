# CIC-1787209937108078: Restore dependency PR CI compatibility gates

## Objective

Restore a green, fail-closed dependency-update path with local task-contract
validation and a refreshed immutable Debian 13 Molecule image.

## Ownership

- The primary agent owns the workflow, image recipe, image references, focused
  tests, portfolio task, and this OpenSpec change in this dedicated worktree.
- Workflow, image-reference, task, and generated-board edits are serialized.
- No parallel writer may edit these shared paths.

## Execution

- [x] CIC-1787209937108079 Remove the retired peer checkout from task-contract CI while preserving local base-history validation and add a regression test for the peer-free route #bug !high @item:CIC-1787209937108078
- [x] CIC-1787209937108080 Add the pinned Debian 13 Molecule image recipe and fail-closed publish/scan workflow, then publish a verified immutable digest #feature !high @item:CIC-1787209937108078 @blocked_by:CIC-1787209937108079
- [x] CIC-1787209937108081 Switch every Debian 13 Molecule scenario and its pin contract to the verified owned digest; run focused YAML and image-pin checks #bug !high @item:CIC-1787209937108078 @blocked_by:CIC-1787209937108080
- [x] CIC-1787209937108082 Run local CI gates, observe hosted repair CI, rerun Dependabot PR checks, and merge #75 and its Dependabot-superseding PR #79 only after all required checks succeed #bug !high @item:CIC-1787209937108078 @blocked_by:CIC-1787209937108081

## Verification

Use the exact gates and evidence categories in `verification.md`. Hosted CI
on the repair SHA and on each merged Dependabot SHA is required before closing.
