# Design

## Offsite backup grant

`rclone sync` stays: restic prunes locally, and a non-hard delete on B2 only hides the object. Hiding needs `writeFiles`; erasing a version needs `deleteFiles`. A key without `deleteFiles` therefore turns every deletion from a compromised node into a hide, which the bucket lifecycle keeps for `daysFromHidingToDeleting` days. The check runs on the controller before the credential reaches the node, so a wrong grant never lands. It follows the existing Kuma and operator-kit exact-capability checks. A same-host `local` remote has no remote grant and is reported as not applicable; Molecule uses that shape. The bucket is not managed by Terraform, so its lifecycle value is an operator setting documented in `docs/how-to/restore.md`.

## Collector label integrity

Prometheus has no receive-side label enforcement. The VictoriaMetrics `extra_label` ingest argument unconditionally overrides a user-supplied label of the same name (VictoriaMetrics v1.52.0 changelog). nginx already maps the verified client-certificate subject to a node identity and requires it to match the path, so it passes that mapped value as `extra_label=node=...` to a loopback vmagent, which forwards to Prometheus on loopback. The relay has its own install root and pin; it is not tied to the release authority of the agent's vmagent. The relay keeps no durable queue while Prometheus is down: it returns 429, and the sender's durable queue keeps the data.

## SSH source floor

The variable validation replaces the zero-prefix rule with a /24 or /48 floor. This rejects world networks, world networks with host bits, and over-broad typos. Live inputs use /32.

## Public HTTP identity

Only the ACME HTTP/80 server lacked `server_tokens off`; a render test now checks every public server block.

## REALITY target

The repository already implements self-steal (`ansible/roles/reality-self-steal`, profile `vpn-p0-self-steal`). The owned name needs an explicit A record, because the zone's wildcard CNAME otherwise sends it to the public site. Its certificate is issued off-node with DNS-01 and supplied through SOPS. The role has no renewal; the pair must be reissued before it expires. Only service clients (watchdog and the cross-node probe) use P0, so the SNI change needs no human device redelivery.
