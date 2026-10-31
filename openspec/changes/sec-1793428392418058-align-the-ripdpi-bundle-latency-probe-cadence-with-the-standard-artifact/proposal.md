# Change: Align the RIPDPI bundle latency probe cadence with the standard artifact

Task ID: `SEC-1793428392418058`

## Why

`SEC-1793386547449444` slowed the standard sing-box artifact's `urltest` group
from five minutes to thirty because a synchronous probe of every transport to
one address every five minutes matches the concurrent-session policing pattern
in the threat model. The RIPDPI bundle kept the five-minute cadence only
because `contract/ripdpi-bundle.payload-failover.json` and
`contract/ripdpi-bundle.hysteria-port-hopping.json` are byte-compared against
the client's vendored copies by `contract-sync`. RIPDPI devices therefore still
emit the policing-shaped burst that the standard artifact no longer does. The
client re-vendors the two fixtures in `po4yka/RIPDPI#DAT-1793428393229398`, so
the deployer can now drop the format split.

## What Changes

- Both the standard sing-box artifact and the RIPDPI bundle emit `interval: 30m` on the `auto` outbound; the format conditional in `scripts/client_payload.py` is removed.
- The two bundle contract examples change the one `interval` scalar; the bundle schema and every other field stay identical.
- `docs/reference/client-notes.md` and the `SEC-1793386547449444` change record no longer describe a cadence split.
- Not breaking: no schema, listener, secrets or operator-input change; a re-emitted bundle differs in one engine field that every supported client already parses.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `security/traffic-metadata-and-decoy-identity`: the bounded client probe cadence applies to every emitted format, not only the standard artifact.

## Impact

- `scripts/client_payload.py`, `contract/ripdpi-bundle.payload-failover.json`, `contract/ripdpi-bundle.hysteria-port-hopping.json`, `docs/reference/client-notes.md`, the `SEC-1793386547449444` change artifacts and `tests/unit/test_client_payload_recipient_boundaries.py` fixtures.
- Cross-repository contract: the client's vendored copies under `core/data/src/test/resources/contract/` must land with the same bytes (`po4yka/RIPDPI#DAT-1793428393229398`) or `contract-sync` reports drift until both sides are merged.
- No Terraform, Ansible, secrets, cloud-init or live-host change.
