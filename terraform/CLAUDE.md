# terraform — cloud resource layer

## Design decisions

The opt-in legacy listener set and provider examples exclude alternate
REALITY ports. Publishing one requires an explicit `public_listeners` entry
and the matching Ansible `xray_fallback_port`; tests retain explicit opt-in
coverage. Existing explicit operator contracts are not rewritten.

**Per-provider root, identical outputs** — Terraform module sources can't
be variable-driven, so each provider gets its own root under
`providers/<name>/`. Every root exports the same outputs: `server_ipv4`,
`server_ipv6`, `honeypot_ipv4`, `service_ipv4`, `service_ipv4_addresses`,
`admin_user`, `ssh_port`, `server_hostname`, `zone`, `public_listeners`,
`nat_source_port_range`. The NAT range is nonempty
only when UpCloud stateless filtering requires source-port remapping; stateful
providers and the inert exception root export an empty string.
`scripts/render-inventory.sh` consumes the common inventory contract.

**SSH port is one cross-layer input** — `var.ssh_port` configures cloud-init,
the provider edge allowlist, the canonical Terraform output, inventory's
`ansible_port`, cloud-init waiting, and the on-host nftables rule. Default 22
preserves existing deployments. Because server resources intentionally ignore
later `user_data` drift, changing this creation-time input triggers node
replacement and is held by `prevent_destroy`; use the normal disposable-node
blue-green path rather than changing a live node in place.

**Encrypted remote state per provider and environment** — state and saved plans are encrypted on the client (`state.tf`, enforced, passphrase in `TF_VAR_state_passphrase`) and kept in a versioned Object Lock bucket behind the backend lock; the backend files live in the ops repository (`TF_BACKEND_ROOT`). `ENV=prod` deliberately remains the legacy `default` workspace; every other `ENV` maps to its own same-named workspace. Initialize a new environment with `make PROVIDER=<provider> ENV=<env> init` before any plan, apply, or output. `make restore-state` restores a bucket version under the lock; `make backup-state` keeps an age snapshot outside the bucket (`docs/how-to/incident.md`, "State loss"). Scripts read state only through `scripts/tofu_state.py` (`state pull`, kept in memory), never from a local path; the label-gated disposable CI deploy keeps its run in a per-run encrypted local backend override instead of the bucket.

**Operations roots live under `ops/`** — a root that holds no VPN node (`ops/egress-proxy`, the fixed-address provider API proxy) is not a provider root: it exports only the outputs its consumers need, and `render-inventory.sh`, the liveness lists and the provider tuples in tests do not list it. It still shares encrypted remote state, the plan policy gate and `make tf-test`, so `terraform-env.sh`, `policy-plan.sh`, `tofu_tfvars.py` and `tofu_backend.py` map its name to `terraform/ops/<name>`, and the CI Terraform matrices run it with the providers.

**No `local-exec` / `remote-exec`** — Terraform stays declarative.
cloud-init owns first-boot bootstrap; Ansible owns runtime state.

**Secondary public IP is opt-in per root** — `additional_public_ip = true`
allocates the honeypot address only.

**Client addresses are movable generations** — `service_ipv4_generations`
(at most two names) attaches provider-movable IPv4s to the same server. The
last one is the `service_ipv4` output (inventory `vpn_service_address`), the
client endpoint; `server_ipv4` (inventory `vpn_host_address`) stays the SSH,
Tailnet and egress identity and never moves. `service_ipv4_addresses` lists
every attached generation for guest `/32` ownership in the `baseline` role.
A blocked prefix or ASN still needs the disposable-node path
(`docs/how-to/rotate-service-ip.md`).

**Typed listener contract crosses the cloud/runtime boundary** — `public_listeners` in tfvars is the provider-edge allowlist. Its resolved Terraform output is rendered into inventory, verified against Ansible's enabled listener manifest before deploy, and used by nftables and security verification. An empty contract fails the plan; the historical implicit default set survives only behind the explicit `use_legacy_public_listeners = true` opt-in. An optional entry `family` (`ipv4`, `ipv6`, `dual`; null means dual and keeps existing rule keys) limits the provider rule, the node ruleset and the verifier to that family; the Ansible `public_listener_families` map must state the same value, set per node in its private `ANSIBLE_EXTRA_VARS_FILE`, and the `listener_family` plan policy refuses a closed-family provider rule.

**Management isolation is validated before planning** — SSH CIDRs cannot have a
zero prefix, SSH ports must be integers, and the effective explicit or legacy TCP selectors cannot contain
`ssh_port`. UpCloud also keeps SSH outside its stateless return range. UDP may
use the same port number. `make apply` evaluates all policy namespaces against
the same private saved-plan snapshot it applies; a failed or empty evaluation
refuses mutation. `tf-conftest` uses the same evaluator.

**Bootstrap identity changes use replacement** — administrator changes on
Hetzner, Vultr and Scaleway, and key changes on Vultr and Scaleway, are protected
by replacement guards. Vultr and Scaleway also compare retained cloud-init
identity during first adoption. Vultr and Scaleway compare the type and key body;
comments are metadata. [Upgrade a legacy digest](../docs/how-to/incident.md#upgrade-an-existing-bootstrap-key-digest) before the first full plan. Hetzner's provider hashes user-data in state,
so the existing key-name attribute guards first adoption; its combined name
makes server-name changes creation-time edits too. Unchanged nodes migrate
without replacement, while `prevent_destroy` blocks identity edits.

**`admin_ssh_public_keys` is a list; only the first entry is node identity** — cloud-init writes the whole list, but each root registers only the first key with the provider and hashes only the first key into its replacement guard, so adding or revoking a later key (the CI key) never replaces a node. The `single_key_list_keeps_node` and `second_key_keeps_node` lifecycle runs (and the UpCloud `admin-keys` test) prove it. Existing nodes keep their retained user_data (`ignore_changes`); `baseline` converges the live `authorized_keys` from the same list.

**Provider adapters preserve canonical listeners** — integer singleton and
legacy XHTTP ports are validated in every root. Vultr converts hyphen ranges to
colon ranges only in its resource port input, keeping output values and resource
keys stable. Its optional provider backups use a daily 03:00 UTC schedule.

**New providers follow one recipe** — create `providers/<name>/` exporting
the same outputs so `render-inventory.sh` keeps its generic path (add provider
code there only for incompatible keys or a guest-convergence check such as
Vultr's secondary IPv4). Validate constrained inputs with `contains([...])`
allowlists like the existing roots, add `mock_provider` cases under `tests/`
for `make tf-test`, and keep DNS inside the owning root behind an explicit
opt-in variable (`providers/vultr/dns.tf`). Add the name to every hardcoded
provider list: Makefile loops, the `ci.yml` provider matrices,
`scripts/terraform-env.sh`, `scripts/backup-tf-state.sh`,
`scripts/tf-policy-test.sh`, `scripts/destroy.sh`, the liveness allowlists
(`contract/protocol-liveness.schema.json`, `scripts/liveness_profiles.py`,
`scripts/install_liveness_sentinel.py`), `vpnd/src/vpnd/config.py`, and the
provider tuples in `tests/unit/` (for example
`test_provider_listeners_parity.py`). This list drifts, so finish with
`rg -il scaleway --hidden -g '!terraform/providers/**'` and cover every
enumeration it finds. Then add a `docs/reference/provider-notes.md` row and
`providers/<name>/CLAUDE.md` with its `AGENTS.md -> CLAUDE.md` symlink. Roots
never compose each other as modules.

## What's done well

- **Validation blocks on every input** — region, plan, CIDR, key formats
  all validated at plan time, not apply time.
- **Outputs are minimal** — only what the Ansible layer needs. No
  back-channel information (e.g., no API keys in outputs).
- **No version constraint on the cloud provider** — pinned in
  `versions.tf` per provider root; major bumps go through staging.

## Pitfalls

- **Image allowlists follow the host OS floor** — Hetzner, Vultr and Scaleway
  admit only Debian 13 and Ubuntu 24.04 images (Scaleway: `ubuntu_noble` until
  a Debian 13 label is verified). Debian 12 and Ubuntu 22.04 nftables cannot run
  the firewall role's `destroy table`. The allowlist governs new nodes only:
  Vultr reinstalls an existing instance in place when `os_id` changes, so its
  root ignores `os_id` drift and a postcondition refuses a changed value. Move
  an existing node to a new OS by provisioning a replacement.

- **Evaluate every policy family on the exact saved plan** — `scripts/check-tf-plan.sh` requires all policy namespaces and a nonempty complete result. Management-port checks include port intervals and unrestricted provider defaults. UpCloud's default public IPv6 interface is not a secondary-IPv4 opt-in.

- **State and saved plans are sensitive** — providers may persist generated
  secrets; Vultr's computed `default_password` is one example. Keep VPN secrets
  out of Terraform inputs/outputs and provider credentials in environment
  variables. Protect state and plans as private artifacts, age-encrypt state
  backups, and never print their contents into session logs.
- **TF state contains the SSH public key fingerprint**, but never the
  operator's private key. If state leaks, assess all exposed fields and retire
  or rotate affected credentials, including provider-generated secrets; deleting
  the state alone does not revoke access. Public key fingerprints also identify devices.
- **Cloud-init `user_data` is plaintext in state** — never put secrets
  there. Even with state encryption, this is operator-readable.
- **`tofu destroy` does not remove backups** — the `backup` role's
  remote restic repo persists. Destroy + recreate restores node data
  from that restic repository (`ansible/roles/backup/CLAUDE.md`,
  `docs/how-to/incident.md`); there is no `make restore` target.
- **Provider auth via env vars only** — never `provider` block credentials
  in code. The block must be empty (the provider auto-reads env).
- **`tf-test`** uses `mock_provider`** — these tests verify the *shape*
  of plans, not that the cloud provider behaves correctly. Real-deploy
  validation is separate (`docs/how-to/ci-real-deploy.md`).
- **`tofu test` is not Terraform's test runner** — there is no `run.state_key`, so a case that needs fresh state goes in its own test file; test state is keyed by the run's module source, so one run cannot switch configurations and keep state. Mock providers return known random strings for computed values even in plan mode, so give numeric-ID resources `mock_resource` defaults. `var.<name>` in an assertion is the raw test value; compare outputs with an explicit typed literal. Teardown reports `prevent_destroy` as an error, keeps the exit status, and leaves an ignored `errored_test.tfstate` with mock data.
- **Raw Terraform bypasses environment selection** — operator paths must use `scripts/terraform-env.sh` (or the Makefile / `vpnd` wrappers), never direct `tofu output`, `plan`, or `apply`.
- **A provider rule without the contract is a drift bug** — do not add static listener ports to a provider firewall or nftables template; update `public_listeners` and the runtime role configuration together.
