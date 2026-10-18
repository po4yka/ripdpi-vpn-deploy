# Secrets — SOPS + age model

## Where things live

```
~/.config/vpn-provision/
  age.key                                # private age key (operator-only, mode 0600)
  prod.secrets.yaml                      # plaintext, EXISTS ONLY MOMENTARILY
  prod.secrets.sops.yaml                 # encrypted, the only durable copy
  staging.secrets.sops.yaml              # same shape, staging environment

vpn-deploy/secrets/
  prod.secrets.example.yaml              # placeholder schema only

vpn-deploy/secrets/local/                # optional, git-ignored operator layout
  config/age.key                         # private age key, mode 0600
  config/prod.secrets.sops.yaml           # encrypted durable copy
  runtime/vpn-prod.secrets.yaml           # plaintext only while needed, mode 0600
  clients/                                # generated client artifacts, mode 0600
```

The external directory is the default. The `secrets/local/` layout is an
explicitly supported convenience for this checkout and is excluded by
`.gitignore`; it is still sensitive local state, not repository content.
Keep VPN secrets out of Git, Terraform variables/outputs, cloud-init `user_data`,
and debug logs; provider credentials come only from environment variables.
Terraform state and saved plans remain sensitive: providers can persist generated
secrets, such as Vultr's computed `default_password`, even when VPN secrets and
provider credentials stay outside Terraform. Use mode `0600` for these files and
`0700` for their private directories, encrypt state backups with `make backup-state`,
and never print raw state or plan contents into session logs.

## age recipients

```bash
# One-time bootstrap
age-keygen -o ~/.config/vpn-provision/age.key
chmod 0600 ~/.config/vpn-provision/age.key
grep '^# public key:' ~/.config/vpn-provision/age.key | awk '{print $4}'
# → age1xyz…  (this is your "recipient")
```

### Hardware-backed age (YubiKey PIV applet)

For high-value operator workstations, replace the software age key
with a YubiKey-backed identity via the `age-plugin-yubikey` plugin.
The encrypted SOPS blob stays useless to anyone without physical
access to the YubiKey, even if they have the file.

Select one YubiKey serial and an available slot (1 through 20). Use `YUBIKEY_GENERATE=1` (`--generate`)
only for first enrollment in a private operator terminal. PIN prompts and plugin
setup diagnostics stay on that terminal; they do not enter command logs. The
plugin refuses a filled slot; the wrapper refuses
`--generate` when a saved identity already exists.

```bash
make setup-yubikey YUBIKEY_SERIAL=<serial> YUBIKEY_SLOT=<slot> YUBIKEY_GENERATE=1
make setup-yubikey YUBIKEY_SERIAL=<serial> YUBIKEY_SLOT=<slot> REENCRYPT=1
```

The second command also resumes an interrupted enrollment without generating a
new key. It checks the saved identity against the selected hardware and retains
its bytes. Without `--generate`, a missing local identity can be recovered from
that same occupied hardware slot.

Migration discipline:

1. Add the selected hardware recipient to every encrypted document. The command
   retains each document's existing recipients, uses an explicit staged SOPS
   config, and verifies unchanged plaintext before publication. It adds exact
   per-file rules to the operator `.sops.yaml` and retains general rules.
   All candidates are checked before publication starts. Publication is per
   file; completed additive updates remain safe to resume after interruption.
   Grouped or non-age recipient policies require a separate reviewed procedure
   and refuse without replacement. One hardware key must not satisfy every
   group of a multi-group quorum.
2. Verify hardware-only decryption on every operator workstation that needs it.
   Clear other age key sources, set `SOPS_AGE_KEY_FILE` to the saved
   `yubikey-identity.txt`, and direct decrypted output to `/dev/null`. Do not
   print plaintext or use terminal output as the verification artifact.
3. Retire the software recipient only as a separate reviewed operation. Update
   the explicit `.sops.yaml`, run `sops updatekeys` on each selected file, and
   retain other authorized recovery recipients. If the retired key may have
   been compromised, also follow [data-key rotation](AGE-RECOVERY.md#rotating-the-age-key)
   before changing stored credentials.

The enrollment command never removes recovery recipients or verifies
hardware-only decryption on behalf of the operator. Private files use mode
`0600`; their directory must use mode `0700`. A failed update returns failure
and keeps prior decryption paths available.

Encrypt against one or more recipients (multiple operators):

```bash
sops --encrypt \
  --age age1aaa…,age1bbb… \
  ~/.config/vpn-provision/prod.secrets.yaml \
  > ~/.config/vpn-provision/prod.secrets.sops.yaml
```

The recipient list is also stored at `.sops.yaml` if you have one — the
runtime needs only **the private key matching one of the recipients** to
decrypt.

## Day-to-day operations

| Action | Command |
|---|---|
| Edit existing secrets | `sops ~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Add a new client | `SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml ./scripts/new-client.sh laptop` |
| Issue one Naive device | `make naive-issue CLIENT=laptop SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Revoke one Naive device | `make naive-revoke CLIENT=laptop SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Read one Naive credential for delivery | `make naive-readout CLIENT=laptop SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml OUTPUT=~/.config/vpn-provision/laptop.naive.json` |
| Re-encrypt under a new recipient | `sops updatekeys ~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Decrypt for deploy | `make decrypt` (writes configured `SECRETS_FILE`, mode 0600) |
| Wipe plaintext | `make clean` (shred or rm) |

`sops <file>` opens your `$EDITOR` against a temp plaintext file in `/tmp`
with mode 0600, re-encrypts on save, and deletes the plaintext. It never
writes plaintext to a path you can `cat` later.

Naive readout requires a new explicit `OUTPUT` artifact in an owner-controlled
`0700` directory. The artifact is `0600` and contains only the selected device.
Existing files, links and shared directories are refused; stdout reports only
operation metadata and the output path. Keep the artifact outside tracked source
or under ignored `secrets/local/`, transfer it through the authorized private
channel, then retire the local copy. No stdout credential compatibility path remains.

Naive uses `naive_secrets.clients[]` with unique `name`, `username`, and independent
strong `password` fields. The encrypted writers require the reviewed SOPS 3.13.3
controller tool; both CI installers verify that release's checksum. Values cross
its stdin update interface rather than secret-bearing command arguments. The
former scalar username/password contract is rejected;
issue new per-device identities. `new-client.sh` adds Naive when its section exists,
inside the same encrypted transaction as the other transports. The three dedicated
verbs share that transaction lock, edit encrypted siblings, and preserve unrelated
material. Readout deliberately prints only the selected device credential: use a
private terminal and secure delivery channel. Revocation changes encrypted source;
use the reviewed credential-rotation deployment, which enters the enabled Naive
role, to enforce it on the node. Revoking the last device
sets `clients: []`, which disables forwarding and retains the decoy site. These verbs
do not revoke that device's credentials in other transports or change its registry
lifecycle.

Bootstrap grants now use `b1_<issued-epoch>_<random>` and expire intrinsically after
`subscription.bootstrap_max_lifetime_seconds` (seven days by default; 60 seconds
through 30 days). Older bootstrap token URLs are rejected and need reissuance;
ordinary `/sub/` URLs retain their existing contract. Optional `--expires` shortens
the intrinsic deadline. Persistent maintenance bounds consumed markers and audit
logs, publishing a monotonic retirement fence before deleting old replay proof.
Compaction uses the absolute supported 30-day lifetime, even under a shorter
current policy. This protects older grants when policy changes; expired markers
may therefore occupy admission capacity until that safe horizon. Increase the
explicit marker capacity for higher issuance volume instead of discarding proof.

Without a `.fleet.mk` override, `SECRETS_FILE` resolves below
`${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}/vpn-provision-$(id -u)}/`. A repo-local
operator can set the following in the ignored `.fleet.mk`:

```make
SOPS_FILE = $(CURDIR)/secrets/local/config/prod.secrets.sops.yaml
SECRETS_FILE = $(CURDIR)/secrets/local/runtime/vpn-prod.secrets.yaml
```

Export `SOPS_AGE_KEY_FILE` separately or from a protected shell environment;
keep directories mode 0700 and files mode 0600. Run `make clean` immediately
after the operation that needs plaintext.

## What's in the secrets file

XHTTP endpoint inputs are canonical: `xray.xhttp_path` has a leading slash and
one or more nonempty segments containing only ASCII letters, digits, underscores
and dashes, with at most 256 bytes. Root, trailing slash, encoded separators,
dot segments, queries, fragments and whitespace are rejected before mutation.
`public_site_canonical_url` and `hysteria.masquerade_url` must agree with the
served primary HTTPS hostname and port. Port 443 is omitted; a listener on 8443
uses `https://vpn.example.com:8443`. Origins have lowercase hostnames and no
credentials, paths, query or fragment. Alternate frontends retain the primary
canonical identity.

This intentionally rejects older accepted inputs. Before rollout, validate the
private configuration categorically, correct its endpoint/origin fields without
printing them, regenerate recipient and liveness artifacts, and converge Xray
and Nginx together. Secrets bootstrap accepts `--xhttp-port` (Make:
`XHTTP_PORT`), defaulting to 8443; direct-only port 443 must be selected explicitly.
This source change does not migrate private configuration or authorize rollout.

See `secrets/prod.secrets.example.yaml` for the full schema. High-level:

```
xray.{version, linux_*_sha256, reality_*, target, server_names, xhttp_path, clients[*]}
nginx_xhttp.{server_name, cert_pem, key_pem}
hysteria.{version, linux_*_sha256, cert_pem, key_pem, bandwidth_*, salamander_*, clients[*]}
geodata.{geosite_url, geoip_url, geosite_sha256, geoip_sha256, install_dir, refresh_interval}
amneziawg_go_version + amneziawg_go_commit / amneziawg_tools_version + amneziawg_tools_commit
amneziawg_secrets.instances[*].{name, listen_port, address_v4, address_v6, server_private_key, jc/jmin/jmax/s1-s4/h1-h4, peers[*]}
backup.restic_password
client_registry.<device>.{status, issued_at, formats, hosts, cohorts, token_hash_prefix, token_expires, awg_binding, awg_delivery_host, awg_public_key_fingerprint, awg_private_key, delivery_options, delivery_sources, last_payload_identity}
client_delivery_identity.{version, generation, key}  # created by authorized delivery
subscription.{port, server_name}     # optional
```

`client_registry` is operator-side per-device metadata (never consumed by
Ansible roles): issuance options for each device so `issue-sub-token.sh
--refresh-token` can reproduce the original payload instead of falling back
to defaults, the lifecycle status (`issued → delivered → active → stale |
revoked | burned`), the AWG client private key as a recovery copy (the
device-local key stays primary), and the payload identity
(versioned private HMAC-SHA256 over the canonical selected-device payload,
format, exact options and AWG binding including the enrolled peer public key) recorded at last delivery for
`make client-drift CLIENT=<device>`. Inspection re-renders in memory and emits
only `current`, `stale` or `unknown`; it never prints the digest or creates
identity authority. The encrypted authority has a 256-bit random key and a
key-bound generation. Re-encryption and unrelated device/metadata edits keep
the selected device current. Missing, malformed or rotated authority, absent
recorded source selectors, and old source/output identities are unknown until
an explicitly authorized redelivery. Issuance alone initializes missing
authority; malformed existing authority refuses instead of being replaced.
Refresh retains private per-host source selectors, format, hosts, cohorts,
AWG host, UTLS selection and expiry. Explicit `--format` / `--expires` overrides
are recorded with the new identity. A staging/verification failure preserves
prior encrypted state and precedes remote writes. Local SOPS and remote
publication cannot commit atomically together: reconcile both after an
interrupted or failed publication before retrying.
The CLI returns 3 with that reconciliation warning once a mutating SSH attempt
has started, even if its reply or subsequent local publication fails. Preflight
and candidate-verification refusals precede that boundary.

AWG uses a nonempty `instances` list as its sole server and peer authority,
including single-instance hosts. Top-level server keys, parameters and peers
are rejected. Each AWG device registry entry has an explicit
`awg_binding: {provider: upcloud, environment: prod, instance: awg0}` identifying
the instance containing its uniquely named peer. Its recovery private key and
public-key fingerprint must match that peer. After AWG-only revocation,
`awg_binding` is `null`, both recovery fields are empty strings, and no instance
may retain a peer with that device name. Other transport credentials and the
global device lifecycle status are preserved. Existing private documents need
an explicit migration and validation before rollout; source updates never
rewrite them automatically.

AWG device names must be unique across all instances. Every device peer requires
a matching registry binding; only peers explicitly marked `routed` are exempt. Export and liveness require
an existing matching registry binding even when a document omits the optional
registry section. After AWG-only revocation, `make awg-issue` can replace that
device's AWG key and binding while preserving its non-AWG registry metadata.
This requires a null binding, empty AWG recovery fields, and an active global
device lifecycle; a globally revoked entry cannot be reissued this way.

`client_registry.*.awg_delivery_host` records the last subscription issuance's
explicit AWG host option; an empty string means automatic selection. It is
separate from `awg_binding`, which owns device credentials. Refresh restores the
recorded delivery choice instead of ambient `AWG_HOST`. Existing entries require
this field; reissue a token with the intended selection rather than guessing a
missing historical value. Preflight and enrollment/revocation use the same
complete registry relationship validator before encrypted publication.

## Rotation

Three rotation scopes:

1. **Per-client** (one device leaks): regenerate that one client's
   `uuid`+`shortId` (Xray), password (Hysteria), or peer keypair (AWG).
   Use `scripts/new-client.sh` to add the replacement, edit secrets to
   remove the old entry, then `make rotate-credentials ANSIBLE_LIMIT=<alias>`
   once per node of the environment; revocation is incomplete until every node
   is rotated and verified (`RUNBOOK-rotate.md` §1).
2. **Server-wide REALITY keypair**: regenerate via `xray x25519`, update
   `xray.reality_private_key` + `xray.reality_public_key`, redistribute
   the new public key + shortIds to clients, run `make deploy`. All
   clients must reissue.
3. **Restic password**: a planned password change rewraps the repository key
   through `restic key passwd`; it does not invalidate snapshots. Keep the
   previous password until the new password passes restore verification.
   A compromised repository master key requires a new local and remote
   generation. Preserve the prior repository until the new generation passes
   backup and isolated restore; retire it only as a separate authorized action.

See `RUNBOOK-rotate.md` for full procedures.

## Recovery — what to do when…

### Lost the age private key

Without it you cannot decrypt the SOPS file. Three options:

1. You encrypted to multiple recipients → use the other operator's age key.
2. You backed up the age key out of band → restore it.
3. Neither → all secrets are unrecoverable. Treat this as a **complete
   credential leak** (assume an attacker may possess the encrypted blob
   forever, even if computationally hard today). Rotate every credential:
   provision a new VPS, generate fresh REALITY keypair, fresh per-client
   UUIDs/passwords/peer keys, fresh restic password. Migrate clients.

### Plaintext secrets file leaked to disk

`shred -u` the file. If shred is not available (some filesystems don't
support it), `rm` and overwrite the free space. Treat the secrets as
compromised and rotate per the per-server rotation above.

### Operator workstation lost

If the age private key was in `~/.config/vpn-provision/age.key`, treat as
"lost the age key" plus the SSH private key. Add: rotate SSH access on
the VPS (`make deploy` with a new `admin_ssh_public_key` in tfvars), and
if Terraform state was on that workstation, see `RUNBOOK-incident.md` §
"State loss".

## Hard rules

- Never `cat` a decrypted secrets file into the terminal.
- Never paste secrets into GitHub issues, PRs, Slack, or Discord.
- Never run `ansible-playbook -vvv` against a host with secrets in scope —
  `-vvv` can dump task vars. Use `--diff` only on roles that mark
  templates `no_log: true, diff: false` (the templates here do).
- The `.gitleaks.toml` ruleset must pass on every commit. `make validate`
  enforces this locally; CI enforces it on push.
