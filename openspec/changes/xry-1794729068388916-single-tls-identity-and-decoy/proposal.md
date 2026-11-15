# Change: Give each node one TLS identity and an operator-owned decoy

Task ID: `XRY-1794729068388916`

## Why

The 2026-11-15 audit found that one scan of a default node shows more than one TLS identity, and that one decoy is the same on every node:
- The self-steal role publishes three fixed files from this public repository as its site. The role has no input for an operator site and no production refusal, while `REQ-TMD-OWNED-DECOY` already gives nginx-xhttp both. Every self-steal node answers TCP/443 with the same bytes.
- With a borrowed REALITY target, TCP/443 presents the target's certificate. The validator records the target's ASN and never compares it with the node's network, although the secrets example lists that comparison as a selection rule.
- On the same address, Hysteria on UDP/443 and nginx on the XHTTP port present the operator certificate. A client and a scanner both see two unrelated names on one address.
- The port 80 server redirects every Host to the XHTTP port when that port is not 443. A redirect to a non-standard port is unusual for a web site and points a scanner at the second identity.

## What Changes

- The self-steal role publishes the site from an operator directory and refuses production without one.
- The REALITY target validator reports whether the target and the node are in the same network, when the operator supplies the node address.
- BREAKING: production refuses a borrowed REALITY target beside Hysteria or nginx-xhttp on the same address, and a borrowed target that the operator recorded as being in a different network, unless the operator records a measured exception with a reason.
- BREAKING: each port 80 server serves the decoy site when the HTTPS port of its name is not 443. It sends no redirect to another port, and a default server answers an unknown Host with the decoy 404 page.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `security/traffic-metadata-and-decoy-identity`: adds the self-steal decoy ownership rule, the single-identity production gate and the port 80 behaviour.
- `transports/reality-target-validation`: adds the target network comparison to the report.

## Impact

- Ansible: `ansible/roles/reality-self-steal/`, `ansible/roles/nginx-xhttp/templates/site.conf.j2` and `public-acme.conf.j2`, a shared preflight imported by `ansible/playbooks/site.yml` and the xray, hysteria and nginx-xhttp roles, `ansible/roles/node_manifest/`, `ansible/group_vars/all.yml`.
- Scripts: `scripts/reality_target_validation.py`; `scripts/validate-ansible-extra-vars.py`, `scripts/deploy-controller.py` and `scripts/fleet-maintenance.py` accept the new operator inputs.
- Secrets: `secrets/prod.secrets.example.yaml` comment for the target rule; no new secret.
- Operations: a production node with a borrowed target beside Hysteria or nginx-xhttp, or with a recorded `reality_target_network: different_asn`, fails preflight until the operator changes the layout or records the exception. Every committed profile that enables REALITY with Hysteria or nginx-xhttp and without self-steal is affected on `env: prod`.
