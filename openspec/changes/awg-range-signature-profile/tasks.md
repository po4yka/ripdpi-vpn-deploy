# ANS-1792776076428131: Deliver AWG range and signature profiles

## Objective

Deliver the supported AWG 3.1 profile without loss between server and client.

## Ownership

Primary: this repository, all canonical contract files and runtime admission. Client worker: Rust, Kotlin and contract mirrors in its isolated checkout. Shared contract changes are serialized through the primary writer.

## Execution

- [x] ANS-1792776155626175 Implement strict range and signature admission and canonical fingerprints with regression tests #feature !high @item:ANS-1792776076428131
- [x] ANS-1792776156217659 Carry the complete profile through role render generators and exports with source capability guards #feature !high @item:ANS-1792776076428131
- [ ] ANS-1792776156839285 Verify real peer traffic and paired client contracts then run source and hosted gates #feature !high @item:ANS-1792776076428131

## Verification

Run targeted semantic, export, schema and source candidate tests; snapshot checks; make check; paired client tests and real peer traffic. Record exact-head hosted results. Physical arm64 and external path acceptance stay open until observed. No live actions are authorized by these steps.
