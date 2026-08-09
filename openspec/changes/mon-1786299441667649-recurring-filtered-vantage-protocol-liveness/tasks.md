# MON-1786299441667649: Make filtered-vantage protocol liveness a recurring fleet gate

## Objective

Operate one recurring evaluator that produces complete, redacted, multi-vantage
evidence for every supported logical profile.

## Ownership

Own liveness policy/evaluation, sentinel scheduling, alerting, evidence tests,
and status documentation. Serialize shared schema and rotation state edits.

## Execution

- [ ] MON-1786299448730889 Extend policy and evidence validation to require control plus independent filtered path classes #feature !high @item:MON-1786299441667649
- [ ] MON-1786299448748334 Wire recurring scheduling, bounded alerts, recovery, and explicit unavailable-vantage state #feature !high @item:MON-1786299441667649 @blocked_by:MON-1786299448730889
- [ ] TST-1786299448765335 Prove profile completeness, failure classification, sustained quorum, and no automatic promotion #feature !high @item:MON-1786299441667649 @blocked_by:MON-1786299448748334
- [ ] DOC-1786299448781815 Record staging and recurring fleet evidence with the exact client-path boundary #feature !high @item:MON-1786299441667649 @blocked_by:TST-1786299448765335

## Verification

Run task contracts and focused tests before the staging and recurring observations.
