## Context

The producer emits a single hopping range and fixed interval for official sing-box. RIPDPI export stops before payload construction. The paired client change implements the missing native destination-port socket adapter and validated import model.

## Goals / Non-Goals

- Goal: export the complete existing policy to a qualified RIPDPI client and reject invalid intervals before publication.
- Non-goal: expand fleet configuration to multiple ranges or random intervals, deploy infrastructure, or issue real device credentials.

## Decisions

- Retain the existing producer wire shape: `server_ports`, `hop_interval`, and matching `ripdpi.hysteria_extras[tag].port_hopping`. Both consumers use the hopping set instead of widening it with the scalar port.
- Require exact whole-millisecond intervals from 5000 through 9223372036854 milliseconds. Keep the existing whole-number seconds, minutes, or hours grammar and use checked integer unit conversion. Reject fractional or finer-unit input instead of rounding. These bounds match the paired client and the upstream signed duration representation.
- Keep official sing-box behavior and unrelated transport guards intact. Do not add a second client compatibility path.
- Merge the client before removing the producer refusal. Qualification uses the pinned real Hysteria server and positive traffic across three scheduled remote-port changes. A local UDP source rebind does not meet this bar.

## Contracts and ownership

- Primary agent owns `scripts/client_payload.py`, producer tests, affected guidance, and this task's artifacts.
- Client native and Kotlin agents own disjoint paths under `po4yka/RIPDPI#OUT-1792820412611017`; shared catalogue changes follow the independently tested stored-policy fix.
- Terraform, cloud-init, Ansible runtime, secrets structure, and fleet state do not change. The bundle schema retains its current shape.
- Checks: targeted recipient and emitter tests, task and strict specification validation, federation, then `make check` through the machine build gate.

## Risks / Trade-offs

- An older client cannot use the new export: require the paired client merge and positive qualification before producer merge.
- Duration parsing can admit values that change in transit: use exact unit conversion and reject sub-millisecond precision and overflow.
- Producer tests cannot prove QUIC continuity: record real client/server acceptance separately from local generation proof.

## Migration Plan

No producer data migration is required. The paired client applies a checked one-way migration for dormant hopping fields before typed catalogue decode. Invalid stored state remains unchanged and the operation fails. A source revert can restore the producer refusal without changing any published recipient or credential. No live rollback is authorized by this source change. Keep both tasks open until their required positive tests and terminal hosted checks pass.
