# role: real-vps-awg-nat — recurring physical evidence provisioning

## Design decisions

**Three trust boundaries, one role** — `echo`, `server`, and `sentinel` modes
are applied by separate serialized plays. The echo host never receives AWG or
SSH keys; the AWG host never receives a client private key; the sentinel owns
only its dedicated client and forced-command SSH private keys.

**Standalone research-role exception** — this role intentionally has no
`vpn.enable_*` toggle and is never included by `site.yml`. It targets an
off-fleet physical sentinel plus two separately inventoried evidence hosts;
putting it in the family deploy would collapse trust boundaries and distribute
sentinel-only keys to production inventory. Its only entrypoint is
`provision-real-vps-awg-nat.yml`, and `ansible/role-tiers.yml` classifies it as
research. That playbook loads private input only from the root-readable SOPS
material named by `VPN_SECRETS_FILE`; placement metadata remains in a separate
mode-`0600` non-secret vars file.

**A dedicated evidence interface** — `awg-evidence0` avoids mutating or
rotating production peers. The operator must reserve its public UDP listener
in the canonical provider/firewall contract before provisioning.

**Exact source is applied before a receipt exists** — the server hook validates
the streamed Git archive, runs the archive's local Ansible playbook with a
root-only variables file, and only then publishes source SHA/digest state.

## What's done well

- The SSH key is restricted to one forced command and cannot allocate a PTY,
  forward sockets, run user rc files, or invoke a shell command.
- Rotation payloads travel over stdin; reports contain only generation, peer,
  client-config, source, archive, capture, and private-log digests.
- TCP/UDP echo is application- and firewall-allowlisted to the sentinel public
  address, rate-limited, capped at 4096 bytes, and never amplifies a datagram.

## Pitfalls

- Re-running the role does not overwrite rotated client/server state. Resetting
  credentials is an explicit maintenance operation, not convergence.
- A prepare crash before its durable receipt leaves no transaction: reconcile
  and the next prepare discard those uncommitted staging files before acting.
- The offline bundle must be built from a clean committed HEAD and supplied as
  a private Ansible variable; a moving branch or remote checkout is rejected.
- Never bypass `VPN_SECRETS_FILE` with a plaintext extra-vars secrets file;
  `make clean` must remove decrypted SOPS material after provisioning.
- Exit 75 means an unavailable prerequisite/control path. A failed exact-source
  apply, restart, reload, or malformed transaction exits as product failure.
