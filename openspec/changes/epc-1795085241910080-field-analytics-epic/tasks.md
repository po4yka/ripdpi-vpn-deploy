# EPC-1795085241910080: Field analytics program: client field reports, per-protocol probes and block detection

## Objective

Coordinate D1 to D7 so the operator can tell a server failure from a network block per ASN and protocol, using opt-in anonymous client reports.

## Ownership

The planner owns the epic and its dependency edges. Each child task owns its own paths. Shared files are serialized in the order D1, D3, D4, D2, D5, D6.


## Execution

- [ ] EPC-1795085507364840 Track child tasks D1 to D7 and keep their blocked_by edges #epic !high @item:EPC-1795085241910080
- [ ] EPC-1795085548204252 Link RIPDPI R1 to R4 qualified IDs as related_tasks once filed #epic !high @item:EPC-1795085241910080

## Verification

Local: `./taskctl validate` and `./taskctl openspec cli validate --strict`. The epic closes after D1 to D7 are done; the acceptance evidence is the D7 verification.
