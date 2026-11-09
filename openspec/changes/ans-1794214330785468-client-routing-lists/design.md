## Context

`subscription-host` already owns an independent HTTPS vhost, bounded bearer-path logging and hardened timers. The `geodata` role serves Xray on the node, requires SHA256 pins and restarts consumers, so it does not fit files that only clients download.

## Goals / Non-Goals

- Goal: clients receive current lists from the delivery host through one stable link.
- Goal: a bad or hostile feed update cannot widen what leaves the tunnel.
- Non-goal: enabling the feature on any deployed profile; rollout is a separate authorized step.
- Non-goal: changing node-side Xray geodata or its pins.

## Decisions

- Extend `subscription-host` instead of adding a role. It reuses the vhost, service user and retirement path.
- The feed is deliberately unpinned, as an exception to version pinning that covers client list data only. A pin would need a release and a deploy for each list update, which is the staleness this change removes. Admission replaces the pin: `.sha256` sidecar, byte cap, protobuf parse, and policy.
- Policy treats every feed tag the profile references as untrusted. Local ranges stay as literal profile rules, because an exempt feed tag would let the feed bypass the floors and canaries. Rejected: exempting a `private` tag.
- Refuse duplicate tags, inverted GeoIP entries, regular expressions, keyword rules, malformed labels, networks above the prefix floors and IPv4-mapped IPv6 prefixes. The role requires `GlobalProxy: "true"`, so unmatched traffic stays in the tunnel.
- Publish by swapping a symlink to a complete generation and keep two generations. `LastUpdated` grows only when the lists, profile or base URL change, because INCY reloads lists when it grows.
- Feed URLs, rules and canaries are private inputs, so the repository carries no operator or regional labels. The path token keeps the location undiscoverable and is not access control.

## Risks / Trade-offs

- A feed can still change entries inside the allowed shape. The canaries and the `max_change_ratio` limit bound this, and the operator chooses the feed.
- The published files are public to anyone holding the token. They contain no credentials.
