# role: observability_control_plane — bounded write-only metrics receiver

## Design decisions

Prometheus binds only `127.0.0.1:9090`; nginx is the sole public listener and
accepts only mTLS `POST /remote-write/v1/nodes/<node_id>` requests on 9443.
The default TLS virtual host rejects a missing or incorrect SNI before it can
reach the write-only vhost. Prometheus generations are content-addressed and
immutable; rollback repoints `current.yml` directly at the prior generation.
The exact certificate subject maps to one technical node id. TLS validation
uses the client CA, CRL, `clientAuth` purpose and two distinct server SANs.
Prometheus is installed through `runtime-release` with explicit pins.
When explicitly enabled, expected targets are validated from a repository
inventory and rendered as bounded contract metrics; source/deploy identity,
TSDB capacity, and pipeline status use the existing bounded evidence families.

## What's done well

The role checks available (not total) filesystem capacity, fixed request and
retention bounds before writes, removes the distribution nginx site, and
starts nginx explicitly after `policy_rc_d` installation. It disables only
its units and generated configuration while retaining TSDB data.

## Pitfalls

Do not expose loopback Prometheus, add a query/admin path, decode Remote Write
protobuf in nginx, or replace certificate/path identity checks with an IP
allowlist. Do not overwrite an existing content-addressed generation with
different bytes. Retention cleanup is explicitly not part of disable. Do not
add a second target-discovery path, endpoint labels, notification routes, or
liveness quorum logic here; protocol verdict adaptation remains external.
