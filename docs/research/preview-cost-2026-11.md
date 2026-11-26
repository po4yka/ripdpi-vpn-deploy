# Full-graph preview cost and concurrent previews — 2026-11-26

> **Status:** Research · **Type:** research · **Tier:** — · **Reviewed:** 2026-11-26

Timed check-mode previews (`make dry-run ANSIBLE_LIMIT='<exact-alias>' ANSIBLE_TAGS=`) of production nodes, the decision for each slow task, and the design that previews several nodes at once while deploys stay one node at a time. Recorded for task `OPS-1795697141240057`.

## No rollout log had per-task timing

The deploy controller enabled `ansible.posix.profile_tasks` since 2026-11-07. Operator rollouts run from fresh worktrees that install no Ansible collections, and the roles use only builtin modules, so the run succeeded and Ansible skipped the callback with a warning. The encrypted preview logs of the `d7a08417` rollout contain no timing line. The controller now installs a source-owned callback, `scripts/ansible_task_timing.py`, into the run's private plugin directory; every site run ends with its 20 slowest tasks, task names and roles.

## Measured previews

All timed runs used the full graph (`ANSIBLE_TAGS=` empty), check mode, and one worktree. Revision `93591d825` is `main` at `bc42a52b` plus the timing callback; `c7576d564` adds the retirement change below.

| Run | Node | Revision | Timed tasks | Ansible time | Result |
|---|---|---|---|---|---|
| `d7a08417` rollout, untimed | node-a (core) | `d7a08417` | 1265 | 57.3 min (controller run) | passed |
| `d7a08417` rollout, untimed | node-b (core) | `d7a08417` | 1305 | 25.1 min (controller run) | passed |
| `d7a08417` rollout, untimed | node-c (core) | `d7a08417` | 1267 | 17.1 min (controller run) | passed |
| `d7a08417` rollout, untimed | split-hop A | `d7a08417` | not counted | 21.6 min (controller run) | passed |
| base, concurrent with split-hop B | node-b (core) | `93591d825` | 779 | 904.5 s | SSH lost at 17:22 |
| base, concurrent with node-b | split-hop B | `93591d825` | 699 | 905.3 s | SSH lost at 17:22 |
| base2 | node-b (core) | `93591d825` | 1055 of about 1305 | 1443.0 s | SSH lost at 17:49 |
| opt | node-b (core) | `c7576d564` | 0 | — | refused in readiness: SSH session timeout |

The three core nodes run almost the same graph (1265 to 1305 tasks, about 720 executed and 550 skipped, about 900 module executions with loop items), yet their preview times differ by a factor of three. The difference follows the management route: no node has a direct Tailnet path from the operator machine, and each one uses a different DERP relay region. At 18:22 the median Tailnet RTT was 366 ms to node-a, 245 ms to node-b and 307 ms to node-c, against 120 to 155 ms at 17:24.

The time is a long tail. In the base2 node-b run, 1443 s over 1055 tasks is 1.37 s per task, or about 2.5 s per executed task (584 executed, 470 skipped). Without the two tasks that waited on a stalled connection, the 20 slowest tasks take about 300 s, about 20 % of the run; the other 80 % is about one to three seconds for each executed task or loop item. Skipped tasks and controller-local `set_fact`/`assert` tasks cost almost nothing. Every slow task makes a remote call in check mode: none of them is delegated to localhost.

Three of the four timed runs ended because the relayed management route stalled for longer than the SSH keepalive budget (15 s × 8): the shared SSH master closed and Ansible marked the node unreachable. The two concurrent runs failed in the same second on two different nodes, and a separate rollout session lost node-a at 17:46, so the stall is on the operator side of the route, not on one node and not caused by running previews at the same time. `OPS-1795702284251279` owns it.

## Slowest tasks: node-b (core, base2, 1055 tasks)

Decisions: keep, make cheaper, or skip in check mode. No decision weakens a recovery, security or authority gate.

| Seconds | Task | Remote in check mode | Decision |
|---|---|---|---|
| 76.5 | snell : Inspect existing snell unit before arming its boot fence | yes, `stat` | keep: the time is the stalled connection that ended the run; the task is one `stat` |
| 47.4 | runtime-release : Refuse an unrelated caller while credential revocation is pending | yes, `command` with `check_mode: false` | keep: a stall; its other run took 2.4 s, and it is a revocation gate |
| 24.7 | nginx-xhttp : Create private TLS publication state and public challenge roots | yes, `file` loop | keep: it previews ownership and modes of each directory |
| 22.3 | subscription-host : Remove only exact owned runtime files | yes, `file` absent loop | make cheaper: one call per absent path of a disabled role (`ANS-1795702245344721`) |
| 20.8 | nginx-xhttp : Install public TLS publication helpers without starting issuance | yes, `copy` loop | keep: the per-file diff is the reviewed preview |
| 20.1 | nginx-xhttp : Inspect managed public TLS directories before taking ownership | yes, `stat` loop | keep: ownership gate before TLS state is taken |
| 19.3 | baseline : Collect service facts | yes, `service_facts` | keep: later baseline decisions need the complete unit list |
| 19.2 | firewall : Install Tailnet firewall recovery units | yes, `copy` loop | keep: recovery units, reviewed per file |
| 18.9 | amneziawg : Install the complete AWG consumer dependencies | yes, `copy` loop | keep: reviewed per file |
| 18.4 | intrusion_prevention : Collect installed service facts after package acquisition | yes, `service_facts` | keep: a deploy needs the state after package installation; in check mode it repeats baseline's query, but the role also runs alone |
| 17.0 | firewall : Install Tailnet firewall recovery units (second run) | yes, `copy` loop | keep: as above |
| 16.4 | nginx-xhttp : Remove the model news units, script, configuration and state | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 14.3 | geodata : Remove only exact owned runtime files | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 14.2 | dns-morph-bridge : Inspect shared Unbound service before retiring its bridge fragment | yes, `service_facts` | make cheaper: the third full unit enumeration of the run is used for one unit (`ANS-1795702245344721`) |
| 13.4 | runtime-release : Remove only declared runtime authority | yes, `file` absent loop | make cheaper: present-only retirement, below |
| 12.8 | firewall : Install the retained firewall consumer and common transaction | yes, `copy` loop | keep: reviewed per file |
| 12.7 | nginx-xhttp : Install guarded public certificate renewal units | yes, `template` loop | keep: reviewed per file |
| 12.2 | subscription-host : Remove field-report ingest files and aggregate textfile | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 12.1 | subscription-host : Inspect exact owned units before retirement | yes, `command` loop with `check_mode: false` | make cheaper: one query for all units instead of one per unit (`ANS-1795702245344721`) |
| 10.7 | public-site : Deliver each bundle archive and schedule | yes, `copy` loop | keep: the bundle bytes are the preview |

By task name over all runs, `runtime-release` retirement is the most repeated cost: `Remove only declared runtime authority` took 43.9 s over 6 runs, `Validate complete declared runtime authority after stopping producers` 17.6 s over 6 runs and `Inspect every declared runtime unit including timers` 15.1 s over 6 runs, and the role ran 12 times in a full graph. By role, firewall (252.7 s), runtime-release (242.5 s), nginx-xhttp (223.5 s) and baseline (180.2 s) took 63 % of the timed part.

## Slowest tasks: split-hop B (base, 699 tasks)

| Seconds | Task | Remote in check mode | Decision |
|---|---|---|---|
| 83.1 | runtime-release : Validate complete declared runtime authority before stopping units | yes, `command` with `check_mode: false` | keep: a stall that ended the run; this is the authority gate before retirement |
| 25.3 | nginx-xhttp : Inspect public TLS lifecycle before owned retirement | yes, `stat` | keep: one `stat`, slowed by the route |
| 22.1 | runtime-release : Remove only declared runtime authority | yes, `file` absent loop | make cheaper: present-only retirement, below |
| 19.0 | subscription-host : Remove only exact owned runtime files | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 17.3 | baseline : Write the admin authorized_keys exclusively from admin_ssh_public_keys | yes, `copy` | keep: SSH authority |
| 16.8 | amneziawg : Install the complete AWG consumer dependencies | yes, `copy` loop | keep: reviewed per file |
| 15.6 | runtime-release : Remove only declared runtime authority (second consumer) | yes, `file` absent loop | make cheaper: present-only retirement, below |
| 13.6 | firewall : Install Tailnet firewall recovery units | yes, `copy` loop | keep |
| 13.4 | firewall : Install Tailnet firewall recovery units (second run) | yes, `copy` loop | keep |
| 12.8 | baseline : Enable forwarding for the effective routing workloads | yes, `copy` | keep: routing authority of the split-hop egress |
| 12.8 | transport-egress : Inspect consumer receipts and interrupted ownership before complete topology retirement | yes, `stat` loop over six journal names | keep: recovery gate before retirement |
| 12.1 | public-site : Remove the public site publisher units, script, bundles and state | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 11.9 | subscription-host : Inspect exact owned units before retirement | yes, `command` loop with `check_mode: false` | make cheaper (`ANS-1795702245344721`) |
| 11.5 | subscription-host : Remove field-report ingest files and aggregate textfile | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 11.3 | runtime-release : Install shared credential revocation admission | yes, `copy` loop | keep: revocation authority |
| 10.1 | baseline : Remove stock cloud-image accounts | yes, `user` loop | keep: account hygiene |
| 10.1 | firewall : Install the retained firewall consumer and common transaction | yes, `copy` loop | keep |
| 10.0 | runtime-release : Remove only declared runtime authority (third consumer) | yes, `file` absent loop | make cheaper: present-only retirement, below |
| 9.7 | nginx-xhttp : Remove routing list runtime | yes, `file` absent loop | make cheaper (`ANS-1795702245344721`) |
| 9.5 | firewall : Install the retained firewall consumer and common transaction (second run) | yes, `copy` loop | keep |

## Optimization: present-only retirement

`runtime-release/tasks/retire.yml` runs once for every disabled consumer, 12 times per production graph. Its removal loop made one remote `file` call for each declared path, and in the full `d7a08417` previews all 51 such calls on each of node-a, node-b and node-c found the path absent. Check mode also validated the same state twice, because it stops no unit. The validator now reports which accepted paths are present; the loop removes only those, from the validation after the producers stopped in a deploy, and check mode skips the second validation. A preview of an unchanged production node therefore makes 63 fewer remote calls (51 removals and 12 validations); a deploy makes 51 fewer. At the base2 rate these calls took about 123 s on node-b, about 8 % of a 25-minute preview. The live re-measurement of this change is not done: the `c7576d564` preview of node-b stopped in readiness on the same route stall.

## Design: concurrent previews, serial deploys

A controller run already keeps its working state private: it copies the decrypted secrets, the selected inventory line, the known-host pins, the SSH key and the generated playbooks into a run-owned directory, sets `ANSIBLE_HOME` and `TMPDIR` inside it, and puts the SSH ControlMaster sockets in a separate run-owned `/tmp/vd-ssh-*` directory. Two previews from one checkout ran at the same time in this research without local interference. The shared local state that blocks concurrent previews is outside the controller:

| State | Collision | Each concurrent preview gets |
|---|---|---|
| Canonical inventory `ansible/inventory/generated.ini` | Runners copy a node's inventory there before a run, so a second run overwrites the first one's input. | An explicit `ANSIBLE_INVENTORY` path that no run writes; the controller reads it once into its private copy. |
| Decrypted secrets path | The default `$RUNTIME_DIR/vpn-$(ENV).secrets.yaml` is shared by runs of one environment, and the first `make clean` deletes it under the other. | Its own `SECRETS_FILE` in a private per-run directory, cleaned by that run only. |
| SSH ControlMaster path | `ansible.cfg` has a shared default, but the controller replaces it with a run-owned `%C` socket directory. | Already isolated. |
| Checkout | The source identity is bound at start and roles are read during the run. | One clean worktree at the reviewed revision for all previews; one worktree per node is not needed. |

Only previews run concurrently. `deploy`, `verify`, `source-drift` and later stages stay one node at a time: `site.yml` keeps `serial: 1`, each node keeps its `transaction.lock`, and a deploy recovery assumes exclusive use of the node. A preview of a node during its deploy happened by accident in this research, because nothing on the operator machine records which node an operation holds; the selected change adds a per-node operation lock for `dry-run` and `deploy` and a fleet deploy lock for `deploy`. Production nodes use separate environments and secrets files, so concurrency is one controller process per node, not parallel hosts inside one run. With previews in parallel, the preview phase of a rollout takes about as long as its slowest node instead of the sum.

Measured with the locks at `e16a6a59e`: previews of node-a and node-b started together from one worktree. node-a took 1040.5 s for 1265 tasks and node-b 1382.7 s for 1305 tasks, both with no unreachable or failed host, so the two previews took 23 min 5 s instead of 40 min 23 s. A third preview of node-a, started while its preview ran, stopped with `node-operation-in-progress` before it read secrets.

## Follow-up tasks

- `OPS-1795702314418305` (OpenSpec, `spec_mode: required`): per-node operation locks and a fleet deploy lock in the controller, and the concurrent preview recipe.
- `ANS-1795702245344721`: remove absent owned paths and query owned units without one remote call per item in the other retirement loops (subscription-host, geodata, nginx-xhttp model news and routing lists, public-site, hysteria exporter) and replace the dns-morph-bridge `service_facts` query.
- `OPS-1795702284251279`: find and remove the management-route stall that ended three of four timed previews and a deploy on 2026-11-26.

## Gaps

- The research runs did not time the complete graph: base2 timed 1055 of about 1305 node-b tasks, and the split-hop B run 699 tasks. The later concurrent previews timed the complete graph of node-a and node-b only; split-hop nodes and node-c have no complete timing.
- The timed split-hop run is B; split-hop A was deployed by a concurrent rollout during this research and was not previewed.
- The effect of the retirement change is computed from the measured per-call cost and the full `d7a08417` previews, not re-measured live.
