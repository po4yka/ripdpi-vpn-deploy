# TST-1786299293097217: Complete recurring AmneziaWG live acceptance

## Objective

Produce one complete current-revision AWG acceptance path from disposable
provisioning through real client traffic, recovery, redacted evidence, and cleanup.

## Ownership

Own the existing AWG real-VPS executor, sentinel/evidence integration, focused
tests, and operator scheduling. Serialize shared evidence and secrets contracts.

## Execution

- TST-1786299379836822 DROPPED: Extend the acceptance manifest with exact-source, freshness, recovery, and teardown outcomes #feature !high @item:TST-1786299293097217
- TST-1786299379854550 DROPPED: Prove negative keys, partial evidence, unavailable infrastructure, and cleanup fail closed #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379836822
- TST-1786299379871208 DROPPED: Run one isolated current-revision client and server acceptance plus one recurring observation #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379854550
- DOC-1786299379888954 DROPPED: Record redacted exact-SHA evidence and the remaining external limitations #feature !high @item:TST-1786299293097217 @blocked_by:TST-1786299379871208

## Offline implementation note

The deploy-side runner now fails closed unless a root-private descriptor with
final-component symlink rejection binds the RIPDPI 40-hex source revision and
immutable client artifact SHA-256. Launcher preflight refusals emit redacted
`INFRA_UNAVAILABLE` records and retain an existing `latest.json`. These offline
safeguards do not supply the descriptor, client artifact, provider inputs,
disposable VPS, or recurring observation.

## Verification

Run task contracts and focused offline tests before the isolated live and recurring gates.
