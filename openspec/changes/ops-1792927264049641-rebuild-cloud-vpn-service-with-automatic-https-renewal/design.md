## Context

This is a fresh fleet. Old grants and runtime data are retired. The operator
approved a bounded cloud topology and encrypted local and vault storage.
Personal devices must not supply runtime, monitoring or renewal capabilities.
The existing nginx publication helper already validates complete candidates,
locks the nginx unit and refuses an unrelated writer during an open ingress
transaction. Hysteria has native ACME support in its pinned server release.

## Goals / Non-Goals

- Goal: current small provider plans, useful public pages and autonomous public
  TLS, with bounded private cloud monitoring and positive live protocol checks.
- Non-goal: reuse old credentials, expose administration publicly, add an
  unrestricted ingress path, claim a filtered-network result from cloud probes,
  or create an external notification dependency without authority.

## Decisions

- Rotate an approved exact public IPv4 SSH source through the existing firewall
  transaction. Bind the accepted file and complete live policy in the reviewed
  plan. Replace one native rule for both activation and compensation; do not
  reload a table or clear timed sets. Retain the operation type until fresh
  public and Tailnet management proofs permit finish. A durable committing
  decision resumes forward after a lost acknowledgement. Foreign changes
  refuse recovery before any file or kernel write.
- Keep three transport hosts and a separate observer. Size the observer from
  existing memory, data and free-space admission rules, not only image size.
  All provider IDs, exact costs and private host inputs stay in the operator kit.
- Extend the current UpCloud root with admitted small Starter SKUs and an
  explicit management-only purpose. This purpose forbids protocol listeners;
  it does not relax SSH allowlists or provider-plan policy.
- Bind the Scaleway root disk size and storage class explicitly and expose
  neither extra disks nor snapshots by default.
- Add an explicit ACME certificate alternative to the nginx and Hysteria secret
  contracts. A certificate has one authority: supplied bytes or ACME, never both.
  The controller validates this shape; cloud admission validates managed bytes.
- Use the pinned Hysteria server's native ACME HTTP challenge and private data
  directory. Its certificate cache stays outside sealed configuration inputs;
  native renewal avoids an external restart or duplicate certificate writer.
  Admit the HTTP challenge in the listener manifest and forbid a competing
  nginx HTTP listener for that native challenge.
- Integrate nginx ACME tasks into the existing nginx role. Install inert ACME prerequisites before the protected ingress transaction.
  Declare one additional typed public-TLS owner in that transaction. After
  the guarded firewall publication, prepare its HTTP challenge, obtain the
  certificate and publish the complete HTTP/certificate candidate through the
  existing helper. Managed TLS files belong only to this owner; the application
  owner must not write them. Parent compensation covers the accepted TLS owner
  together with the application owners.
- Keep the full deployment alive and owned between HTTP preparation and CA
  issuance. A controller wait allows at most 600 seconds for three consecutive
  equal samples from two public DNS resolver views. Every managed name must
  resolve to the exact Terraform-owned IPv4 and optional IPv6. Auxiliary names
  may alias the canonical name; unrelated aliases and stale addresses refuse.
  The operator verifies the real HTTP 301 and canonical Location from a cloud
  host before the separate reviewed DNS apply. Timeout, DNS child interruption
  or CA failure enters normal host compensation. Controller cancellation or
  loss can retain the journal for ordinary interrupted-transaction recovery.
  DNS can remain changed after later CA failure; preserve that outcome and
  retry the ordinary full deployment. No partial graph, interactive pause or
  manual certificate-helper invocation is introduced.
- Use the official OS Certbot package, a role-owned hardened persistent timer
  and a small activation adapter. Validate SAN, key match and remaining validity
  before giving the complete HTTP/certificate write set to the shared publication helper.
  The autonomous renewal path refuses an open ingress transaction under the
  shared unit lock; the explicit deployment path participates as its declared
  TLS owner. Every timer run
  reconciles the current lineage so a failed post-renewal activation retries.
  Existing valid supplied-certificate workflows remain distinct supported
  workflows; this is not an alias for old managed authority.
- Check native ACME listener conflicts against both effective transport toggles.
  Inactive sibling TLS inputs do not claim a public listener during client issuance.
- Keep the public article content and routes. Improve layout, navigation and
  the canonical-host response; check rendered output at narrow and wide sizes.
- Keep the monitoring resource ceilings. Add an explicit panel-only mode with
  node and pipeline health, no fabricated delivery heartbeat and no Telegram
  credentials. The owner selected the private panel and provider notifications.
  Production and cloud observer admission remain explicit; no retired dedicated
  collector or old acceptance receipt is reused.
- Keep agent installation, rotation and removal in the exact-host observability
  lifecycle. Full VPN convergence must preserve that independently owned runtime.
- Admit the operator-owned static site through one typed override. Snapshot its
  bounded, owner-controlled regular files before convergence, reject links and
  unsafe ancestry, and recheck the source tree before host writes.
- SSH ownership schema 2 requires an explicit VPN or observer inventory section.
  Keep identical source, dual-path and rollback checks for both sections.
- Allow 7200 seconds for a complete first-convergence or preview session on
  admitted small nodes. Keep the separate SSH, native validation and transaction
  deadlines, owned-child cancellation and failed-preflight refusal.
  Final protocol collection uses the same owned-session supervisor for every
  SSH worker. INT, TERM, HUP and QUIT must reclaim probe sessions before the
  collector exits or releases the fleet verification locks.
- Use per-provider encrypted operator documents and separate runtime grants.
  Remote backups use the checksum-pinned official rclone Debian package with
  B2 API v4 authorization. Keep dpkg ownership and the existing narrow grants;
  both backup entrypoints use one installer and check mode does not download.
  The decryption identity has an independently verified vault copy. Temporary
  plaintext identities and operation output are removed when no longer needed.
- Store Xray logs at the root-owned `/var/lib/vpn-xray-logs`, outside both the
  OS-managed group-writable log directory and the runtime user's home. Keep
  descriptor checks, file modes and all log readers aligned with this path;
  deployment must not change the shared system log directory to gain admission.

## Contracts and ownership

- Terraform: UpCloud, Scaleway and Vultr roots, policies and matching mock tests.
  Vultr uses an explicit zone and stable record map for A, AAAA and CNAME.
  Import retained record IDs with their current values before changing endpoint
  addresses. Do not create the zone or keep the old AAAA-only input contract.
- Ansible: nginx-xhttp ACME tasks, adapter and units; Hysteria ACME inputs and
  cache; listener manifest; protected ingress write-set declaration; current
  bounded observability roles and panel-only admission.
- Secrets: mutually exclusive supplied/ACME TLS fields, validators, examples and
  coverage. Managed public certificate validation moves to the admitted target;
  it cannot be silently skipped on a supplied-certificate configuration.
- Operator scripts: effective certificate selection and canonical Make/deploy
  interfaces. No provider credentials enter Terraform variables or saved-plan
  diagnostics. No new vpnd-only deployment path is introduced.
- Web: existing public-site templates/assets and their rendered snapshots/tests.

Native Hysteria admission has two evidence classes. Its exact binary first uses
an explicit temporary TLS projection inside the private validation lease. The
live unchanged ACME configuration must then pass authenticated forwarding with
system trust and the expected SNI before receipt commit. Its mutable cache stays
outside the sealed generation. Projection evidence is not issuance or renewal.

Native backups restore their own full snapshot ID into private scratch and
validate the exact five-file certificate/account set before retention or remote
replication. Explicit fresh recovery normalizes service ownership and uses the
same pinned native server, unchanged ACME policy and an isolated disposable cache
bind mount for authenticated warm admission. Its private publication journal
binds snapshot, policy, manifest and exact directory identities. One same-FS
rename replaces only the empty fresh cache; an interrupted commit reconciles
those exact identities. Ordinary convergence does not copy or recursively chown
cache contents. Offline authority checks cannot prove that the CA still accepts
the restored account key; separate online renewal remains required evidence.

The nginx renewal coordinator holds the existing unit lock before CA operations.
A private durable claim binds each lineage to its exact policy and survives
failed issuance. An existing unclaimed lineage refuses adoption. Only accepted
certificate publication changes the timer configuration; ingress compensation
restores that configuration with the prior certificate. The issuer child sees
nginx state read-only. Explicit panel-only monitoring disables delivery and relay
authority. Its pipeline proves fresh node samples and advancing expected-target
rule evaluation, without a notification receipt.

## Risks / Trade-offs

- HTTP-01 requires DNS to resolve to the target. On these absent old hosts,
  publish DNS after basic HTTP readiness, then issue TLS and activate the
  protected service. Never keep a retired IPv6 record beside a new IPv4 record.
- Native Hysteria ACME HTTP and nginx HTTP cannot share a bind address/port.
  Reject that combination instead of adding a second certificate path.
- Renewal can meet deployment publication. The shared unit lock and protected
  transaction admission preserve prior authority; retry activation on a later
  timer even when the renewed certificate is no longer due for issuance.
- The observer shares a provider with one transport host but is independent of
  the collector and uses a distinct placement. Do not claim independence from
  failure of that whole provider.
- Provider rates, available images, stock, source IP and taxes can change.
  Recheck exact plans and authorized cost bounds immediately before creation.
- Panel-only monitoring detects state but does not prove an external message or
  human receipt. Provider account notifications remain provider-owned settings.

## Migration Plan

1. Save and read back new operator grants, verify provider APIs and reconcile the
   private catalog. Verify encrypted restore before relying on offsite backup.
2. Implement and test provider inputs, certificate authority and public pages.
   Run targeted behavior tests, template snapshots, relevant native/Molecule
   checks and the cross-layer local gate. Review the actual patch independently.
3. Use one time-bounded staging node to qualify the supported protocol paths.
   Record exact source and runtime evidence; retire the exact test resources.
4. Review saved provider plans, then create only the approved bounded hosts.
   Verify host identity, SSH recovery, Tailnet enrollment and ownership before
   ordinary deployment. Admit the observer independently of the VPN fleet.
5. Set DNS at the HTTP readiness boundary, issue public TLS, deploy the reviewed
   service and verify HTTPS, renewal, reboot and authenticated cloud-client paths.
6. Restore encrypted backup in isolation, preserve honest evidence categories
   and finalize private recovery information. Failure leaves working certificate
   generations intact; failed new nodes use exact-resource cleanup rather than
   adoption of retired authority.

Changing a live supplied certificate owner into an ACME owner is outside this
fresh-node rollout. Such a node must be recreated under a reviewed plan; do not
adopt a foreign active certificate receipt or restore old bytes over new TLS.
