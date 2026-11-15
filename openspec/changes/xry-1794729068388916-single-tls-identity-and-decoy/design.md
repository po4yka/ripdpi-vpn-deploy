## Context

`proposal.md` gives the motivation. `enable_reality_self_steal` is `false` in `group_vars/all.yml` and in the live profiles, so the borrowed target is the common layout. `REQ-TMD-REALITY-CONSISTENCY` already states that a borrowed target fails the owned-name comparison by construction; this change adds the network comparison and a production gate on the result. The self-steal role copies `files/public-site/*` with a file glob. The nginx-xhttp port 80 server has one `server` block with `return 301 https://$host:<port>`.

## Goals / Non-Goals

- Goal: a scan of one production address shows one certificate identity, or the operator recorded why not.
- Goal: no production node serves site bytes that this repository publishes.
- Non-goal: a new default profile. The operator still selects self-steal or a borrowed target.
- Non-goal: the Hysteria obfuscation default and port choice. The measurement task for transport signatures owns those.

## Decisions

- The self-steal input copies the nginx-xhttp contract (`nginx_xhttp_public_site_dir`): a controller-local directory, enumerated and published in one transaction, with the same production refusal. Rejected: reuse the nginx-xhttp variable, because the two roles can serve different names.
- The validator gets the node address as an explicit argument and looks up both ASNs through the existing `probe-asn.sh` budget. `unknown` does not fail the validator, because the lookup depends on an external service; the production gate treats `unknown` as a refusal reason only when no previous recorded result exists.
- The gate lives in one preflight task file that the xray and hysteria roles include, so that either role refuses the layout. Rejected: a check in `site.yml`, because the roles also run from other playbooks.
- The exception is one variable with a free-text reason. The manifest records only that it is active. Rejected: one acknowledgement variable for each case, because the operator decision is the same.
- Port 80 serves the decoy root directly when the XHTTP port is not 443. Rejected: close port 80, because the Hysteria ACME path and the listener contract use it.

## Contracts and ownership

- Ansible: `ansible/roles/reality-self-steal/` tasks, defaults, cleanup and Molecule; `ansible/roles/nginx-xhttp/templates/site.conf.j2` and its snapshot; a shared preflight under `ansible/playbooks/tasks/`; `ansible/roles/node_manifest/`.
- Scripts: `scripts/reality_target_validation.py` and its report schema.
- Configuration: new variables `reality_self_steal_public_site_dir` and `tls_identity_exception`.
- Docs: `docs/research/reality-target-selection-2026-07.md` is unchanged; the self-steal and deploy guides state the new inputs.

## Risks / Trade-offs

- Existing production nodes with a borrowed target and Hysteria on UDP/443 fail the next deploy → the failure message names the two listeners and the three ways to pass: self-steal with a shared certificate, another Hysteria port, or the recorded exception.
- ASN equality is a coarse test of network neighbourhood → it is the rule the secrets example already states; the report keeps the three-value result so that a finer test can replace it.
- A site that serves content on port 80 without a redirect loses the HTTPS upgrade → the decoy has no user sessions, and the XHTTP-on-443 layout keeps the redirect.

## Migration Plan

Merge, then for each production node choose the layout or record the exception before the next deploy. Deploy through the ordinary dry-run and deploy transaction. Rollback is a revert and a second deploy. Gates: the validator unit tests, `make molecule-test ROLE=reality-self-steal`, `make molecule-test ROLE=nginx-xhttp`, `make snapshot-check`, and one `make check` before handoff.
