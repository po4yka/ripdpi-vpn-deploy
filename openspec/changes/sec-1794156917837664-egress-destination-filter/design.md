## Context

See `proposal.md` for motivation. Xray and Hysteria2 frontends have one direct outbound: authenticated SOCKS5 to the transport-egress normalizer. `Normalizer._destinations` in `scripts/transport_egress_normalizer.py` receives the recipient host, resolves a name through the node resolver, and passes the addresses to `DestinationPolicy.admitted_candidates` in `scripts/transport_destination_policy.py`. The normalizer has no capabilities, loads its configuration through `LoadCredential`, and is published as part of one generation with rollback.

Facts that limit the design:

- `ansible/roles/runtime-release/files/validate_yaml_mapping.py` refuses a Hysteria2 configuration with `acl` or `resolver`. Recipient authority belongs to the normalizer.
- The `vpn-p1-web` and `vpn-p2-udp` profiles set `enable_geodata: false`. Node classes in the fleet have as little as 1 GB of memory.
- The Xray gateway receives addresses that the normalizer already resolved, so it cannot match names.
- AmneziaWG traffic uses kernel forwarding and does not reach the normalizer.

## Goals / Non-Goals

- Goal: one deny decision for P0, P1 and Hysteria2 at the existing boundary, disabled by default.
- Goal: bad deny data cannot replace an accepted generation.
- Non-goal: AmneziaWG filtering. A DNS filter can only partly cover it and adds a resolver to the smallest node. A separate task can add it after measurement.
- Non-goal: per-device policy. The normalizer identifies the frontend credential, not the device.
- Non-goal: content inspection, TLS interception, category filtering such as advertising, or automatic list updates.
- Non-goal: generating client routing profiles. The repository documents the client-side block and acceptance checks it on a device.

## Decisions

- Enforce in the normalizer. Rejected: Xray `block` rules plus Hysteria2 ACL, because this needs two rule engines, removes a deliberate Hysteria2 authority check and needs geodata on profiles that do not have it. Rejected: gateway rules, because the gateway does not see names.
- Check the name before resolution, by a walk over its label suffixes against a frozen set. The cost depends on the number of labels and the check sends no DNS query for a denied name. Reuse `canonical_name` so that case and a trailing dot have one meaning.
- Check address ranges on literal and resolved addresses in `DestinationPolicy.admitted_candidates`, after the existing isolation. Filter a mixed answer instead of denying the whole name, as the isolation does.
- A name matched by the allow list skips the deny name and range checks. Isolation is always evaluated.
- Use a plain text input (one name or one CIDR per line) instead of `geosite.dat`. The normalizer is Python with no Xray dependency, and one parser can validate the whole list. The role converts the verified input to one private candidate file.
- Pin one source URL and SHA256 per list in the `destination_filter` secrets section, with the same refusal of moving URLs as `geodata`. The first implementation step selects the source and records the reason. Candidate: a maintained threat-intelligence domain feed at a fixed commit. Its medium variant has about 360,000 entries; the full variant has about 1.4 million and is expected to exceed the budget.
- Update the list through a new pin and the ordinary transport-egress generation change. Rejected: a daily timer as used for geodata, because an unattended list change would run the generation transaction without review. The accepted cost is that entries age between deployments.
- Denials raise the existing `PolicyError("destination-denied")`, so the wire result and log text do not change.
- Reject activation if the canary host or the REALITY target is denied. The failure must occur at candidate admission, before the accepted generation stops.

## Contracts and ownership

- `scripts/transport_destination_policy.py`: name and range deny decision, parser, limits.
- `scripts/transport_egress_normalizer.py`: name check before resolution, private data load.
- `ansible/roles/transport-egress`: toggle evaluation, verified download, candidate file, `LoadCredential`, rollback set, Molecule scenario. Update its `CLAUDE.md`.
- `ansible/group_vars/all.yml`: `vpn.enable_destination_filter`, default `false`.
- `secrets/schema.json`, `scripts/validate-secrets.py`, `scripts/check-secrets-coverage.py` input, `secrets/prod.secrets.example.yaml`: `destination_filter.{domains_url, domains_sha256, ranges_url, ranges_sha256, allow_domains}`.
- `docs/reference/secrets.md`, `docs/reference/client-notes.md`: inputs, coverage and the client-side block.

## Risks / Trade-offs

- False positive blocks a service → operator allow list; staging soak before production.
- Client sends an address instead of a name, or the frontend cannot sniff the name → only the address-range check applies; documented as a limit and covered by a test on each path.
- Xray sniffing may not send a name for each protocol → the verification step tests name delivery to the normalizer on P0, P1 and Hysteria2 before acceptance.
- A name that resolves through an unlisted CNAME to a listed name is not matched → documented; the address-range check can still apply.
- Memory on the smallest node → measured entry limit; a list over the limit is refused.
- Generation transaction disturbs service during an update, as observed on a slow-disk node → updates are operator-run and staged, never automatic.
- The list source has its own licence → the data is fetched by the node and not stored in the repository; the owner confirms use at source selection.

## Migration Plan

Forward: deploy the code with the toggle off, which changes nothing. Enable on staging with a pinned list, soak, then enable per production profile as a separately authorized deployment. Rollback: set the toggle to false and deploy, or let the generation transaction restore the accepted generation after a failed candidate. There is no breaking change; existing profiles render the same normalizer configuration.
