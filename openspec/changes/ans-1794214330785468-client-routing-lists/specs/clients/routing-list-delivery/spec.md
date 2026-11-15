## Purpose

Deliver self-refreshing client routing lists from the subscription plane without letting a feed update widen what leaves the tunnel.

## ADDED Requirements

### Requirement: REQ-ROUTING-LISTS-ADMISSION — Candidates pass policy before publication

The refresher MUST refuse a candidate unless its digest sidecar matches, it stays within the byte cap, it parses without duplicate tags or inverted GeoIP entries, every tag the profile references exists, direct rules are bounded domains and networks within the configured prefix floors, every `must_direct` name matches, no `must_not_direct` name or address matches, and direct entry counts stay within `max_change_ratio` of the served generation.

#### Scenario: Feed adds a broad direct rule

- **WHEN** a candidate adds a top-level domain, a regular expression, or a network wider than the floor to a direct tag
- **THEN** the run exits non-zero with a category and publishes nothing

#### Scenario: Feed adds a canary

- **WHEN** a candidate makes a `must_not_direct` name or address match a direct tag
- **THEN** the run refuses with `feed-direct-canary`

### Requirement: REQ-ROUTING-LISTS-KEEP — A refusal keeps the served generation

Any refusal or failure MUST leave the served generation, its files and its `LastUpdated` value unchanged.

#### Scenario: Refused update

- **WHEN** a refresh is refused after an earlier successful publication
- **THEN** clients still download the earlier files

### Requirement: REQ-ROUTING-LISTS-SERVED — Only client files are served and refresh is client-visible

The delivery host MUST serve only `profile.json`, `geosite.dat`, `geoip.dat` and their `.sha256` files under `/routing/<token>/`, with URI-free logs. `LastUpdated` MUST grow when the lists, profile or base URL change and MUST NOT change otherwise.

#### Scenario: Unchanged feed

- **WHEN** a refresh finds the same lists, profile and base URL
- **THEN** the served generation and `LastUpdated` stay the same

#### Scenario: Internal file requested

- **WHEN** a client requests `manifest.json` under the routing path
- **THEN** the route does not match

### Requirement: REQ-ROUTING-LISTS-BLOCK — Direct rules do not bypass the server deny filter

When the profile enables the destination deny filter, the refresher MUST admit the filter's pinned files by SHA-256 and MUST publish, after the operator's block rules, a client block rule for each direct destination that the filter denies. It MUST leave out a rule that covers an `allow_domains` name and MUST NOT check literal `DirectIp` ranges. An unusable deny file, a keyword or pattern direct rule, or more than 10,000 rules MUST refuse the run.

#### Scenario: Deny name under a direct domain

- **WHEN** the deny list contains a subdomain of a direct domain
- **THEN** the published profile has a `domain:` entry for it in `BlockSites`

#### Scenario: Direct domain under a deny name

- **WHEN** a direct domain or exact name is at or under a deny name
- **THEN** that direct domain or exact name becomes a block rule, not the deny name

#### Scenario: Deny range on a direct feed network

- **WHEN** a deny range overlaps a direct feed network
- **THEN** only the overlapping part becomes a `BlockIp` rule

#### Scenario: Allowed name under a deny entry

- **WHEN** a direct domain under a deny name holds an `allow_domains` name
- **THEN** no block rule covers that direct domain

#### Scenario: Deny range on a local network rule

- **WHEN** a deny range overlaps only a literal `DirectIp` range
- **THEN** it does not become a client block rule

#### Scenario: Deny data does not match its pin

- **WHEN** a downloaded deny file has another SHA-256 digest
- **THEN** the run refuses with `block-digest-mismatch` and the served generation stays

### Requirement: REQ-ROUTING-LISTS-RETIRE — Disabling removes only owned runtime

Disabling the feature or the role MUST retire the routing list units, refresher, policy file and published data, and MUST preserve an administrative unit mask.

#### Scenario: Feature disabled

- **WHEN** convergence runs with `nginx_xhttp.routing_lists.enabled` false after it was true
- **THEN** the owned units and files are absent and the vhost has no routing location
