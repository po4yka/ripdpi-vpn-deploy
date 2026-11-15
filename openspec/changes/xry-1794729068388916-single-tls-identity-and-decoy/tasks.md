# XRY-1794729068388916: Give each node one TLS identity and an operator-owned decoy

## Objective

A production address presents one TLS identity or a recorded exception, no production node serves the repository's decoy bytes, and port 80 behaves like the decoy site.

## Ownership

- `ansible/roles/reality-self-steal/`, `ansible/roles/nginx-xhttp/templates/site.conf.j2`, a shared preflight under `ansible/playbooks/tasks/` included by `ansible/roles/xray/` and `ansible/roles/hysteria/`, `ansible/roles/node_manifest/`, `scripts/reality_target_validation.py`, their tests, snapshots and docs.

## Execution

- [x] XRY-1794729166198238 Publish the self-steal site from an operator directory and refuse production without one #bug !high @item:XRY-1794729068388916
- [x] XRY-1794729177636809 Report the target network and refuse two TLS identities on one production address #bug !high @item:XRY-1794729068388916
- [x] XRY-1794729189657998 Serve the decoy on port 80 without a redirect to another port #bug !high @item:XRY-1794729068388916

## Verification

- Validator unit tests, `make molecule-test ROLE=reality-self-steal`, `make molecule-test ROLE=nginx-xhttp`, `make snapshot-check`, one `make check`; remote CI. Production nodes receive the change through the reviewed dry-run and deploy transaction after the operator chooses a layout or records the exception.
