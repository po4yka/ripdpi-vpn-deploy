# role: probe-matrix-target

## Design decisions

One research-only role owns the complete target surface: an auxiliary Xray process for VLESS-XHTTP and both Trojan shapes, mtg for MTProto, and an nginx TLS control listener. All five ports are explicit and must match Terraform's listener contract.

The mtg executable uses the shared `runtime-release` contract, so checksum
validation, immutable receipts, and current/public/previous publication match
the production runtimes even though this role remains research-only.

## What's done well

- Runtime users, configs, and logs are isolated from the family transport stack.
- Secret-bearing templates use `no_log` and `diff: false`; all generated configs are root-owned or readable only by the relevant runtime group.
- Both auxiliary runtimes use the transport sandbox floor with only
  `CAP_NET_BIND_SERVICE`; Molecule boots the rendered units with inert pinned
  executables so a directive that prevents service startup fails acceptance.

## Pitfalls

- Never enable this role on a family profile; it is a measurement target with five public listeners.
- Keep paired target transport parameters identical. Only credentials, endpoint addresses, and egress topology may vary.
