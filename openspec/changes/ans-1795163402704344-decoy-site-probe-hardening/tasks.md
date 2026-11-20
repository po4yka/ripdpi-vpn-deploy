# ANS-1795163402704344: Harden the decoy sites against content clustering and bare-address probes

## Objective

The nginx-xhttp and reality-self-steal sites refuse repository-bundled bytes and dot paths in an operator-owned tree, send no certificate to a handshake that does not name the site, accept the TLS versions and groups of an ordinary site, and hold more idle connections on the self-steal target.

## Ownership

`ansible/roles/reality-self-steal/`; in `ansible/roles/nginx-xhttp/` the files `templates/site.conf.j2`, `templates/public-acme.conf.j2`, `tasks/enable.yml`, `tasks/routing-lists.yml`, `molecule/default/verify.yml` and `CLAUDE.md`; `tests/unit/test_public_site_contract.py`, `tests/unit/test_reality_self_steal.py` and the two vhost goldens. The Terraform listener contract, the firewall and the live rollout belong to other owners.

## Execution

- [x] ANS-1795164066655530 Add the bundled-bytes and dot-path gates to both site roles with their tests #bug !high @item:ANS-1795163402704344
- [x] ANS-1795164144591321 Add the default TLS server and the shared TLS policy to both vhosts with tests and Molecule checks #bug !high @item:ANS-1795163402704344
- [x] ANS-1795164238196044 Raise the self-steal connection limits, the certificate lifetime floor and the opt-in TCP/80 redirect #bug !high @item:ANS-1795163402704344
- [x] ANS-1795164360045220 Fix the XHTTP timeouts, error statuses, ACME 404 and routing-list base URL, and correct the role notes #bug !high @item:ANS-1795163402704344

## Verification

Local: `pytest tests/unit/test_public_site_contract.py tests/unit/test_reality_self_steal.py tests/unit/test_transport_site_transaction.py tests/unit/test_agent_instructions.py`, `make snapshot-check`, `ansible-lint` on the two roles, and `make task-check`. Hosted CI runs Molecule for both roles; the pinned image has no build for the local arm64 Docker host. Dry-run, staging, live and client evidence wait for the operator rollout after each node has its own site content.
