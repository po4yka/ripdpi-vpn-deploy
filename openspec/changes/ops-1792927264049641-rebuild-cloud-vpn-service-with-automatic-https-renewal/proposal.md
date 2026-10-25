# Change: Rebuild the cloud VPN service with managed public TLS

Task ID: `OPS-1792927264049641`

## Why

The previous fleet and its credentials were retired. A new fleet must run
without personal devices, serve the existing public information site, and
renew public certificates while the operator workstation is offline.
The current nginx role accepts operator-delivered certificate bytes only.
Current provider inputs also omit the selected small Starter plans and an
explicit cost bound for the site root disk.

## What Changes

- Create reproducible input contracts for small current cloud plans, bounded
  site storage, and a management-only independent cloud observer.
- Add cloud-managed ACME issuance and renewal with validated certificate
  activation, explicit consumer ownership, and safe failure handling.
- Improve the public information site's navigation, reading layout, responsive
  behavior and metadata without publishing access or management data.
- Admit an explicitly provisioned cloud observer and a separately verified
  production environment to the existing resource-bounded monitoring workflow.
- Keep provider credentials encrypted in the private operator kit and separate
  broad operator access from narrow runtime credentials.
- BREAKING: a managed certificate is owned by its cloud issuance lifecycle;
  deployment must not replace it with an older operator snapshot.

## Capabilities

### New Capabilities

- `operations/managed-public-tls`: issue and renew public endpoint certificates
  without an online operator workstation; validate and activate consumers.
- `infrastructure/bounded-cloud-node-inputs`: admit current small plans, exact
  root storage and an explicit management-only observer purpose.
- `web/public-information-site`: serve readable, responsive, navigable public
  articles with correct routes and metadata.

### Modified Capabilities

- `operations/resource-bounded-observability`: allow an explicitly approved
  cloud observer and independently admitted production rollout without
  restoring the cancelled dedicated collector topology.

## Impact

- Terraform provider inputs, policies and mocked provider tests.
- Ansible certificate, ingress and observer lifecycle contracts, secret input
  admission, certificate consumers, renewal units and their tests.
- Public site assets/templates, snapshots and rendered browser checks.
- Private provisioning inputs, encrypted operator material and live acceptance.
  No provider credential values or private deployment addresses enter Git.
