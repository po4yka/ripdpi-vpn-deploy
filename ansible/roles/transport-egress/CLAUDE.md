# role: transport-egress — final recipient destination boundary

## Design decisions

Private normalizer and native Xray gateways form one generation. The normalizer has sealed DNS-only NSS, authenticated fixed frontend listeners and no capabilities. Only normalized admitted literals reach native gateways; final kernel policy remains authoritative for TCP and every UDP packet. Dedicated gateway identities isolate recipient traffic from trusted frontend plumbing.

Candidate files are compared and parsed before publication. `begin` captures all fixed accepted configuration, helper, policy and frontend paths before definitively stopping the accepted controller and mapping processes. Frontend consumers invoke the same entrypoint before their changed publication. `rollback` restores original bytes, modes and groups, reapplies kernel policy and requires authenticated generation readiness. Immutable runtime paths survive publication changes.

The root controller owns service generation and recovery. Normalizer startup resets both native mapping processes before fresh UDP tuple pools can exist. Current authenticated readiness, process IDs and the accepted config digest identify a generation; `is-active` alone is insufficient. Enabled frontends recover after gateway and normalizer recovery. WARP TUN replacement triggers a fresh paired generation.

## What's done well

- Input and identity admission happen before package or account mutation; unresolved fresh check mode predicts changes without invented UIDs or sockets.
- Secrets use private root files and `LoadCredential`; diagnostics are categorical and candidate values remain under `no_log`.
- Exact unit ownership excludes prefix scans. Retirement stops mapping processes while retaining deny policy, receipts and dedicated accounts for safe readmission.

## Pitfalls

- The native runtime sends SOCKS success before final dial. Never replay application bytes or try another address after publishing success.
- Native UDP mapping outlives TCP control. Both normalizer tuples remain bound for 240 continuous quiet seconds, reset by every late packet. Process loss requires a native generation reset.
- `+` privileged pre-start commands intentionally perform short root-owned policy and service jobs; the normalizer itself retains empty capabilities and rejects AF_UNIX.
- An authenticated local probe establishes private readiness, not public path acceptance or registered vendor tunnel capability.

- Startup restores lost owned kernel policy only after definitively stopping frontends and gateways, then verifies it before runtime admission. This restores reboot service autonomously while preserving foreign-hook refusal.

- A failed newly added WARP candidate is retired after recipient stop and before restoring isolation files when the prior snapshot has no WARP gateway. The retained vendor package stays masked and disabled, so rollback cannot expose its stock host service on reboot.

- First guarded migration quiesces and boot-disables existing fixed frontend units before publication; an unaccepted snapshot cannot re-enable an unsafe legacy route. Actual MainPID real/effective/saved/filesystem UIDs must match the typed kernel policy at start and every readiness snapshot. A UID drift refuses admission while exact owned-unit shutdown remains available.
- Account admission rejects global UID aliases, foreign primary-group members and duplicate group-GID aliases. An absent service user can reuse only a nonzero, empty, unshared orphan named group; groups are otherwise created explicitly before assigning the user's private primary group. Global account metadata never leaves the read-only helper.
- Startup clears only actual failed unit state. An inactive unreferenced unit can be unloaded between introspection and `reset-failed`, so ordinary startup loads it directly. Command failures record fixed operation/unit categories without dynamic arguments or child stderr.
- Native Xray credentials retain the `config.json` suffix. The pinned parser accepts the identical JSON bytes under that name and exits 23 under an extensionless `config`; validation and runtime format authority must agree.
- Readiness failures retain fixed journal, authentication and UDP-control stages at the existing deadline. Journal diagnostics expose only whether the current MainPID message and expected journal UID were seen and live process identity was verified; attribution cannot substitute for actual UID admission or relax the journal predicate.
- The root generation controller explicitly retains CAP_SETUID so its authenticated readiness child can drop to the admitted caller UID under the existing seccomp floor. Systemd otherwise removes that capability during sandbox setup. The child transition clears effective capabilities; recipient normalizer and gateway units retain empty capability sets.
- Identity refusal fixtures build the non-UID preflight contract through the canonical input-only builder. A final published normalizer config contains runtime and frontend identities and must not be substituted for that earlier contract; the fixture must reach the actual account guard without weakening earlier admission.
- Every controller-started foreground runtime explicitly uses Type=exec so service start completes after credential, sandbox, UID and executable setup. The initial start-state read checks ownership and reset metadata without admitting the transient systemd executor; the synchronous start is followed by unchanged strict active-state and process-UID admission. Status, ready and accepted snapshots remain strict throughout.
