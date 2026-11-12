# Change: Block unsafe recipient destinations at the egress boundary

Task ID: `SEC-1794156917837664`

## Why

Authenticated P0, P1 and Hysteria2 clients can reach every public destination. The exit blocks BitTorrent and outbound QUIC, but no rule stops known phishing, malware or command-and-control destinations. An operator who issues device access cannot reduce this exposure at the server, and the device that uses the access gets no protection from the VPN path.

All three paths already reach recipients through one component, the transport-egress normalizer. This component owns the recipient destination decision, so one deny policy can cover all three paths without a separate rule set for each engine.

## What Changes

- Add an optional deny policy to the recipient destination boundary. It denies listed names, their subdomains and listed address ranges for P0, P1 and Hysteria2.
- Add an operator allow list that can exclude a false positive from the deny policy. It cannot permit a destination that the private-address isolation denies.
- Deliver the deny data from one pinned source with a SHA256 digest, inside the existing transport-egress generation, so that a bad list leaves the accepted generation active.
- Refuse activation when the deny data would deny a destination that runtime acceptance needs.
- Keep the policy disabled by default. Operators enable it per profile after staging.
- Document the paths that this policy does not cover: AmneziaWG and traffic that a client routes directly, and how to configure a client-side block for direct traffic.

## Capabilities

### New Capabilities

- `transports/destination-deny-filter`: deny policy for recipient-selected P0, P1 and Hysteria2 destinations, its input admission, its failure behavior and its stated coverage limits.

### Modified Capabilities

None. The private-address isolation in `transports/resolved-destination-boundary` stays unchanged and always applies first.

## Impact

- Ansible: `transport-egress` role, candidate files, normalizer unit and configuration; protocol toggle in `ansible/group_vars/all.yml`.
- Scripts: `scripts/transport_destination_policy.py`, `scripts/transport_egress_normalizer.py`.
- Secrets contract: a new `destination_filter` section in `secrets/schema.json`, `scripts/validate-secrets.py` and `secrets/prod.secrets.example.yaml`.
- Documentation: `docs/reference/secrets.md`, `docs/reference/client-notes.md`, role notes.
- Runtime: normalizer memory use increases on each node that enables the policy. Enabling or updating the policy requires a transport-egress generation change on that node.
- Terraform, cloud-init, vpnd and the RIPDPI bundle contract do not change.
