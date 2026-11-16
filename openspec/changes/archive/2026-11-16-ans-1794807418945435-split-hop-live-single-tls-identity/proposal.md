# Change: Present one TLS identity on the live split-hop Node A

Task ID: `ANS-1794807418945435`

## Why

The live split-hop Node A profile serves REALITY with a borrowed target on TCP/443 next to nginx-xhttp and Hysteria, which present the operator certificate on the same address. One scan of that address therefore sees two unrelated TLS identities. The TLS identity preflight refuses this layout on a production host, and the live pair is a production host, so Node A can no longer be redeployed from the current source. The profile's `vpn` map is canonical: the deployment controller replaces the host's map with it, and the private extra-vars allowlist does not admit transport switches. The operator chose REALITY self-steal for Node A on 2026-11-16, and that choice needs a tracked profile change.

## What Changes

- The profile `vpn-split-hop-family-egress-live` enables REALITY self-steal, so TCP/443 presents the operator certificate that nginx-xhttp and Hysteria already present.
- The same profile sets the loopback self-steal port to a private port that differs from its public nginx-xhttp port. The role default equals that public port, and the role refuses a self-steal port that is a public listener.
- BREAKING for the live pair: the next deploy of a host in this profile needs a `reality_self_steal` secret, `xray.target` on the new loopback port, `xray.server_names` with only the owned name, and an operator-owned site directory. The REALITY entry of every device on that host changes.

## Capabilities

### New Capabilities

- `ansible/split-hop-live-tls-identity`: the TLS identity that the live split-hop Node A profile presents on a production address.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/group_vars/vpn-split-hop-family-egress-live.yml` only. No role, template, schema or Terraform change.
- Secrets and private inputs: the live Node A SOPS document and its extra-vars file change at deploy time. They are outside Git.
- Clients: the device payload for REALITY changes for devices on the live Node A. Other transports keep their credentials.
- The onboarding profile `vpn-split-hop-ingress-live` and both staging profiles keep their layout.
