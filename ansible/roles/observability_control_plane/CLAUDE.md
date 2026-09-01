# role: observability_control_plane — bounded write-only metrics receiver

## Design decisions

Prometheus binds only `127.0.0.1:9090`; nginx is the sole public listener and
accepts only mTLS `POST /remote-write/v1/nodes/<node_id>` requests on 9443.
The exact certificate subject maps to one technical node id. TLS validation
uses the client CA, CRL, `clientAuth` purpose and two distinct server SANs.
Prometheus is installed through `runtime-release` with explicit pins.

## What's done well

The role checks fixed request and retention bounds before writes, preserves a
previous configuration before changing `current.yml`, and disables only its
units and generated configuration while retaining TSDB data.

## Pitfalls

Do not expose loopback Prometheus, add a query/admin path, decode Remote Write
protobuf in nginx, or replace certificate/path identity checks with an IP
allowlist. Retention cleanup is explicitly not part of disable.
