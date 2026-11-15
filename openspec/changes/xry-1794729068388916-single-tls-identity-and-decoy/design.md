## Context

`proposal.md` gives the motivation. `enable_reality_self_steal` is `false` in `group_vars/all.yml` and in the live profiles, so the borrowed target is the common layout. `REQ-TMD-REALITY-CONSISTENCY` already states that a borrowed target fails the owned-name comparison by construction; this change adds the network comparison and a production gate on the result. The self-steal role copies `files/public-site/*` with a file glob. The nginx-xhttp port 80 server has one `server` block with `return 301 https://$host:<port>`.

## Goals / Non-Goals

- Goal: a scan of one production address shows one certificate identity, or the operator recorded why not.
- Goal: no production node serves site bytes that this repository publishes.
- Non-goal: a new default profile. The operator still selects self-steal or a borrowed target.
- Non-goal: the Hysteria obfuscation default and port choice. The measurement task for transport signatures owns those.

## Decisions

- The self-steal input copies the nginx-xhttp contract (`nginx_xhttp_public_site_dir`): a controller-local directory, enumerated and published in one transaction, with the same production refusal. Rejected: reuse the nginx-xhttp variable, because the two roles can serve different names.
- The validator gets the node address from the `NODE_ADDRESS` environment variable, like its other inputs, and looks up both ASNs through the existing `probe-asn.sh` budget. Without the variable it sends nothing and reports `unknown`. One target address in another AS gives `different_asn`. `unknown` does not fail the validator, because the lookup depends on an external service.
- The preflight contacts no service: a lookup at deploy time would send the node address to a third party on every run. The operator records the validator result in `reality_target_network`; only a recorded `different_asn` refuses. An empty or `unknown` value does not refuse, because a P0 node with a borrowed target is the layout the main spec already accepts.
- The gate lives in one preflight task file. `site.yml` imports it in `pre_tasks`, so that the refusal comes before any host change, and the xray, hysteria and nginx-xhttp roles import it for standalone runs, like `transport-input-preflight.yml`. Rejected: a check in `site.yml` only, because the roles also run from other playbooks.
- The gate counts Hysteria and nginx-xhttp on any port as listeners with the operator certificate: a scanner compares names for each address, not for each port. With self-steal enabled the gate passes, also when the roles use distinct operator names; the self-steal role already refuses one name with two certificates, and its notes accept distinct names.
- The exception is one variable with a free-text reason. The manifest records only that it is active. Rejected: one acknowledgement variable for each case, because the operator decision is the same.
- Port 80 serves the decoy root directly when the HTTPS port of the name is not 443; this covers the primary server, the distinct fallback name and the managed-TLS server in `public-acme.conf.j2`. One `default_server` in `site.conf.j2` answers every other Host with the decoy 404; the managed-TLS file carries none, because it is validated beside the packaged default site on a fresh host. The port 80 servers keep logging off and carry no news or feed location. Rejected: close port 80, because the Hysteria ACME path and the listener contract use it.

## Contracts and ownership

- Ansible: `ansible/roles/reality-self-steal/` tasks, defaults, cleanup and Molecule; `ansible/roles/nginx-xhttp/templates/site.conf.j2` and its snapshot; a shared preflight under `ansible/playbooks/tasks/`; `ansible/roles/node_manifest/`.
- Scripts: `scripts/reality_target_validation.py` and its report schema; the extra-vars allowlist in `scripts/validate-ansible-extra-vars.py`, the site snapshot in `scripts/deploy-controller.py` and the input discovery in `scripts/fleet-maintenance.py`.
- Configuration: new variables `reality_self_steal_public_site_dir`, `reality_target_network` and `tls_identity_exception`.
- Docs: `docs/research/reality-target-selection-2026-07.md` is unchanged; the self-steal and deploy guides state the new inputs.

## Risks / Trade-offs

- Existing production nodes with a borrowed target beside Hysteria or nginx-xhttp fail the next deploy → the failure message names the listeners and the three ways to pass: self-steal, a node without those listeners, or the recorded exception. Another Hysteria port is not a way to pass, because the address still presents two names.
- The gate checks only Hysteria and nginx-xhttp → other roles that serve an operator certificate (subscription host, Naive, CDN front) need one more row in the preflight.
- ASN equality is a coarse test of network neighbourhood → it is the rule the secrets example already states; the report keeps the three-value result so that a finer test can replace it.
- A site that serves content on port 80 without a redirect loses the HTTPS upgrade → the decoy has no user sessions, and the XHTTP-on-443 layout keeps the redirect.

## Migration Plan

Merge, then for each production node choose the layout or record the exception before the next deploy. Deploy through the ordinary dry-run and deploy transaction. Rollback is a revert and a second deploy. Gates: the validator, preflight, self-steal and public-site unit tests (they run the role tasks through `ansible-playbook`), `make molecule-test ROLE=reality-self-steal`, `make molecule-test ROLE=nginx-xhttp`, `make snapshot-check`, and one `make check` on the integrated branch.
