# role: real-vps-awg-nat — external evidence provisioning

## Design decisions

**Three trust boundaries, one role** — `echo`, `server`, and `sentinel` modes
are applied by separate serialized plays. The echo host never receives AWG or
SSH keys; the AWG host never receives a client private key; the sentinel owns
only its dedicated client and forced-command SSH private keys.

**Standalone research-role exception** — this role intentionally has no
`vpn.enable_*` toggle and is never included by `site.yml`. It targets an
off-fleet persistent Linux sentinel plus two separately inventoried evidence hosts;
putting it in the family deploy would collapse trust boundaries and distribute
sentinel-only keys to production inventory. A disposable systemd-capable Linux
VM on the operator Mac's consumer uplink must not invoke this role: one-shot
acceptance belongs to the separate protocol-liveness path because this role
deliberately leaves recurring echo, peer and forced-command state installed.
That disposable path is not operationally enabled until it has fail-closed VM
isolation preflight, report-bound executor evidence, and exact de-onboarding.
Its only entrypoint is
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
- Evidence services share the transport sandbox floor. Echo runs without
  capabilities, while AWG and nft loaders retain only `CAP_NET_ADMIN`; those
  two units deliberately do not deny the systemd `@privileged` syscall group.

## Pitfalls

- Re-running the role does not overwrite rotated client/server state. Resetting
  credentials is an explicit maintenance operation, not convergence.
- A prepare crash before its durable receipt leaves no transaction: reconcile
  and the next prepare discard those uncommitted staging files before acting.
- The offline bundle must be built from a clean committed HEAD and supplied as
  a private Ansible variable; a moving branch or remote checkout is rejected.
- Sentinel provisioning binds the client source to the pinned `amneziawg-go`
  commit and its artifact digest to the immutable toolchain manifest. Every
  run re-hashes the resolved binary and validates that manifest before evidence
  collection; a hand-written descriptor is not a supported activation path.
- An existing recurring timer is disabled before generation inputs change and
  remains disabled after any failed converge. Provisioning waits for the shared
  lane lock; only the exact-source installer re-enables the completed generation.
- The standalone provisioning play is an explicit disruptive maintenance
  operation, not an ordinary idempotent family converge: even an exact-current
  generation is quiesced and revalidated so no stale private input is trusted.
- Never bypass `VPN_SECRETS_FILE` with a plaintext extra-vars secrets file;
  `make clean` must remove decrypted SOPS material after provisioning.
- Exit 75 means an unavailable prerequisite/control path. A failed exact-source
  apply, restart, reload, or malformed transaction exits as product failure.
- A local disposable sentinel belongs to the separate protocol-liveness lane,
  not this recurring role. It must use a non-default isolated VM profile,
  dedicated identities, no host mounts or published ports, and exact cleanup.
  Do not transfer credentials until those checks and de-onboarding are enforced.
  Record its consumer-uplink vantage without claiming a persistent physical host.
