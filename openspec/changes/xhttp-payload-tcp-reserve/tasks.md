# XRY-1793635470456809: Deliver bounded XHTTP pools with payload-verified TCP reserves

## Objective

Deliver complete bounded XHTTP profiles and verify TCP recovery from UDP payload failure.

## Ownership

Primary owns scripts/client_payload.py, tests/unit/test_xhttp_alternate_profiles.py,
tests/fixtures/xhttp-payload-tcp-reserve.json, delivery documentation and this task.
The paired client owns its Kotlin/native implementation in a separate worktree.
The producer writes the fixture before the consumer copies it. No shared writer lane.

## Execution

- [ ] XRY-1793635898207050 Deliver bounded recipient pools and verify payload TCP reserves end to end #feature !high @item:XRY-1793635470456809

## Verification

Run targeted exporter tests, the paired consumer parser/runtime/native pool and
payload selector tests, fixture byte parity, independent review and the full local
make check through build-gate. Record hosted CI on each PR. No dry-run, staging,
live rollout or physical-device mutation is part of this source change.
