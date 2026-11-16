## Context

`proposal.md` gives the motivation. The live Node A runs `vpn-split-hop-family-egress-live`: REALITY, nginx-xhttp, Hysteria and AmneziaWG on one address, with every recipient flow leaving through Node B. `ansible/playbooks/tasks/tls-identity-preflight.yml` refuses a borrowed REALITY target beside those listeners on a production host. The `reality-self-steal` role already supports a host that also runs nginx-xhttp: it requires one certificate when both use the same name, and it refuses a self-steal port that is a public TCP listener.

## Goals / Non-Goals

- Goal: a production host in the live family-egress profile passes the TLS identity preflight with no exception.
- Goal: the profile renders a self-steal port that the role's port guard admits.
- Non-goal: change the onboarding profile `vpn-split-hop-ingress-live` or the staging profiles. Onboarding a new live Node A through the ingress profile on a production host still needs a layout decision; that is separate work.
- Non-goal: change a role, a template, the secrets schema or Terraform.

## Decisions

- Change the existing live profile instead of adding a second live family-egress profile. The pair has one Node A, and a second complete `vpn` map would duplicate every toggle. Rejected: `tls_identity_exception` in private extra vars, because it keeps the two-identity layout and the operator chose self-steal.
- Set `reality_self_steal_port: 8444` at the top level of the profile. The role default 8443 equals `nginx_xhttp_public_port`, which this profile inherits, and `reality-self-steal/tasks/configure.yml` refuses a self-steal port that is a public TCP listener. No role, playbook or script uses 8444. Rejected: move the public nginx-xhttp port, because devices and DNS-01 certificates of the live pair already use it.
- Keep the profile's other keys unchanged. `test_split_hop_live_node_a_keeps_the_production_device_transports` pins the profile to the device transports plus named differences, so the two new values are added there as named differences.

## Contracts and ownership

- `ansible/group_vars/vpn-split-hop-family-egress-live.yml`: owns `vpn.enable_reality_self_steal: true` and `reality_self_steal_port: 8444`.
- `ansible/roles/reality-self-steal`: unchanged. It owns the secret contract (`reality_self_steal.server_name`, `cert_pem`, `key_pem`), the transport contract (`xray.target`, `xray.server_names`), the one-certificate rule for a name shared with nginx-xhttp, and the operator-owned site rule for production.
- Private inputs of the live Node A (outside Git): its SOPS document gains `reality_self_steal` with the nginx-xhttp name and certificate, `xray.target` becomes `127.0.0.1:8444`, and `xray.server_names` holds only that name. Its extra-vars file gains `reality_self_steal_public_site_dir` and `nginx_xhttp_public_site_dir`.
- `docs/reference/deploy-profiles.md`: the row of the live family-egress profile states the self-steal identity.

## Risks / Trade-offs

- The combination of self-steal and nginx-xhttp on one host has unit coverage of each rule but no Molecule scenario for both roles together → the live rollout keeps a full dry-run before the deploy, and the nginx candidate inspection runs in check mode.
- Devices on the live Node A lose REALITY until they import the new entry → the device refresh runs right after the deploy, and the other three transports keep working.
- A host in this profile deployed with old secrets is refused → this is the intended fail-closed path; the refusal happens before mutation.

## Migration Plan

Forward: merge the profile change; update the live Node A SOPS document and extra-vars file; run the full dry-run and review it; deploy; reinstall Node B's liveness sentinel for the new Node A identity; refresh the device payload. Rollback: revert this change, restore the previous `xray.target` and `xray.server_names`, and redeploy with a recorded `tls_identity_exception`; the role retires its owned endpoint. Compatibility break: the REALITY entry of each device on the host. Gates: the unit tests named in `tasks.md`, `make snapshot-check`, the hosted CI on the merge commit, and the live dry-run.
