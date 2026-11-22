## Purpose

Define the dedicated egress node that gives CI one fixed source address for provider API calls: its CONNECT-only allowlist proxy, Tailnet-only access path, hardening, secret-free state, provider-side allowlists and break-glass procedures.

## ADDED Requirements

### Requirement: REQ-EGRESS-CONNECT-ONLY — Only CONNECT to allowlisted API hosts on 443

The proxy MUST accept only the HTTP `CONNECT` method, only to port 443, and only to host names on the allowlist (`api.hetzner.cloud`, `api.scaleway.com`, `api.upcloud.com`, `api.vultr.com`, the configured `s3.<region>.backblazeb2.com`, `api.porkbun.com`, `api-ipv4.porkbun.com`, `api.tailscale.com`). It MUST reject IP-literal targets and every other method, and it MUST NOT terminate or inspect TLS.

#### Scenario: Plain HTTP request

- **WHEN** a client sends `GET http://example.com/` to the proxy
- **THEN** the proxy answers 403 and opens no upstream connection

#### Scenario: Host not on the allowlist

- **WHEN** a client sends `CONNECT github.com:443`
- **THEN** the proxy answers 403

#### Scenario: Allowlisted host on another port

- **WHEN** a client sends `CONNECT api.vultr.com:80`
- **THEN** the proxy answers 403

#### Scenario: Numeric target has an allowlisted reverse DNS name

- **WHEN** an IP-literal target has a PTR record for an allowed hostname
- **THEN** the proxy refuses the request without contacting the upstream

### Requirement: REQ-EGRESS-TAILNET-ONLY — The proxy is reachable only from granted Tailnet tags

The proxy MUST listen only on the node's Tailnet address. nftables MUST drop the proxy port on every other interface, and the Tailnet policy MUST grant the port only to `tag:ci-tofu` and optionally one named operator device. The node MUST expose no public inbound service.

#### Scenario: Public scan

- **WHEN** the proxy port is probed on the public address
- **THEN** there is no answer

#### Scenario: Deploy-tag runner

- **WHEN** a `tag:ci-deploy` runner connects to the proxy port
- **THEN** the Tailnet drops the connection

### Requirement: REQ-EGRESS-SECRETLESS — The node holds no operator or provider credential

The node, its OpenTofu state outputs and its Ansible variables MUST NOT contain provider tokens, state passphrases, age identities or SOPS documents. Its access log MUST record only time, client, target host, status and byte counts.

#### Scenario: Node compromise review

- **WHEN** the node disk is inspected
- **THEN** it holds only its Tailnet node key, SSH host keys and the proxy configuration

### Requirement: REQ-EGRESS-HARDENED — The proxy runs as a hardened unit

The proxy MUST run as an unprivileged user under a systemd unit that meets the repository hardening floor (`systemd` skill), with a pinned package version, bounded connection and file-descriptor limits, and restart on failure.

#### Scenario: Unit audit

- **WHEN** `systemd-analyze security` runs on the unit
- **THEN** the exposure score meets the floor recorded in the role's Molecule test

### Requirement: REQ-EGRESS-FIXED-ADDRESS — The source address survives recreation

The public IPv4 MUST be a retained primary IP resource that is reassigned to a recreated server. A server recreation MUST NOT change the address that provider allowlists name.

#### Scenario: Server replaced

- **WHEN** the egress server is destroyed and recreated by `tofu apply`
- **THEN** the new server uses the same IPv4 and the Vultr API accepts calls through it

### Requirement: REQ-EGRESS-PROVIDER-PROOF — Every provider client works through the proxy

Before any provider allowlist is enabled, each OpenTofu provider used by the fleet and the B2 backend MUST be shown to complete `tofu plan` with `HTTPS_PROXY` set to the egress proxy, with the proxy log showing `CONNECT` to that provider's host.

#### Scenario: Provider ignores the proxy

- **WHEN** a provider's plan succeeds but the proxy log shows no `CONNECT` to its host
- **THEN** that provider's allowlist is not enabled and the gap is recorded

### Requirement: REQ-EGRESS-ALLOWLISTS — Provider allowlists name only the egress address

The Vultr API access control MUST list only the egress IPv4 (and IPv6 if used) and MUST NOT list the workstation's rotating address. Optional allowlists at UpCloud, Scaleway and Porkbun MUST name only the egress address.

#### Scenario: Call from a runner address

- **WHEN** a runner calls the Vultr API directly
- **THEN** Vultr rejects the call

### Requirement: REQ-EGRESS-BREAK-GLASS — Documented recovery when the proxy, VPS or GitHub is down

The runbook MUST repair a stopped proxy through pinned management SSH on the Tailnet. For a lost server it MUST recreate only the egress root using direct Hetzner and B2 access with the W3 lock, retain its IP, verify the new host identity and enroll it before restoring proxied jobs. The operator MUST be able to perform this recovery without GitHub. Emergency Vultr console access MUST be time-limited and recorded.

#### Scenario: Proxy and GitHub both down

- **WHEN** the operator must recreate a Vultr node with GitHub and the proxy unavailable
- **THEN** the runbook leads to a successful apply from the MacBook and a receipt that records the temporary allowlist entry and its removal

#### Scenario: Proxy process and server recovery

- **WHEN** separate drills stop the service and remove a disposable egress server
- **THEN** the first drill restores the service through management SSH and the second restores the retained address and provider connectivity without depending on the lost proxy
