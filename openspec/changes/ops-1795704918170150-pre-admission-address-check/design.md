## Context

`scripts/emit-bundle.sh` publishes node addresses. `make burn-check` and the liveness sentinel observe nodes after publication. `docs/explanation/threat-model.md` states that CI measures only the unfiltered half.

## Goals / Non-Goals

- Goal: Refuse to publish a node address that a filtered-side vantage cannot reach, and keep ICMP out of admission and liveness evidence.
- Non-goal: any IP address, hostname, key or concrete evasion parameter in the repository.

## Decisions

- Vantage: an operator-run filtered-side producer, the RIPDPI diagnostics address check on a device in the filtered network, signs one attestation per check with its own Ed25519 key. The contract is `contract/node-address-check.schema.json` with the signed golden fixture `contract/node-address-check.golden.json`. Rejected: the liveness executor, which runs on the unfiltered side and cannot see filtered reachability; a new vantage service.
- Trust: the operator lists vantage public keys in a private trust file (`ADDRESS_VANTAGE_KEYS`) and drops attestations into a private directory (`ADDRESS_ATTESTATION_DIR`). One key is one independent control point. A malformed, tampered, untrusted or future-dated attestation refuses every admission, so the evidence directory cannot hold ambiguous input.
- Evidence: only the newest attestation of each vantage key for each address counts, so a newer failure replaces an older pass from the same key and the reverse.
- Refusal rule: failures from two or more distinct keys against addresses in the same IPv4 /24 close the block and refuse admission even when another vantage passed; the message says to recreate the node with a new address. IPv6 nodes are judged by their own address.
- Admission rule: when the block is not closed, an address is admitted when one trusted attestation, not older than seven days, for that exact address reports TCP pass and TLS pass. One failing key without a pass asks for a second vantage or recreation. No result refuses. A fail is a TCP or TLS fail; ICMP is recorded as a hint and ignored.
- Scope of the check: the gate decides address-level reachability. The attestation records the probed listener port, and the operator probes the P0 TLS listener, but the gate does not compare that port with every transport port in the bundle; port-level or protocol-level blocking stays with the liveness probes and `make burn-check`.
- Placement: the gate runs in the shared in-memory materializer for every RIPDPI bundle (`emit-bundle`, device issuance, migration and subscription token delivery). The read-only drift comparison does not publish and is exempt. The sing-box, Xray and AWG standalone formats are outside this change. No Terraform hook, so the layer boundaries stay unchanged.

## Contracts and ownership

- `scripts/` (emit path and the check script), `docs/how-to/deploy.md`, `docs/explanation/threat-model.md`. One writer.

## Risks / Trade-offs

- A false refusal costs one node recreation -> the node is disposable, and the operator message names the cause.
- A vantage outage blocks admission -> fail-closed is the stated behaviour; the operator can retry.
- Existing nodes also need a fresh attestation before a new RIPDPI bundle names them -> this is intended: a reissued bundle is a new admission of the address. The operator runs the check from the filtered-side device before issuing.

## Migration Plan

Forward only. Rollback reverts the change.
