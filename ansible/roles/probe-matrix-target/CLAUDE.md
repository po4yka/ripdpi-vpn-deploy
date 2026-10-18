# role: probe-matrix-target

## Design decisions

Trojan passwords use JSON serialization for both TCP and XHTTP target inbounds.
The parsed target value must equal the original authority and the Python probe
driver value for every schema-valid string. Parser success alone cannot prove
that credential bytes are unchanged.

FakeTLS admission runs on the controller before any target mutation. It accepts
hex or unpadded URL-safe base64 with an ee prefix, nonzero sixteen-byte key and
valid ASCII hostname. It reports field categories only. The official mtg tar.gz
uses one versioned architecture directory; the shared installer selects its mtg
member and strips exactly one component. Correct archive extraction uses the
local release and receipt identity `<mtg_version>+archive.1`; the upstream version
and member names keep `<mtg_version>`. This separates the corrected executable
from a legacy same-version receipt that may own raw tarball bytes. Legacy bytes
and receipts remain immutable; a successful migration retains their release as
the previous pointer. Stage-only acquisition preserves the
accepted runtime links until the candidate version and native configuration
parser pass. Native validation also runs when configuration bytes are unchanged,
so a binary-only migration cannot skip version and parser admission. The
validator uses explicit loopback access addresses, discards
credential-bearing output and does not start the proxy or contact Telegram.
An invalid candidate retains the old mtg configuration and runtime authority.

Disabled role intent stops only declared owned services and removes exact runtime
configuration; shared packages, immutable release receipts and unrelated state
remain. The unique `probe_matrix_target_role_enabled` selector defaults true for direct calls.

One research-only role owns the complete target surface: an auxiliary Xray process for VLESS-XHTTP and both Trojan shapes, mtg for MTProto, and an nginx TLS control listener. All five ports are explicit and must match Terraform's listener contract.

The mtg executable uses the shared `runtime-release` contract, so checksum
validation, immutable receipts, and current/public/previous publication match
the production runtimes even though this role remains research-only.

Enable publishes owned TLS material, vhost and link through the shared complete
nginx transaction. The local Molecule PKI is synthetic but the nginx parser is
real. Disable removes the owned TLS vhost through the shared complete-candidate nginx
transaction before retiring its certificate. It preserves global nginx enablement,
does not start an inactive shared nginx, and preserves every other listener.
Disabled absence always enters the nginx transaction, even when both vhost files
are already gone: a retained publication journal or stale active listener must
recover before certificate retirement. Its validation root is only `/etc/nginx`,
matching the vhost-only write set; a missing `/etc/probe-matrix` cannot block
reconciliation of an unchanged inactive or interrupted removal.

## What's done well

- Runtime users, configs, and logs are isolated from the family transport stack.
- Secret-bearing templates use `no_log` and `diff: false`; all generated configs are root-owned or readable only by the relevant runtime group.
- Both auxiliary runtimes use the transport sandbox floor with only
  `CAP_NET_BIND_SERVICE`; Molecule boots the rendered units with inert pinned
  executables so a directive that prevents service startup fails acceptance.

## Pitfalls

- Never enable this role on a family profile; it is a measurement target with five public listeners.
- Keep paired target transport parameters identical. Only credentials, endpoint addresses, and egress topology may vary.
- A changed service unit queues only that runtime's restart after daemon reload;
  starting an already active service cannot apply changed execution or sandbox
  settings. An unchanged unit does not interrupt either runtime.
