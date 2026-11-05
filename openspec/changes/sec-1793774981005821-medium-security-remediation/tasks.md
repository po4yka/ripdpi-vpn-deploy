# SEC-1793774981005821: Remediate medium security audit findings

## Objective

The five confirmed medium audit findings are fixed in source and on the deployed fleet.

## Ownership

- `ansible/roles/backup/`, `scripts/backup-storage-grant.py`, `ansible/roles/observability_control_plane/`, `scripts/observability-operator.py`, `ansible/roles/nginx-xhttp/templates/public-acme.conf.j2`, `terraform/providers/*/variables.tf`, their tests and docs.

## Execution

- [x] SEC-1793776165979531 Refuse non-append-only offsite backup credentials before delivery #bug !high @item:SEC-1793774981005821
- [x] SEC-1793776927682536 Enforce the node label at collector ingest with a loopback relay #bug !high @item:SEC-1793774981005821
- [x] SEC-1793777693877736 Refuse SSH source networks broader than /24 or /48 #bug !high @item:SEC-1793774981005821
- [x] SEC-1793778451096956 Hide the nginx version on the HTTP/80 ACME server #bug !high @item:SEC-1793774981005821
- [x] SEC-1793778849874329 Move P0 to the REALITY self-steal target and reissue append-only backup keys #bug !high @item:SEC-1793774981005821

## Verification

- Focused unit, Terraform, snapshot and lint checks; remote CI; dry-run, deploy and verify on node-a, node-b and node-c; external probes of the public surfaces.
