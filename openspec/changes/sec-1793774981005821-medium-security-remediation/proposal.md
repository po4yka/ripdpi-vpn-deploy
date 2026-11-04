# Change: Remediate medium security audit findings

Task ID: `SEC-1793774981005821`

## Why

A read-only audit of the deployed fleet on 2026-11-04 found five confirmed medium issues. Node backup keys could delete their own offsite copies, and the bucket kept hidden versions for only 7 days. The collector trusted the `node` label inside remote-write payloads, so one node could write healthy series for another. The SSH CIDR gate refused only zero-length prefixes. The public HTTP/80 ACME server revealed the nginx and distribution version. P0 used a third-party REALITY target hosted outside its own provider network, and that cross-network certificate is a known active-probing signal. A sixth candidate, a missing observer guest firewall, was disproved: the observer bootstrap applies the host-class guest firewall, and an external scan of the ephemeral range got no reply.

## What Changes

- The backup role refuses an offsite credential unless it is append-only (exactly `listBuckets`, `listFiles`, `readFiles`, `writeFiles`), limited to one private bucket and to this node's prefix, with `hard_delete` off.
- A loopback vmagent relay between collector nginx and Prometheus overrides `node` with the identity of the client certificate.
- Every provider root refuses `allowed_ssh_cidrs` entries broader than /24 (IPv4) or /48 (IPv6).
- The HTTP/80 ACME server sets `server_tokens off`.
- Operations: P0 moves to the existing REALITY self-steal profile with an owned `edge` name. The node backup keys are reissued as append-only, and the bucket keeps hidden versions for 30 days.

## Capabilities

### New Capabilities

- `security/operator-surface-hardening`: append-only offsite grants, attributed telemetry ingest, bounded SSH sources, a version-free public HTTP surface, and a same-host REALITY target.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/backup/tasks/configuration.yml`, `ansible/roles/observability_control_plane/`, `ansible/roles/nginx-xhttp/templates/public-acme.conf.j2`.
- Terraform: `allowed_ssh_cidrs` validation in all four provider roots.
- Scripts: `scripts/backup-storage-grant.py`, `scripts/observability-operator.py`.
- Operations: P0 secrets, its inventory cohort and DNS, node backup keys, bucket lifecycle, and the private observability vars that carry the relay pin.
