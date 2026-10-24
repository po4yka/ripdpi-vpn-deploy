# ansible — runtime state ownership

## Design decisions

Transport preflight passes the exact AWG Go and tools commits with the private instance authority. Range and signature admission requires both reviewed commits before runtime mutation. The role normalization path uses the same inputs.

The protected activation orchestrator closes standalone full retirement through `playbooks/tasks/transport-egress-finish.yml`. A surrounding ingress site transaction retains completion ownership instead, including the exact revocation authority in its durable commit decision.

Explicit empty Xray/Hysteria client lists retire their effective transports.
Empty named REALITY cohorts and Snell variants are excluded before admission;
an empty variant must never fall back to shared Snell authentication. The
Snell projection filters public variants and private runtime users together;
it retains the complete encrypted authority outside Ansible runtime facts. Device
credential rotation invokes the full role lifecycle even for disabled transports,
so retained old credentials cannot survive a successful fleet revocation. AWG
retirement retains its existing firewall transaction. Naive empty-client
handling remains the canonical role's explicit authentication retirement.

Alternate REALITY listeners default to disabled (`xray_fallback_port: 0`).
An explicit alternate must match the provider listener contract and is probed
independently from TCP/443; choosing another port does not hide its protocol.
Full-stack Molecule declares its opt-in at host scope so canonical playbook
group-vars discovery cannot replace the fixture port with the disabled default.
The optional nonsecret `client_payload_failover` group input is consumed only
by RIPDPI recipient export and requires two operator-owned HTTPS controls.

Site baseline defers managed DNS stub restoration until DNS-Morph has retired
its listener. The retiring role calls only baseline's resolver tasks; tagged
runs that omit retirement retain the working upstream resolver.

DNS-Morph controller admission runs after exact-node ownership in site pre_tasks, before host changes and
at standalone role entry. Both use the same bounded YAML validator and rendered
role contract; malformed seed material and implicit echo-only inputs refuse in
normal and check mode. Split-hop ingress retains its UID output boundary when
the WireGuard route stops, independently from its policy-routing lifecycle.

Shared protocol admission rejects VLESS authentication aliases and AWG peer
prefixes containing any instance server address before publication. Snell and
Trojan templates retain exact credential bytes through JSON serialization.
Subscription privacy defaults cover the whole virtual host, including refused
paths, while route-specific rate limits remain unchanged.

Debian13 Molecule consumers share one immutable image digest. Refresh it through
the existing CI publisher, require its current HIGH/CRITICAL scan to pass, and
update every Molecule consumer plus the pin guard together. The parent image
and scanner policy remain separate reviewed inputs.

Initial firewall publication is retained through the protected ingress commit.
It uses accepted AWG claims until the AWG consumer takes ownership after that
commit. AWG rollback therefore restores post-protected policy and preserves
committed frontend ports. Tagged runs refuse unrelated protected listener
changes before publication. The durable ingress commit also finishes its exact
firewall owner; an interrupted acknowledgement cannot turn a committed route
into an old firewall generation.

AWG consumer acceptance retains executable bytes, shared units, complete configs
and instance membership in one private runtime transaction. Its separate firewall
decision covers unchanged-runtime policy changes too. Confirm candidate quiescence
before restoring files; retain recovery authority when stop cannot be proven.

Optional transport candidates retain native parser admission before publication.
Naive excludes request-bearing HTTP errors from retained logs. The mtg consumer
uses the shared verified archive lifecycle and admits FakeTLS input before host
mutation; source validation does not enable its research profile.

Hysteria smoke mirrors enabled Salamander in its private client document and retains verified TLS with the effective inner/server identity.

Protected commit keeps a durable `committing` ingress journal while finishing the native consumer outer route. Both begin and rescue resolve that decision before adopting or compensating an open transaction; a failed roll-forward retains remaining journals and stops. Only an undecided journal may roll back. Lost acknowledgement after journal removal releases compensation ownership as an already completed commit.

ECH smoke clients use the declared inner identity even when the nginx frontend has a different hostname; certificate verification stays enabled.

AWG device source claims are typed by family. The firewall and standalone AWG
role admit the exact IPv6-capable uplink before their runtime mutations; network
routing remains operator/provider authority. AWG candidates retain whole prior
configurations until all instance activations succeed.

AWG singleton and multi-instance deployments both use the nonempty encrypted
instance list. Observer checks and role normalization never synthesize a
legacy `awg0` peer/key authority.

REALITY smoke executes a complete owned start/probe/cleanup transaction for each effective cohort or primary/fallback listener. Verification omits the legacy base port when cohorts replace it. Hysteria smoke mirrors Salamander and retains certificate/SNI validation.

AWG verification and watchdog use the same normalized instance list as convergence. Observers receive only interface names; private instance records remain under `no_log`.

The disposable P0/P1/Hysteria profile derives its canonical HTTPS origin from the generated nginx server name and effective primary port, so server masquerade and the served certificate share one authority. Full-stack fixtures retain the same port-aware origin. Its watchdog canary endpoint remains independent.

Full-stack Molecule scenarios keep the default task/recap callback stream with JSON results. Structured YAML result bodies can resemble changed-task lines to the pinned idempotence reporter; genuine persistent changes must still be reported. The operator callback remains YAML.

Both full-stack scenarios import `molecule/prepare-transport-credentials.yml` through their preparation entrypoints, establishing owned runtime mount propagation and proving genuine `LoadCredential` delivery before transport convergence.

**Protected site staging has one compensation owner** — explicit static role imports keep protected preparation, Xray/self-steal/XHTTP/Hysteria staging, shared activation and ingress compensation commit in one rescued block. It closes before unrelated runtime roles. Failure quiesces candidate transports, restores matching protected Nginx authority, then resumes accepted egress. Static imports expose their defaults to preflight just as the prerequisite roles do; shared protocol tags select the full protected sequence. A deploy that finds an undecided ingress site journal left by a killed run adopts it into this same rescue: `transport-ingress-begin.yml` detects it with a read-only `stat` of `site.json`, sets the compensation facts from the egress outer route status, which it reads only after the transport-egress role's shared helper admission (its `helper-authority.yml` task file, also imported first by `runtime-prepare.yml`) accepts the root-owned ancestry and single-link regular helper file, and fails with `interrupted-protected-ingress-transaction`. A refused admission, an unreadable status, or a missing helper whose route state is present or cannot be judged fails closed before adoption with the journal retained: without the helper only an absent `outer.json` in a root-owned 0700 `/var/lib/ripdpi/transport-runtime` directory (the state the helper's own status accepts), or an absent directory, proves the outer route closed, and any other state fails with `egress-outer-helper-missing` and runs nothing, naming the whole `transport_runtime_*.py` helper set to restore. Check mode refuses with the same category without adopting, and the rescue's final message then states that no recovery was attempted. A pending-only ordinary publication journal (no site journal) refuses check mode with the distinct `interrupted-nginx-publication` category, while a deploy recovers a recognized one in the helper's `begin` and then converges the complete graph, which that dry-run could not preview, so the runbook allows it only while source parity holds. Adoption assumes no other live deploy targets the node.

**Protected frontends share one egress generation** — site stages the normalizer, private native gateways and both enabled Xray/Hysteria frontends before activation. Protected transport tags select both frontend consumers so internal authority changes cannot leave one with stale credentials. Host and namespace guards precede listeners; subscription-only and disabled profiles retire consumers first. Hysteria-only hosts acquire the shared pinned Xray runtime without creating a REALITY frontend.

Credential rotation stages enabled protected frontends through these same roles
and activates their shared generation once. It reconciles their approved pinned
runtime/configuration authority and uses the roles' candidate validation and
whole-route rollback, rather than a second config publisher or direct restart
handler. AWG rotation republishes the complete canonical firewall before activating its
complete role lifecycle, so newly assigned typed addresses are admitted, removed
claims disappear and obsolete instances retire. Deployment and AWG rotation share provider/runtime listener admission
before mutation, including read-only comparison in check mode. Rotation performs
transport semantic admission first and retains the prior firewall through AWG activation and
restores it on any refusal. Snell and Naive retain independent rotation flows.

The controller replaces the canonical `vpn` map, so most production profiles omit `enable_transport_egress`. Consumers must derive guarded-generation ownership from the transport egress preparation predicate (`transport-egress-prepare.yml`), never from that optional key with a false default.

**Transport semantic admission precedes mutation** — site and credential
rotation import `playbooks/tasks/transport-input-preflight.yml` before host
changes. Enabled Xray, Hysteria and AWG roles use that same controller-side
entry for standalone invocation. It delegates to localhost without privilege,
executes read-only in check mode, and sends private values only on stdin under
`no_log`. Disabled-role reconciliation bypasses unused transport inputs.

**Exporter endpoint verification shares installation admission** — `verify.yml`
gathers only local network facts and reuses monitoring's literal private endpoint
validator. Custom ports and IPv6 targets match the sender's scrape jobs; public,
wildcard and unapproved Tailnet overrides refuse before the HTTP probe.

Credential rotation enters the enabled Naive role's authoritative validation and
activation lifecycle, so all-profile issuance/removal cannot leave Naive access
unchanged while the other transport credentials rotate.

**Drift inspection is read-only** — `diff-secrets.yml` compares full parsed Xray configuration using the canonical role template and defaults with selected inventory/secrets, then checks enabled services and binary pins. Secret comparisons use `no_log` and never print configuration diffs. The `vpn-ci-*` profiles use typed complete toggle maps with explicit research allowlists; they retain normal SSH ownership requirements.

**Operational validation follows runtime state** — Xray rotation, verify and rollback use the shared validator with the installed service asset authority; rollback candidates validate before publication and failed activation restores original bytes. Operator runtime rollback retargets `xray.service` and its links only; the egress-owned private gateway units keep the pinned release until the pin changes and a deploy re-renders them. OS maintenance loads the effective secret contract before upgrades and verifies selected services plus every configured AWG instance.
Watchdog verification starts its bounded role-owned unit so systemd loads
notification credentials, then checks only journal records after a captured
cursor; it never recreates a secret-bearing shell environment.

**One playbook per intent** — `site.yml` (deploy), `os-maintenance.yml` (serial OS upgrades/reboots), `verify.yml`, `security-verify.yml`, `smoke-test.yml`, `rollback-config.yml`, `rollback-xray.yml`, `rotate-credentials.yml`. No mega-playbook with conditional flags; new intent = new playbook. `rotate-credentials.yml`, `rollback-xray.yml` and `rollback-config.yml` are exact-node plays: they import `playbooks/tasks/exact-node.yml` as their first `pre_tasks` entry (one inventory alias equal to `--limit`) and run `serial: 1` with `any_errors_fatal`; rotation additionally requires the host inventory `env` to equal `ENV`.
`verify.yml`, `security-verify.yml` and `smoke-test.yml` load one environment's
secrets for every selected host, so their first `always` pre-task imports
`playbooks/tasks/selected-env.yml`, which refuses a host whose `env` is not
`ENV`; their Make recipes pass `ENV` explicitly and drop inherited
`ANSIBLE_SKIP_TAGS`/`ANSIBLE_RUN_TAGS`. `smoke-test.yml` gathers facts in a
pre-task after that check, so a refused host is never contacted.
`observability-host-bootstrap.yml` retains only the historical dedicated-host
contract; the current operator refuses that bootstrap. Current observability
adds bounded collector/agent slices to existing VPN hosts and a pinned Kuma
container to an independently admitted existing host. Collector private ingress
uses its own nginx master/unit with the installed binary in the collector
slice; it never restarts or rewrites the VPN's global nginx service/sites.
The sender uses independently pinned vmagent with one disk-backed remote-write
queue. Its physical queue allowance and the collector allowance are both
reserved on a shared filesystem; retained Prometheus WAL is not migrated or
deleted automatically. Resource limits still apply to the entire agent slice.
The Kuma playbook owns only observer runtime, private push ingress and backup.
`install-sshd-recovery.yml` installs the isolated recovery foundation on one
explicit node; it never activates a migration or imports baseline handlers.

**Roles are feature-toggleable** — `group_vars/all.yml` carries `vpn.enable_*`
booleans. Disabling a profile is a config change, not a code change.
Observability uses `observability_contract.enabled_environments` for inventory
and secret validation; only `staging` is currently allowed. This is separate
from runtime role enablement and must not silently enable production.

**Deployment profiles are explicit** — prefer `vpn-p0-minimal`,
`vpn-family-standard`, `vpn-device-full`, and `vpn-lab` group_vars for new
inventory cohorts. Legacy `vpn-p0`, `vpn-p1p2`, and `vpn-fullstack` remain
aliases for existing inventories and must stay guarded by `role-tiers.yml`.
`vpn-device-full-staging` retains all four device transports and restricted
Tailnet management but disables monitoring, watchdog and backup for a scoped
recovery rehearsal. It inherits the reviewed exact Tailnet sources from all.yml;
its complete `vpn` map follows the controller's replacement semantics. This
profile does not establish monitoring or backup acceptance. `vpn-device-full-tailnet`
retains the complete device-full service set with Tailnet management enabled for
blue-green replacements; it still requires exact approved controller sources.

**Per-role `roles/<role>/defaults/main.yml`** — every variable a role consumes has a
default. `group_vars` only overrides. Reading a role's defaults file tells
you most of what it exposes; a few toggles (e.g. firewall's
`firewall_egress_policy`) still default only in `group_vars/all.yml`.

**Live source parity is explicit** — `node_manifest` records the clean source
revision and deployable digest. `source-drift.yml` compares both live values
with the current checkout; `deploy` and `verify` run that gate automatically.

**Injected fact aliases are disabled** — use `ansible_facts[...]` for gathered
facts. Top-level `ansible_*` names are reserved for magic and inventory vars.

**Technical cohort group names are preserved** — rendered inventory uses
hyphenated profile slugs. Ansible keeps those names verbatim without warning;
templates must address them with bracket notation rather than attribute syntax.

**Inventory is rendered, not committed** — `scripts/render-inventory.sh`
reads `terraform output -json` and emits `inventory/<env>.yml`. Don't edit
the rendered file.

**Listener collisions fail before convergence** — `site.yml` renders a sanitized public listener manifest and runs `scripts/check-listener-collisions.py` in pre_tasks before any role mutates services or nftables. Collisions with the effective SSH port are host state and fail in the firewall role instead (see `roles/firewall/CLAUDE.md`).

**Safety pre-tasks run under role tags** — secrets presence, SSH allowlist,
role-tier loading and approval guards use `always`, just like listener checks.
Selecting a transport tag must not bypass prerequisites for baseline/firewall.

**Provider listener contract is fail-closed** — inventory carries Terraform's resolved `public_listeners` contract. `site.yml` rejects any mismatch with the runtime manifest before roles run; the firewall role and `security-verify.yml` use that same contract rather than maintaining port lists.

**SSH listener verification uses effective state** — `security-verify.yml`
derives the single active port from `sshd -T` and passes it to the live
firewall verifier. `verify.yml` also reconciles that port with bounded
`ssh.service`/`ssh.socket` state; it never infers ownership from process scans.
Port 22 has no special-case exemption when sshd uses a custom listener.

**`molecule` for testing roles, full-stack for site.yml** — `molecule-test
ROLE=<name>` runs in a Docker container per role. `molecule-full-stack`
exercises `site.yml` end-to-end.

**Hardening is split across roles** — `baseline` (sshd fragment via the SSH
transaction, sysctl floor, IP-forward toggle, time sync), `firewall`
(nftables), `intrusion_prevention` (opt-in fail2ban, sshd jail),
`policy-ratelimit` (blackhole-abuse throttling, not probe defence),
`package_updates` (unattended upgrades), `monitoring` (journald limits),
`watchdog` (transport probes and bounded restarts), `honeypot` (opt-in
canary listeners). Each role's `CLAUDE.md` owns the details.

**New roles follow one recipe** — scaffold `roles/<name>/` (tasks, defaults,
meta, handlers as needed); add its `vpn.enable_*` toggle to
`group_vars/all.yml`; classify it in `role-tiers.yml` (tier and
`toggle_role_map`, checked by `scripts/check-deploy-profile.py`); add any
secret keys to `secrets/prod.secrets.example.yaml` and `secrets/schema.json`;
add a Molecule scenario or a justified skip in `docs/reference/testing.md`; create
goldens for new templates with `make snapshot-update`; write
`roles/<name>/CLAUDE.md` plus its `AGENTS.md -> CLAUDE.md` symlink; include
the role in `playbooks/site.yml` behind the toggle; update `README.md` if
operator-facing behaviour changed. `tests/unit/test_governance_counts.py`
then requires the new role count in the root `AGENTS.md` and the template
count in `docs/reference/testing.md`.

## What's done well

- **Idempotency is a contract** — every role's molecule scenario runs the
  play twice and asserts the second run is `changed=0`. Drift = bug.
- **No `command:` / `shell:` without `creates:` or `changed_when:`** —
  ansible-lint enforces this. Pre-commit + CI catch violations.
- **Vault is not used** — SOPS owns secrets. `VPN_SECRETS_FILE` env is
  loaded through a play-level `vars_files:` entry in `playbooks/site.yml`.

**Native acceptance fixture authority** — Protected native transport acceptance uses a disconnected owned canary fixture shared by Xray, Hysteria and full-stack Molecule. Dedicated probe client tuples are selected explicitly; native role fixtures omit pre-rendered runtime, identity and egress facts so ordinary Ansible resolves actual immutable candidates and service users.

## Pitfalls

- **Supported hosts are Debian 13+ and Ubuntu 24.04+** — the firewall replaces
  its ruleset with `destroy table`, which older nftables rejects. A `site.yml`
  pre-task refuses older releases before any host change. Hetzner, Vultr and
  Scaleway image allowlists admit only these releases; UpCloud selects a
  template UUID, so there the pre-task is the only guard.

- **`changed_when:` on `command:` is mandatory** — otherwise it reports
  changed every run, breaking idempotency assertions.
- **`gather_facts: true` on every play** — needed for OS-specific branches.
  Don't disable globally; disable per-play if you must.
- **Gathered facts are not top-level variables** — `inject_facts_as_vars` is
  disabled for ansible-core 2.24 compatibility. Use `ansible_facts[...]`.
- **Hyphenated groups require bracket notation** — use `groups['vpn-p0-minimal']`,
  never `groups.vpn-p0-minimal`; `force_valid_group_names=ignore` intentionally
  preserves the inventory contract instead of silently replacing characters.
- **Role ordering matters** — baseline → package_updates → firewall → intrusion_prevention → geodata → transport/listener roles → monitoring → backup → watchdog → node_manifest.
  `site.yml` enforces this; don't rely on `meta: dependencies`.
- **OS maintenance is fleet-serial** — `os-maintenance.yml` upgrades and,
  when required, reboots one host at a time. It must reject residual packages
  and reboot markers before advancing.
- **Handler queues fire at end-of-play** — a service restart triggered in
  role A doesn't happen until role B is done. Use `meta: flush_handlers` if
  later roles depend on the restart having happened.

- **Smoke cleanup requires ownership** — atomically claim the private workdir, use unique per-run unit names, and stop only clients whose start returned success; failed claims or starts never authorize cleaning another invocation, and an unconfirmed start/stop retains the private claim to block unsafe retries.

- Site roles use a unique `<role>_role_enabled` scalar for lifecycle dispatch
  instead of skipping disabled roles. Preserve each prior enable predicate and
  tags; security policy roles always reconcile their explicit false policies.
  Tailnet management retirement requires separately recovered SSH authority.

- **The shared helper admission accepts an absent helper file** — `roles/transport-egress/tasks/helper-authority.yml` skips a missing `transport_runtime_*.py`, so any caller that would read a skipped helper run as nothing open must judge the absence separately, as `transport-ingress-begin.yml` does from the outer route's state directory and `outer.json`.
