# Change: Host and refresh client routing lists on the subscription plane

Task ID: `ANS-1794214330785468`

## Why

An INCY routing profile imported once from a static link never receives new lists, and its list files come from a third-party CDN. Clients need current lists from infrastructure the operator controls, without a new link for each update.

## What Changes

- A daily `vpn-routing-lists` timer in `subscription-host` downloads list files from operator-configured HTTPS feeds and publishes them with the operator's INCY profile under `/routing/<token>/`.
- Every candidate passes digest, size, parser and policy admission. A refusal keeps the served generation.
- Clients import an `incy://autorouting/onadd/` link, so INCY refreshes the profile and lists itself.
- `subscription.routing_lists` is a new optional, disabled-by-default secrets block.

## Capabilities

### New Capabilities

- `clients/routing-list-delivery`: admitted self-refreshing delivery of client routing lists.

### Modified Capabilities

- None.
