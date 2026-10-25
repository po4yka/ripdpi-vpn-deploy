# OPS-1792927264049641: Rebuild the cloud VPN service

## Objective

Serve the rebuilt public site over automatically renewed HTTPS and qualify the
cloud-only VPN transports and private panel within the approved resource bounds.

## Ownership

The main implementation owns the affected UpCloud/Scaleway roots, nginx-xhttp
and Hysteria roles, certificate schemas and selection scripts, listener and
protected ingress contracts, observability roles, public-site assets/templates,
matching tests and this linked task. Shared schema, site playbook, manifests and
snapshot files are edited serially. Private grants and live inputs remain in the
single ignored operator kit. A later independent patch review is read-only.

## Execution

- [ ] OPS-1792928402362900 Provision current small plans with exact storage and private observer admission #feature !high @item:OPS-1792927264049641
- [ ] OPS-1792928402860448 Renew public nginx and Hysteria certificates on cloud hosts with validated authority #feature !high @item:OPS-1792927264049641
- [ ] OPS-1792928403354199 Improve and render the public reading site across screen sizes #feature !high @item:OPS-1792927264049641
- [ ] OPS-1792928403861188 Run bounded private panel monitoring without external bot credentials #feature !high @item:OPS-1792927264049641
- [ ] OPS-1792928404361547 Qualify staging and deploy the approved cloud service with HTTPS and encrypted recovery #feature !high @item:OPS-1792927264049641

## Verification

Run provider mock tests, focused ACME/observer/site behavior checks and reviewed
snapshots. Use gated native/Molecule checks where supported, then the cross-layer
local gate. Live evidence requires reviewed saved plans, exact staging cleanup,
verified host/SSH/Tailnet ownership, authenticated cloud-client traffic on all
four protocols, public HTTPS, renewal, reboot and encrypted restore. Keep source,
CI, staging, live, client and recovery claims separate.
