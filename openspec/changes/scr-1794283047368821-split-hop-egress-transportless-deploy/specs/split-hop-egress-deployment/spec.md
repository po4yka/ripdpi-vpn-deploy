## Purpose

Let the canonical deployment controller converge a split-hop egress node that publishes no client listener, without weakening the SSH promotion proof for any node that does publish one.

## ADDED Requirements

### Requirement: REQ-NLP-CONTRACT — Admission needs the host's own empty listener contract

The deployment controller MUST admit a `no-public-listener` promotion document only when the host's own inventory row records an empty provider listener contract and no group-wide inventory variable, operator override or deployed secret sets that contract. It MUST refuse every other host before the first SSH contact.

#### Scenario: Host with an empty contract in its own row is admitted

- **GIVEN** an egress-only host whose inventory row records an empty provider listener contract
- **WHEN** `make deploy` runs with a `no-public-listener` promotion document for that host
- **THEN** the controller proceeds to SSH without invoking the sentinel proof validator

#### Scenario: Contract that lists, lacks or shadows a listener is refused

- **GIVEN** a host whose contract lists a listener, is absent, or is set only in `[vpn:vars]` or in the deployed secrets
- **WHEN** `make deploy` runs with a `no-public-listener` promotion document for that host
- **THEN** the controller refuses before any SSH contact

### Requirement: REQ-NLP-TOGGLES — Admission needs an explicit egress-only toggle set

The deployment controller MUST admit a `no-public-listener` promotion document only when the host's effective `vpn` sets `enable_split_hop_egress` to true and each of `enable_xray_reality`, `enable_nginx_xhttp`, `enable_hysteria` and `enable_amneziawg` explicitly to false.

#### Scenario: Absent or enabled transport toggle is refused

- **GIVEN** a host with an empty contract whose effective `vpn` omits the Hysteria toggle or disables `split-hop-egress`
- **WHEN** `make deploy` runs with a `no-public-listener` promotion document for that host
- **THEN** the controller refuses before any SSH contact

### Requirement: REQ-NLP-TRANSACTION — The SSH transaction keeps every fresh management check

The SSH baseline transaction MUST bind a `no-public-listener` document to the exact target identity before prepare, and for that kind it MUST skip only the external sentinel proof while keeping the fresh status RPC and SFTP session on every management transport, the final status, confirm and rollback.

#### Scenario: Admitted node commits after fresh management checks

- **GIVEN** a `no-public-listener` document bound to the transaction target
- **WHEN** the baseline transaction applies a changed sshd configuration
- **THEN** it runs status and SFTP on each management transport, runs no sentinel proof, and confirms

#### Scenario: Document bound to another target is refused

- **GIVEN** a `no-public-listener` document whose target identity, schema version or field set differs from the expected one
- **WHEN** the baseline transaction starts
- **THEN** it refuses with `promotion-proof-mismatch` before prepare

### Requirement: REQ-NLP-PROVIDER — UpCloud provisions a listener-free Node B

The UpCloud provider root MUST accept `node_purpose = "split-hop-egress"` only with an empty public listener set, no legacy listeners and no Hysteria, and MUST keep refusing an empty listener set for an ordinary VPN node.

#### Scenario: Split-hop egress purpose plans with no listener

- **GIVEN** `node_purpose = "split-hop-egress"`, `public_listeners = []` and `enable_hysteria = false`
- **WHEN** Terraform plans the UpCloud root
- **THEN** the plan publishes no listener and creates no observer storage

#### Scenario: Split-hop egress purpose refuses a public listener

- **GIVEN** `node_purpose = "split-hop-egress"` with a TCP/443 public listener
- **WHEN** Terraform plans the UpCloud root
- **THEN** the firewall precondition fails
