# Change: Complete Critical and High External Acceptance Gates

Task ID: `EPC-1788891270457728`

## Why

Critical and High source behavior has reached protected main, but several
requirements still lack evidence from the environments they govern. Those
requirements were removed from the active portfolio by a terminal cancellation
batch even though the current completion objective requires externally blocked
work to remain open with a precise blocker. A single successor change is needed
to restore the real completion boundary without resurrecting terminal task IDs
or claiming that source and hosted checks prove staging, live fleet, current
transport, recovery, or cleanup behavior.

The owner narrowed this acceptance on 2026-09-28 to deployment and fleet
behavior. Android installation/device testing, alert drills, and offsite
copy/restore are excluded; their absence is not recorded as a pass.

## What Changes

- Establish one active acceptance contract that binds all external execution to
  a clean, exact protected-main source revision and deployable digest.
- Require guarded isolated staging, serial live-fleet convergence, SSH recovery,
  security verification, source-drift, authenticated four-transport traffic,
  fresh AmneziaWG evidence, guarded client/executor retirement, and verified
  provider cleanup as separate outcomes.
- Keep the successor task open when an external account, credential, target,
  client runtime or authorized executor required by this scope is unavailable, and
  record the exact blocker at the last safe boundary.
- Reconcile the unfinished acceptance obligations of the thirteen terminal
  Critical and High predecessor tasks without changing or reusing their IDs.
- No breaking production contract change is introduced; the change restores
  evidence and execution obligations for behavior already delivered to main.

## Capabilities

### New Capabilities

- `operations/critical-high-external-acceptance`: Exact-source orchestration and
  evidence rules for dry-run, staging, live fleet, authenticated client traffic,
  recovery, and cleanup across the remaining Critical and High scope.

### Modified Capabilities

- None.

## Impact

- Terraform provider environments and guarded staging cleanup manifests.
- Ansible inventory, deployment controller, SSH recovery, verification,
  security verification, source-drift, and recovery playbooks.
- SOPS-encrypted deployment inputs and private evidence files.
- Current client profiles, pinned client runtimes, four transport
  profiles, and fresh AmneziaWG acceptance workflow.
- External provider, fleet, and client
  execution environments; no external write is authorized unless its specific
  preflight, ownership, cost, and cleanup gates pass.
