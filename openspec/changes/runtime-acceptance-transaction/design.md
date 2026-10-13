## Context

Shared runtime-release verifies owned bytes and compensates its link publication, but returns committed before Xray or Hysteria2 configuration and service readiness are accepted. A later parser, asset, certificate, bind or startup failure leaves the active links selecting a rejected runtime. Existing nginx and geodata publication improvements do not establish a complete transport runtime transaction.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. The implementation request authorizes source delivery and isolated acceptance, without real inventory or credentials.

## Goals / Non-Goals

- Goal: commit transport runtimes only after complete configuration and readiness acceptance with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Reuse shared runtime locking, root-owned staging, digest receipts, immutable release identities and no-follow publication; do not create a second deployment controller.
- The transport acceptance commit follows complete native validation and observed protocol readiness; link equality and is-active alone are not sufficient.
- Keep the previous distinct accepted generation across unchanged retries, including binary, assets, config, TLS and relevant enabled/active unit state.
- Candidate validation must name staged binary and asset paths rather than implicitly validating through already-published public links.
- Persistent recovery records containing private authority remain root-only and bounded; diagnostics publish categorical state and nonsecret identities only.
- Unknown or foreign recovery authority refuses without deletion. An unconfirmed restoration remains an incomplete transaction and cannot be reported as accepted.
- First-install failure leaves no enabled unaccepted transport; ordinary upgrades restore prior positive forwarding.

## Contracts and ownership

- ansible/roles/warp-outbound/ (bounded process-disappearance retirement and CI refusal diagnostics)
- tests/unit/test_warp_pin_contract.py
- ansible/roles/observability_agent/ (sender activation and retained queue)
- tests/unit/test_observability_runtime_queue.py
- ansible/roles/runtime-release/tasks/main.yml
- ansible/roles/runtime-release/files/runtime_release_activate.py
- ansible/roles/runtime-release/CLAUDE.md
- ansible/roles/xray-runtime/tasks/main.yml
- ansible/roles/xray-runtime/CLAUDE.md
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/handlers/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/handlers/main.yml
- ansible/roles/hysteria/CLAUDE.md
- tests/unit/test_runtime_release_contract.py
- tests/unit/test_runtime_release_consumers.py
- tests/unit/test_hysteria_runtime_release.py
- NEW: tests/unit/test_transport_runtime_acceptance.py
- NEW: tests/integration/transport_runtime_acceptance/
- ansible/roles/runtime-release/files/transport_runtime_*.py
- ansible/roles/transport-egress/tasks/runtime-*.yml
- ansible/roles/transport-egress/tasks/begin.yml
- ansible/roles/transport-egress/tasks/rollback.yml
- ansible/roles/transport-egress/files/snapshot.py
- ansible/roles/geodata/
- ansible/playbooks/rollback-config.yml
- ansible/playbooks/rollback-xray.yml
- ansible/playbooks/tasks/transport-ingress-commit.yml
- ansible/molecule/
- tests/unit/test_transport_runtime_acceptance_native.py
- tests/unit/test_transport_runtime_adapter.py
- Makefile
- secrets/prod.secrets.example.yaml
- Dependencies: None; may be implemented independently after baseline confirmation.. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation runs in the authorized dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A full transaction crosses runtime-release and consumer role boundaries; recovery ordering and handler queues must be designed together.
- Service activation and compensation can interrupt sessions; bounded interruption must be explicit and measured.
- Power loss may interrupt several filesystem and process changes; a durable journal and deterministic retry are required rather than claiming multi-file atomicity.
- Recovering private config and TLS must not overwrite a foreign inode or discard independent operator work.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Source implementation is authorized; no live mutation is included. Preserve existing runtime receipts and distinct archive/source identities, and define any receipt format change without compatibility shims. Existing accepted service state must be captured through trusted bounded inspection before transition; unknown legacy authority cannot silently become accepted. Integrated nginx/geodata transactions and review evidence stay intact. Upgrade and PQE evaluation depend on this capability, but neither upgrades nor PQE activation belong to this repair. Live adoption requires an exact authorized target, reviewed candidate and authenticated rollback proof.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-RTA-CANDIDATE`: Extend runtime-release consumer tests and NEW transport acceptance native fixtures; inject asset failure and semantic parser rejection after successful binary staging.
- `REQ-PROTO-RTA-ADOPTION`: NEW exact native service fixtures covering wrong TLS, occupied socket, startup error and active-but-broken protocol readiness.
- `REQ-PROTO-RTA-RECOVERY`: NEW kill-point tests plus existing runtime-release compensation coverage; assert complete bytes, inode ownership, unit state, protocol result and A-to-B-to-B previous identity.
- `REQ-PROTO-RTA-AUTHORITY`: Extend real local Ansible check-mode tests and NEW symlink/hardlink/foreign journal/privacy failure regressions.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_runtime_release_contract.py tests/unit/test_runtime_release_consumers.py tests/unit/test_hysteria_runtime_release.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-transport-runtime-acceptance — Exercise exact owned native upgrade and rollback acceptance plus process-death recovery without real inventory.`

The native target must execute complete cases and fail on selected skips before acceptance. No credentialed recipe is authorized merely by being listed here.

CI runs the complete consumer target in a pinned fresh systemd container on
its own disposable Linux runner, with isolated runtime and firewall authority.
The existing native suite and consumer suite are disjoint, together cover every
native test, and both are mandatory in the selected required-check graph. This
preserves foreign-authority refusal instead of adopting another fixture's state.
Owned numeric canaries bind without reverse DNS inside the disconnected namespace.

## Supported native candidate validation

Xray candidate validation uses its supported native test command against the staged config and staged asset directory. Hysteria has no validation-only server flag: validate actual staged runtime and TLS by bounded server startup plus authenticated readiness in an invocation-owned isolated Linux namespace, using the intended sandbox and listener contract. YAML shape validation remains supplemental. Any uncertain cleanup or leaked process/socket refuses live activation and retains owned recovery evidence; never invent a check flag or bind candidate validation onto a real production listener.

## Canonical dependencies

- No new implementation prerequisite.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.

## Concrete transaction boundary

Byte acquisition keeps immutable runtime receipts and returns a staged selection plan. The shared consumer publisher holds a private directory lock and validates complete Xray/Hysteria candidates before selection. A durable preparation claim precedes fixed backup allocation; pending intent precedes live replacement. Exact original inodes, prior absence, unit state and authenticated probe parameters belong to the same compensating boundary. The accepted receipt follows loaded executable identity and real pinned-client forwarding to an owned canary.

The existing guarded-generation controller owns process lifecycle. Hysteria admission clones its intended sandbox into an invocation-owned namespace and performs actual TLS/authenticated forwarding. The publisher does not invent a validation-only Hysteria flag or a second persistent controller.

An outer intent coordinates the existing ingress/egress snapshot owner. Consumer file restoration retains its journal until the outer route and policy are restored; only then do positive native rollback traffic and prior unit restoration finalize the consumer receipt. Interrupted outer staging is recovered before any subsequent candidate preparation. Existing frontend retirement and operator config/runtime rollback callers use the same publisher; retained immutable releases are not deleted.

Protected geodata downloads produce an immutable pair without changing selected files. Consumer acceptance validates staged asset authority, selects both files and records adoption only after real frontend readiness. Timer refresh uses the same acceptance boundary. Profiles without protected frontends retain the existing paired-byte publisher.

Site retirement adds absence declarations to the one complete consumer plan, including complete frontend shutdown. Timer refresh and operator rollback refuse an open outer intent before any lease recovery or publication. Native admission leases include the boot identity; after a proven reboot, missing volatile resources are reconciled only when the new manager confirms no replacement unit or process, while durable file and directory claims remain exact.

Required canary URL and dedicated per-protocol client names are admitted before host mutation. Probe credentials remain in private files/stdin; diagnostics expose fixed categories and bounded source frame identities only. A change in accepted probe parameters participates in exact compensation.

Exact before/after nodes are staged in private directories beside their selected paths, with private-directory and live-parent inode claims persisted centrally. Namespace-local mount IDs are checked at invocation time and are never persisted; separately mounted leaves refuse before publication. This supports the existing systemd writable bind mounts without weakening filesystem protection. The existing generation controller refuses unfinished intent when no live publisher holds its retained lock, including unattended boot and direct normalizer preparation.

Outer intent includes a typed consumer receipt proof, written under the publisher lock only after native readiness, including unchanged retries. The generation controller rejects outer staging before that proof; an exact completed consumer receipt keeps admission through subsequent ordinary Ansible phase gaps.

Retirement verifies a missing selected parent through its nearest existing no-follow ancestry and omits that absent subtree from inode publication. It creates no missing frontend directories or synthetic storage; existing selected parents retain exact transactional absence claims.

## Sender queue preservation

The owner authorized the sender repair in this PR on 2026-10-13. The pinned vmagent starts remote-write workers before HTTP readiness; fatal startup may consume persisted read positions without graceful requeue. A root-only ephemeral activation helper reuses the shared publisher. It stops and confirms the complete old process is gone, records and copies the single bound receiver queue before replacing any selector, and retains that copy through durable acceptance. Rejected or interrupted publication restores the queue in place, retaining its root inode, before restarting the exact old service. Repeated recovery stops never capture a new baseline. The native historical nonce must reach the actual authenticated receiver after rollback.

Admission preserves the existing 2 GiB queue allowance and filesystem reserve. The working tree and private copy each stay below 1 GiB, bounded by native single-URL layout, sizes and allocated bytes; candidate contents are cleared before restoration to avoid a third copy. Unknown entries, unsafe ownership, mounts, oversized data or insufficient capacity refuse without deleting original data. An unresolved journal blocks unattended start unless its exclusive live publisher owns the activation lock. No new persistent boot controller or live fleet action is introduced.

The owner also authorized finishing the observability alerting repair on 2026-10-13. Its independent change owns the canonical examples, producers and alert behavior. It is integrated before the runtime transaction so the updated client mirror remains aligned; no live metric emission is claimed.

Pinned native atomic writes may retain bounded private metadata staging files or empty initial-chunk staging files after interruption. These exact forms remain within the existing copy/count budget and participate in exact compensation. Live readiness retries only a detected inode replacement within its existing deadline; snapshot capture stays quiescent and foreign-authority refusals remain immediate.

Ephemeral native-validation units are `0600` and read by PID1 before sandbox identity is applied. Their exact leases require that private mode; publicly readable units refuse before process or resource mutation. Native admission and interrupted validation recovery exercise this permission boundary.
