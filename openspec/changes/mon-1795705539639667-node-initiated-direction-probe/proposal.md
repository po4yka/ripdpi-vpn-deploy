# Change: Probe node-initiated connections from the liveness sentinel to separate one-way from two-way blocks

Task ID: `MON-1795705539639667`

## Why

Initiation direction is the main variable that public VPS-block reports leave unrecorded. One public report dated 2026-11-21 described a direction-dependent stateful block on one host: connections that the host started failed while connections toward it passed. Treat this as single-source and unverified.

The sentinel today tests the client direction only. Block detection (`MON-1795086646495369`, D5) joins sentinel success with client failures. With a node-initiated result it can also say whether the block acts in one direction or in both. Part of the field analytics theme of epic `EPC-1795085241910080`, but filed as a separate task so the epic scope does not grow.

## What Changes

- Add a bounded node-side probe for connections that the node starts toward configured domestic targets. Export the stage result with a direction label.
- Let the D5 hint text use the direction label. The hint stays advice for the PLAN output of `scripts/fleet-rotate.sh`.
- Overlap: `fleet-health-rotation` owns rotation and does not change. D3 (`MON-1795086175387484`) owns the client-direction probes and does not change. Order: implement after D3 and D5 land.

## Capabilities

### New Capabilities

- `operations/node-initiated-direction-probe`: node-initiated connection probe and its direction label.

### Modified Capabilities

- None.

## Impact

- Ansible: the node-side exporter pattern and `ansible/roles/observability_control_plane/` alert annotations.
- Docs: `docs/reference/protocol-liveness.md` and `docs/reference/observability-operations.md`.
