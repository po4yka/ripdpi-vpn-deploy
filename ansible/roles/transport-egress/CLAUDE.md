# role: transport-egress — final recipient destination boundary

## Design decisions

Runtime probes use the watchdog secret's canary URL and expected HTTP status. The default status is 204 when no value is supplied.

Consumer admission streams its fixed helper sources with the private request on stdin. The small launcher pins each source digest and path before any module executes; complete sources must not enter a command argument, which has a separate Linux size limit.

Device revocation carries the same exact operation/digest through outer begin, frontend acceptance and finish. Pending revocation refuses ordinary recovery and snapshot restoration; failure quiesces the route and leaves the immutable candidate for an authorized forward retry. Even after consumer acceptance, an unfinished outer revocation cannot compensate to its old credential snapshot.

Protected site commit finishes `outer.json` through the ingress decision owner, retaining `site.json` until finish succeeds. Interrupted begin and rescue resolve a recorded commit before route status/adoption or quiescence. Do not independently roll back egress while that ingress decision remains committing.

Gateway units bind an immutable Xray release and have one publisher: the shared runtime transaction. Stage retains separate gateway candidates, validates their unit syntax privately and includes them in change prediction; only configuration, helpers and controller/normalizer units use egress publication. The generation reader exposes the validated `gateway_units` selection for runtime rollback without a second topology list. Egress keeps lifecycle and whole-route compensation ownership.

Quiescence and retirement query each exact claimed unit before stopping it. A claim may precede gateway publication or survive first-install compensation; only systemd's complete not-found/inactive/zero-PID state permits omission. Loaded or running units still require shutdown, and failed or malformed introspection refuses restoration. Retirement retains the complete ownership scope for listener removal even when every claimed unit is absent.

Frontend credential checks resolve the configuration from each exact owned systemd unit through the shared runtime parser. Custom Hysteria directories must agree during both candidate admission and controller startup; unsafe units and relative or traversing configuration paths refuse.
Hysteria credential authority is parsed as YAML using the system Python dependency installed by its role. Equivalent serialization must retain readiness; only one exact guarded SOCKS5 outbound is admitted. Duplicate or non-string mapping keys, merge keys and unsafe YAML tags refuse without exposing configuration values.

Controller preparation installs its exact semantic companion alongside native probe helpers before recovery or candidate admission. Shared helper admission includes that root-owned, single-link file. Inline acceptance loads this companion first from the same hash-bound source envelope; a module's file path does not make sibling modules importable. The frontend validator's companion remains part of its own guarded generation and may still be older while a candidate is being validated.
Whole-route snapshots include the ECH key's exact bytes, mode, group and absence alongside its config and unit. Consumer-only journaling cannot replace outer site compensation authority.

Private normalizer and native Xray gateways form one generation. The normalizer has sealed DNS-only NSS, authenticated fixed frontend listeners and no capabilities. Its resolver is the direct gateway's loopback forwarder (`LOCAL_DNS_FORWARDER`, a dokodemo-door inbound on 127.0.0.2:53 answered by the built-in DNS over DoH with `nonIPQuery: reject`), so recipient names never leave the host in plaintext; the direct gateway alone carries `CAP_NET_BIND_SERVICE` for that port, and kernel policy admits only its port-53 replies toward 127.0.0.1. DNS-Morph keeps the numeric upstream resolvers because it binds UDP/53 on every address. Only normalized admitted literals reach native gateways; final kernel policy remains authoritative for TCP and every UDP packet. Dedicated gateway identities isolate recipient traffic from trusted frontend plumbing.

Candidate files are compared and parsed before publication. `begin` captures all fixed accepted configuration, helper, policy and frontend paths before definitively stopping the accepted controller and mapping processes. Frontend consumers invoke the same entrypoint before their changed publication. `rollback` restores original bytes, modes and groups, reapplies kernel policy and requires authenticated generation readiness. Immutable runtime paths survive publication changes. The role snapshot list must equal the helper’s complete managed path set plus the accepted receipt, including absent private Hysteria hosts authority; an omitted absent path still invalidates exact receipt parity and suppresses accepted rollback recovery.

The root controller owns service generation and recovery and is enabled at `multi-user.target`. Acceptance checks its persistent enablement; an active but disabled controller must converge again. Frontends do not need independent boot links. Normalizer startup resets both native mapping processes before fresh UDP tuple pools can exist. Current authenticated readiness, process IDs and the accepted config digest identify a generation; `is-active` alone is insufficient. Configured frontends recover after gateway and normalizer recovery. WARP TUN replacement triggers a fresh paired generation.

Watchdog requests use fixed per-frontend signals delivered to the current root controller. The controller verifies retained mapping and other frontend PIDs, authenticated readiness and frontend credentials before replacing only the requested frontend and publishing its updated accepted receipt. The requester validates the private receipt/controller binding and waits within one bounded deadline for the admitted new PID; unrelated drift retains whole-generation recovery.

Site compensation retains the open egress transaction until ingress compensation commits. Frontend and activation rescues defer to that one owner while a site transaction is active. The shared quiescence task stops only the exact owned units before ingress restoration, and ordinary standalone rollback reuses the same sequence.

Site frontend retirements accumulate with the remaining candidates and commit once, before whole-route retirement when no frontend remains. External timer/operator acceptance operations cannot replace the outer owner's baseline during staging. Quiescence admits known transient process states solely to stop the owned candidate; accepted unit snapshots and readiness still require stable state.

Protected runtime consumers stage acquisition and frontend authority before the shared acceptance entrypoint. The transaction publishes the controller unit with gateway and frontend units under one root-only recovery journal, starts this role's existing generation controller and requires native authenticated frontend canary traffic plus loaded executable identity. Readiness-only and predictive passes do not publish candidates. An accepted consumer activation is retained by the following role activation instead of restarting the verified PID again. Snapshot restoration preserves already matching nodes so it cannot invalidate an exact consumer inode receipt.

Root-owned ancestry and single-link regular-file admission of the acceptance helpers is one shared task file, `helper-authority.yml`, refusing with `consumer-helper-authority-refused`. `runtime-prepare.yml` runs it before any write, and `playbooks/tasks/transport-ingress-begin.yml` runs it before executing `transport_runtime_outer.py status` as root while adopting an interrupted protected ingress journal, so a symlinked, multiply linked or group- or world-writable helper (or ancestor) fails closed with the journal retained before adoption. Keep one copy of that check.

## What's done well

- Input and identity admission happen before package or account mutation; unresolved fresh check mode predicts changes without invented UIDs or sockets.
- Secrets use private root files and `LoadCredential`; diagnostics are categorical and candidate values remain under `no_log`.
- Exact unit ownership excludes prefix scans. Retirement stops mapping processes while retaining deny policy, receipts and dedicated accounts for safe readmission.

## Pitfalls

- The native runtime sends SOCKS success before final dial. Never replay application bytes or try another address after publishing success.
- Native UDP mapping outlives TCP control. Both normalizer tuples remain bound for 240 continuous quiet seconds, reset by every late packet. Process loss requires a native generation reset.
- `+` privileged pre-start commands intentionally perform short root-owned policy and service jobs; the normalizer and the WARP gateway retain empty capabilities and the normalizer rejects AF_UNIX.
- An authenticated local probe establishes private readiness, not public path acceptance or registered vendor tunnel capability.

- Startup restores lost owned kernel policy only after definitively stopping frontends and gateways, then verifies it before runtime admission. This restores reboot service autonomously while preserving foreign-hook refusal.

- A failed newly added WARP candidate is retired after recipient stop and before restoring isolation files when the prior snapshot has no WARP gateway. The retained vendor package stays masked and disabled, so rollback cannot expose its stock host service on reboot.

- First guarded migration quiesces and boot-disables existing fixed frontend units before publication; an unaccepted snapshot cannot re-enable an unsafe legacy route. Actual MainPID real/effective/saved/filesystem UIDs must match the typed kernel policy at start and every readiness snapshot. A UID drift refuses admission while exact owned-unit shutdown remains available.
- Account admission rejects global UID aliases, foreign primary-group members and duplicate group-GID aliases. An absent service user can reuse only a nonzero, empty, unshared orphan named group; groups are otherwise created explicitly before assigning the user's private primary group. Global account metadata never leaves the read-only helper.
- Startup clears only actual failed unit state. An inactive unreferenced unit can be unloaded between introspection and `reset-failed`, so ordinary startup loads it directly. Command failures record fixed operation/unit categories without dynamic arguments or child stderr.
- Native Xray credentials retain the `config.json` suffix. The pinned parser accepts the identical JSON bytes under that name and exits 23 under an extensionless `config`; validation and runtime format authority must agree.
- Readiness failures retain fixed journal, authentication and UDP-control stages at the existing deadline. Journal diagnostics expose only whether the current MainPID message and expected journal UID were seen and live process identity was verified; attribution cannot substitute for actual UID admission or relax the journal predicate.
- Activation rescue records only finite refusal categories and whitelisted unit metadata before rollback; diagnostic collection shares one four-second budget with a five-second outer kill deadline, caps input/output and reads at most twenty records from the current controller invocation, while unavailable or unknown evidence never prevents rollback or changes the original readiness refusal.
- The root generation controller explicitly retains CAP_SETUID so its authenticated readiness child can drop to the admitted caller UID under the existing seccomp floor. Systemd otherwise removes that capability during sandbox setup. The child transition clears effective capabilities; the normalizer and WARP gateway units retain empty capability sets and the direct gateway holds only `CAP_NET_BIND_SERVICE`.
- Identity refusal fixtures build the non-UID preflight contract through the canonical input-only builder. A final published normalizer config contains runtime and frontend identities and must not be substituted for that earlier contract; the fixture must reach the actual account guard without weakening earlier admission.
- Every controller-started foreground runtime explicitly uses Type=exec so service start completes after credential, sandbox, UID and executable setup. The initial start-state read checks ownership and reset metadata without admitting the transient systemd executor; the synchronous start is followed by unchanged strict active-state and process-UID admission. Status, ready and accepted snapshots remain strict throughout.

The existing generation controller checks consumer admission before startup, preparation, recovery and every monitored cycle. Unfinished consumer publication or compensation permits runtime selection only while the canonical publisher retains its directory lock; after publisher death or reboot, unattended startup refuses until an authorized role retry restores the transaction.

The outer route marker records exact consumer acceptance only after the native readiness gate, including unchanged retries. Before that proof, unattended startup refuses; afterward ordinary Ansible phase gaps retain admission. Pending publication or compensation retains its own guard until recovery completes.
