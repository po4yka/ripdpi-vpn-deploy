# tests — coverage matrix

## Layers

| Layer | What | Where | Speed |
|-------|------|-------|-------|
| Unit | Python validators + Jinja-render assertions | `tests/unit/` (pytest) | seconds |
| Snapshot | Golden Jinja renders for every template | `tests/snapshot/` | seconds |
| Schema | `validate-secrets.py` jsonschema | `tests/unit/test_secrets_schema.py` | seconds |
| Molecule (role) | Per-role Ansible scenario in Docker | `ansible/roles/<role>/molecule/` | ~1 min/role |
| Molecule (full-stack) | `site.yml` end-to-end | `ansible/molecule/full-stack/` | ~10 min |
| TF test | `mock_provider` plan-shape tests | per `terraform/providers/<name>/` | seconds |
| CI ephemeral deploy | Label-gated real UpCloud deploy | `.github/workflows/` + `docs/CI-REAL-DEPLOY.md` | ~15 min |

## Design decisions

Recovery boundary tests use real age ciphertext and preserve the prior state
inode on failed decryption or structure validation. Same-second writers publish
distinct complete private backups; reserved environment aliases refuse before
Terraform or private inputs.
File and directory sync failures refuse success and retention; directory sync
failure retains the complete, decryptable private backup already published.

Real restic restore cases remove one selected artifact at a time, including
delivery TLS/vhost, auxiliary transports, topology policy and watchdog inputs.
Empty revocation sets remain valid. Archived absolute links resolve only within
the restored filesystem; a live-only target cannot satisfy verification.

Recipient regressions execute actual Ansible share mode repair, including retained
shares without a new upload and unchanged repeats. Molecule separately checks
nginx-group read access, unrelated-UID refusal and mirror true-to-false execution
retirement with accepted payload and replay authority retained. RIPDPI hopping
refuses before output; official sing-box keeps supported hopping.
Expression-only Jinja test environments enable autoescape explicitly; their
compiled predicates keep the same boolean results.
The mirror retirement fixture defers independent timer schedules and drains their
services before its exact authority baseline. Timers stay enabled and active for
the check-mode control. All seven authority categories remain exactly compared;
failure diagnostics expose only fixed component names and change booleans.

DHCPv6 portable tests exercise actual admission and both rendered egress policies.
The native hopping suite additionally sends real UDP across owned network
namespaces through the complete rendered firewall; wrong interfaces, ports and
unapproved global server addresses remain negative cases. A separate native case
keeps the original twelve probes intact and warms one unicast tuple before wrong
interface checks in both directions. It repeats the same link-local addresses on
two links, observes established state at priority -1 without a verdict and
requires both cold and established denials. No conntrack flush separates probes.
An expected local OUTPUT drop accepts only EPERM from sendto on an explicit
negative probe; the receiver must still see no packet. Positive sends and other
errno values remain fatal.
The DHCPv6 receiver binds and joins its multicast group before readiness. It
checks the actual socket's bound interface and exact group membership on that
interface. Missing, unreadable or mismatched membership refuses before the
sender runs. It does not query an input multicast FIB route: that query can
require multicast forwarding state which local UDP delivery does not use. Its
complete observation window starts only after the parent confirms the sender
result through a bounded control acknowledgement. Portable real loopback UDP
regressions delay sender startup beyond that window and require missing control
acknowledgement to refuse. Native probe diagnostics contain fixed phase names,
bounded millisecond counts and packet-presence booleans only. The multicast
probe also records group membership, no-verdict OUTPUT/INPUT counters, late
POSTROUTING and early PREROUTING counters, and UDP
error, no-port and ignored-multicast deltas in its owned namespaces. Counter setup and UDP baselines precede
listener creation; the receiver reads membership before readiness, so the parent
adds no observer command between readiness and send. The runner admits one exact-schema record
only after a complete attempt and successful observation, with fixed labels,
bounded integers and booleans. Missing UDP metrics or unmeasured values leave
the record absent. Passing pytest output remains private; failure output supplies
the validated CI record. Observation errors
retain the packet outcome and raw logs stay private. Unknown fields, duplicate probes
and oversized or malformed records publish no diagnostics.
The two transit counters use the same fixed tuple and install/query calls as
the OUTPUT/INPUT counters. They locate loss between output and local input;
they do not prove that the packet crossed the veth link or identify its cause.

Only the failed bootstrap multicast case can publish a DHCPv6 readiness
property before ready. It contains only the fixed bind-join stage and a zero
not-applicable authority mask. Obsolete route stages and masks are refused. No
raw child output enters public evidence. An actual pytest JUnit regression
retains the original receiver refusal and verifies this property through the
runner parser. Readiness evidence is separate from complete packet observations.
The sender remains blocked until ready, and all probe assertions and deadlines
stay fixed.
The core runner first runs both complete canonical DHCPv6 cases in its private
scratch directory. A pass still requires the unchanged complete core suites;
a failure leaves the main suites incomplete with success false and verified
cleanup. Early JUnit never substitutes cases in the complete suite manifest.
On an early packet failure, the runner retains the completed observation through
the hopping suite's closed parser and field. Successful early gates publish no
sample; canonical hopping owns the single record otherwise. A pre-ready refusal
still has no structured readiness entry in the main result. Retention does not
establish the cause of a lost packet.

Offline sentinel regressions use the exact deterministic no-TUN Git fixture
and real source admission, installation, input hashing and standalone readers.
They prove refusal before mutation for wrong assets and input identities, plus
retention of the prior toolchain. They do not claim a physical client result.
Publication-only native fixtures pass their actual acquired Go directory to
configure; a binary content digest is not an upstream source commit.

Host native CI copies the completed runner checkout and artifacts into a unique
root-owned directory under `/opt` before root AWG admission. Tests execute the
actual staging and cleanup shell on an owned temporary tree, with only the
privilege boundary and paths changed. They retain original bytes and inodes,
preserve symlinks, remove failed copies and reject cleanup outside the owned
stage. Root runtime steps use that copy; source ownership checks stay strict.

Native SOCKS readiness reads the full two-byte method selection within its
original ten-second deadline. EOF, wrong version and wrong method refuse.
Only failed hopping cases may publish a bounded five-field readiness summary:
family, phase, cycle, reason and unit state. Source strings, endpoint details,
unit names and raw child output remain private. Real socket regressions cover
fragmented replies and stalled peers; they do not establish native QUIC traffic.

Native AWG failure summaries reuse the reviewed strict three-file projection.
Only fixed family, phase, result and expected enums plus a bounded cycle reach
public case evidence. The actual pytest JUnit regression retains raw child
output in private local files and refuses unknown, duplicate or oversized
properties. Packet assertions, source policy, retries and deadlines stay fixed.

The native AWG lifecycle lab passes one explicit canonical source root to its
parent adapter and isolated child. Source descriptors, tools and executable
paths share that root. Do not recreate `/opt` aliases: source admission refuses
symlink ancestors before it verifies the exact correction and binary receipt.
Portable admission tests use synthetic Git and executable bytes only; they do
not establish AWG traffic or compiler acceptance.

AWG checksum regressions execute the actual pinned Go completion and
segmentation functions through an overlay. Independent checksum arithmetic
covers zero and nonzero UDP, both address families, TCP zero preservation and
later zero segments. The native packet case sends the exact zero-producing
IPv6 tuple and an adjacent control through unchanged production guards. It
requires six real DNS replies, completed pre-NAT ffff/fffe checksums and no
checksum errors. Synthetic Git and no-TUN Molecule cases prove admission and
lifecycle only. Native build receipts bind corrected source to binary bytes.

Network protocol regressions retain real socket delivery after both TCP FIN
directions, bounded blocked-writer behavior and empty UDP payloads. Certificate
fixtures use isolated test CA trust and distinct root/intermediate identities;
untrusted supplied roots cannot certify themselves. Resolver tests execute
actual relocated Ansible tasks through enable, interrupted apply, deferred
retirement, disable and repeat convergence, preserving custom resolver authority.

The native upgrade fixture renders hopping ingress for its owned host veth in
both IP families. This render-only context preserves the facts used by canonical
Ansible convergence. The exact local-destination redirect, native authentication
and observed multi-port traffic remain required.

Transport audit regressions cover local-only hopping NAT, forwarded UDP,
retained split-hop denial during tunnel stops, strict overlay allowances,
complete multi-host metadata and exact client bandwidth hints. DNS-Morph
preflight tests run the real controller validator before synthetic mutation
sentinels. Render fixtures and research stubs establish no live protocol claim.
Strict overlay-only render tests compare the complete UDP allowlist in both
toggle states. Link-local DHCPv6 stays on the explicit uplink despite unrelated
overlay default-route facts; broad UDP and unapproved global servers stay absent.
Provider NAT guard tests allow only the exact DHCPv6 preflight import before the
firewall assertion; the split-hop assertion stays first. IPv6 control ordering
uses the unique standalone terminal drop, independently of earlier scoped denies.

Checkout metadata regressions use real Git with large NUL-framed input,
non-UTF-8 path bytes and an owned attributes FIFO. Retain active-filter refusal,
index identity, empty-input EOF and the query deadline. Telegram flood tests
cross actual local HTTP handlers into a synthetic upstream and require later
webhooks and canary send/edit to share the same monotonic deadline.

Security delivery regressions use real local redirect servers, synthetic SOPS
and age authorities, and actual private filesystem publication. Failure and
interruption checks preserve the last complete generation. SSH planner tests
exercise the exact prior managed policy, hybrid promotion, retained rollback
bytes, contextual effective policy and idempotency. A successful parser test
does not prove a live SSH or hardware migration. Subscription tests race real
HTTP readers against filesystem publication and cover fsync, rename, signals,
legacy input, mirror generations and private namespace admission.
Legacy HTTP fixtures use the role's exact 0700 route modes and distinguish
expiry parsing failures from unsafe file authority. Inventory cases send LF and
CRLF encoder output through the real renderer and strict host parser.
Synthetic SOPS decryptors consume all ciphertext from stdin before they return
fixture JSON. A payload larger than pipe capacity checks this contract on
Darwin and Linux.

Protocol audit regressions use schema-valid synthetic inputs and actual
controller preflight in ordinary and check mode. They prove identity/address
refusal before later publication, exact parsed server/client credential bytes,
and retained positive controls. Delivery cases consume generated remote URLs
through the real local backend; native nginx checks unmatched and disabled
bearer routes as well as successful and failed proxy outcomes. Certificate
cases run the complete script with issued certificates and matching CNs, so
missing or mismatched SANs cannot pass through subject fallback.

Disposable CI admits the fixed root-owned executable and acquisition directories through no-follow directory descriptors before it installs clients. Only the `/usr/local/bin` and `/opt` leaf modes change to 0755; unsafe ancestors, symlinks and foreign ownership refuse. Executable regressions run the exact inline admission code in an owned temporary tree, with only its paths and expected UID changed, and preserve existing child bytes and inodes. The complete AWG native fixture creates its fresh claimed acquisition root and release directory with explicit 0755 modes; actual umask 0000 and 0777 regressions prevent unsafe default intermediate permissions, without changing existing authority.

The early AWG rollback step runs the complete canonical dual-stack goal with the same pinned sources and isolated environment. The final native bundle retains that goal to check the complete runtime context.

Warm AWG startup failure evidence reports only fixed unit-state values, bounded numeric status and parent/source metadata, fixed journal categories and literal known role task names. A separate process loads unchanged installed helpers without bytecode writes and probes transaction check-mode validation plus adapter validation/inspection; it never applies or recovers. Refusal text is admitted only when it equals a literal categorical code in those helpers. Unknown values, exception messages and raw journal text never enter test output. The early CI warm case does not replace the complete native runtime suite.

AWG namespace adapters prepend their owned executable directory to the inherited toolchain PATH. A portable regression resolves a non-global symlink to the actual pinned Ansible executable and runs `ansible-playbook --version`; real role publication and compensation remain native CI checks.

AWG native configuration expectations use Ansible block trimming and retain the final newline. A portable comparison executes the actual template lookup and checks exact bytes; generic snapshot rendering keeps its existing contract. Warm adoption uses the actual initial role and complete publication task. A changed complete generation may replace unchanged file inodes; retain exact bytes and modes across binary-only changes, and assert inode stability on unchanged convergence. Custom unit candidates use the publication task rather than claiming the full role would retain fixture-only settings.

Private authority fixtures set their owned root to the process GID. Darwin may
inherit another group from the home directory; matching the production storage
contract here keeps strict ownership checks active in portable tests.

Deployment recovery regressions execute real Make scheduling with inherited
parallel controls and require no deploy after a failed check. Process cleanup
regressions include exited command leaders with live descendants. State backup
tests use actual age encryption over synthetic state and execute the documented
recovery selector; preserve valid backup names for sibling environments.

Protocol compatibility checks use pinned real engines and synthetic local
credentials. P0, Snell and Naive failure paths prove authentication and privacy;
mtg release/parser checks make no Telegram requests. An inert service fixture
proves lifecycle behavior only, never protocol parsing or authenticated traffic.

REALITY monitor cancellation tests wait until synthetic decryption has completed, assert that the shell work path is inside the supervisor-owned parent, and then deliver each supported termination signal. Genuine SOPS/age coverage encrypts YAML with a fresh synthetic authority and requires successful monitor admission and cleanup. CLI diagnostics remain on stderr while stdout remains JSON-only. Aggregate-deadline coverage admits the intended descendant before expiry and retains one bounded clock across setup and cleanup.

Runtime acceptance requires the production log-parent trust contract: root ownership and no group/other write permission. Tighten an owned disposable image before tests; never relax the descriptor-based provisioner or rewrite its failure as a successful activation.

Native Alertmanager timeout coverage publishes split alert updates inside a real grouping window. Zero group wait can dispatch before all seven alerts join the group; retain the five-alert cap, two-alert truncation and one-second webhook deadline assertions.

CI jobs that execute the real taskctl/workspace integration fetch complete Git history: immutable archive-link projections require the reachable terminal source commit. Missing history remains a refusal, never an inferred receipt match.

Real log rotation uses the configured authenticated-probe deadline across process replacement. The pinned REALITY engine has a five-second cold target-record learning loop; steady-state destination-boundary probes retain their three-second socket budget.

Watchdog race regressions replace socket ownership after vacancy admission and during the canary. Success and server recovery both require the retained client PID to own its loopback listener.

REALITY partial-input regressions reject explicit invalid fields before loading missing operator-private defaults. DNS worker regressions exercise overflow refusal and complete deduplicated candidate sets; runtime TLS and owned-public paths remain separate real-engine checks.

The disconnected TUN fixture pins extracted Xray 26.3.27 binary digests independently for amd64 and arm64; unknown architectures or modified executables refuse.

Native transport fixtures retain each owned unit before starting it and verify stopped PID/state before deleting runtime authority. Portable controller regressions retain authority after a lost start acknowledgement or unconfirmed stop; they are not native traffic evidence. Redaction assertions use the effective fixture credential rather than a stale literal. Failed start acknowledgement or unconfirmed stop cannot become a passing cleanup.

Alternate XHTTP regression cases exercise canonical materialization through the real semantic resolver and native profile adapter; mocked provider metadata is input selection only, never traffic proof.

AWG constrained-path failures retain the bounded client exception, traffic phase and IPv6 UDP error counters alongside route and peer evidence. Probe diagnostics contain only owned synthetic traffic metadata, never AWG credentials.

AWG constrained-path failures publish one bounded `awg-probe-summary` JUnit property. It contains only IP family, reconnect cycle, the last complete exact traffic phase, expected admission and process result. The four-transport runner admits its strict five-field JSON only for the two failed or errored dual-stack cases. It drops duplicate properties or keys and invalid fields. Portable regressions execute the actual probe failure and timeout hooks through real pytest JUnit and preserve their original failures. This evidence does not establish native traffic acceptance or explain older artifacts.

Ingress/egress commit tests kill a separate process before and after the durable decision, native outer finish and ingress journal deletion. Portable tests model only the egress adapter; the native lane retains a real accepted outer route and proves authenticated canary traffic after roll-forward or whole-route rollback. Ansible composition also covers a lost acknowledgement after journal deletion so rescue cannot revert committed egress. Native acceptance uses the least-duration split so new boundary cases mix with existing lifecycle cases instead of accumulating in one contiguous partition.

Native interruption fixtures launch Ansible in a uniquely owned transient
systemd scope. Module workers may create separate sessions, so process-group
signals alone cannot reclaim the invocation. Real scope regressions cover
normal launcher exit and SIGKILL while preserving a foreign worker.

Portable CI shards fetch complete Git history for real `taskctl` workspace
queries. Completed related-task references are accepted through committed
closure history; a shallow checkout cannot establish that history. The shard
budget includes those audited pointer lookups.

Authenticated watchdog XHTTP cases retain primary/fallback delivery and refusal boundaries in both auto and tuned stream-up mode.

The complete XHTTP delivery matrix extends the endpoint target with real native
Xray format consumption, distinct alternate TLS identity, primary outage,
wrong-certificate refusal, bounded-pool comparisons, idle reuse,
process reconnect, namespace-only netem and baseline restoration. Aggregate
measurements contain bytes, timings, RSS and socket counts only. Local fixture
processes do not establish physical-client or production acceptance.

Native lab retirement clears failure state only for its claimed stopped unit names after removing their files, then requires systemd to report each as absent and inactive. A failed removed unit can otherwise remain cached with a load error and poison the next lab's initial admission.

Subprocess ownership regressions require a retained session leader at the group signal boundary, and real quiet descendants must stop after successful exit, timeout, owner loss or a broken status report. A denied group signal fails once, while the private control channel still reclaims the supervisor. Fallback kill and wait failures retain categorical diagnostics.

REALITY monitor regressions execute 256 KiB TLS transcripts through the actual shell path. Valid transport checks retain healthy classification or an unknown ASN lookup, rather than failing because a quiet pipeline reader closes early. Certificate, SAN and ALPN refusal cases remain required.

WARP teardown regressions require successful fresh kernel absence checks before accepting concurrent veth removal. Persistent links, replacement namespace handles, dangling aliases and unreadable probes refuse; failed preparation retains its original error after successful compensation.

The AWG source-candidate lab compiles exact upstream baseline/candidate pairs
and exercises real systemd/TUN traffic in a disconnected local container.
APT inputs use a dated signed Ubuntu snapshot; the minimal base bootstraps TLS
from a checksum-pinned public CA package. Portable regressions exercise delayed
container visibility, explicitly unknown cleanup and moved refs with warm bundles.
Packet captures and mixed-version TCP/UDP/DNS are Linux runtime evidence only.
Production-role readiness and physical Android acceptance are separate claims.
When placing lab input manifests, consult `.github/workflows/contract-sync.yml`:
keep local build provenance beside the lab fixtures and reserve `contract/`
for client-vendored payloads.

Dual-family namespace probe regressions force both IPv4-first and IPv6-first logging. Concurrent child launch order does not imply log order; require exactly one request per family, the same namespace and in-tunnel hostname resolution in either schedule.

Controller interruption fixtures release their synthetic workers through an owned stop marker and retained subprocess handles. Cleanup never signals a recorded process group after its ownership can have expired; privacy and child-removal assertions remain unchanged.

ECH and BBR recipient fields are materialized in the shared Python payload path used by both delivery and drift inspection. The internal XHTTP-only selection retains semantic admission and is refused by bundle export.

Bootstrap failure regressions execute ECH refusal, encryption failure and termination with synthetic tool authority, remove only newly staged plaintext and preserve existing operator documents. Bundle tests reject the monitoring-only flag before producer execution; adapter cases bind staged credential paths, and a real systemd case converges ECH in a custom configuration directory without relying on a default key.
Controller path tests retain exact unit ownership and reject ambiguous or unsafe configuration selections before frontend credential reads.

ECH export and sentinel cases keep distinct nginx and ECH inner identities. The real native recipient matrix also retains that distinction, so hostname fallback cannot silently bind ECH to the unrelated frontend.

Parser adoption regressions execute both CI installation fragments with checksum-verified real sing-box bytes and an owned destination. Local acquisition supplies verified, tampered, truncated, wrong-version and incompatible-executable archives. Refusal must retain the prior inode and an actually usable parser; successful full-profile acceptance must atomically replace it and clean staging.

Guidance coverage exercises the workflow's actual Git collection against an advanced base branch. Preserve full history for three-dot comparisons; a shallow fetch can hide the merge base after checkout.

Baseline resource tests execute its real first Ansible assertion and require an invalid value to stop before the next mutating task. ECH native leak checks run Hysteria with debug logging as well as secure positive/negative recipient traffic. The systemd generation case adopts both BBR profiles under the actual credential sandbox.

The complete native transaction suite is split into two disjoint CI groups in independent fresh systemd containers; both are required and a collection test proves their complete union. Keep the full local Make target unchanged.
Each case imports installed runtime helpers only after its own lab has established the module path; isolated partitions must not depend on earlier cases initializing the interpreter.
ECH probe regressions exercise both isolated import and Ansible's inline loading. Whole-route snapshot cases retain private ECH bytes, permissions, group and exact absence; generation helper unit cases establish their own runtime library path.
ECH identity admission excludes literal IPs before executable acquisition. Native UDP listeners probe the UDP port space; BBR recipient tests retain the paired XHTTP intermediate while refusing unqualified engine output.

Warm Hysteria upgrades retain Salamander and exercise the canonical firewall redirect through the lab veth. Per-port counters must observe an actual five-second client hop before and after upgrade and compensation; a datagram outside the range remains unchanged.
The native client may randomly choose its current destination again. Keep authenticated traffic running within one finite observation deadline until counters prove two distinct destinations, then require a fresh authenticated request before accepting the hop.

ECH native traffic stays in a private netns. Host-wide UDP ceilings are observed, tuned and restored before entering that namespace because Linux 6.8 does not expose them there. Packet decoding explicitly selects QUIC for the allocated test port. Capture only supported-recipient traffic and trust failures, outside the throughput measurement interval. Root CI steps preserve the pinned Python PATH.
The controlled 0.1% random loss applies only to concurrent throughput measurements. Single-datagram UDP/DNS functional assertions retain the same five-millisecond path without injected loss, so expected UDP loss cannot randomly invalidate acceptance.

Native frontend fixtures verify the same upgraded Hysteria bytes as the builder. Smoke control-flow fixtures load the deployed CA directory from shared group variables; encrypted synthetic fixtures must track the plaintext runtime selection.

ECH unit cases check wire framing, private/public key agreement, identity/generation matching, strict emitter routing and root-only systemd credential wiring. They are source evidence; exact native ECH negotiation, packet identity, traffic and generation compensation have a separately selected Linux lane.

AWG onboarding fixtures use an HTTPS hostname so the real dual-family probe
validator admits the positive path. Rotation tests follow the canonical
configuration transaction and its private loops; the removed restart handler
cannot stand in for complete failure compensation. Native CI coverage includes
the dedicated dual-stack lane alongside binding and general runtime targets.

Tagged deployment and AWG rotation execute the same real listener admission;
mismatched or missing provider contracts must refuse before a mutation sentinel.
AWG rotation publishes canonical firewall claims before the complete peer
role lifecycle and retains prior firewall authority through refusal.
Exact-node fixtures execute only the node/environment play heads; separate
listener admission regressions cover positive, mismatch and check-mode paths.

AWG failure tests change both peer claims and MTU, publish the real canonical
firewall candidate, then verify real nft restoration before authenticated prior
traffic resumes. The nft adapter only enters the owned network namespace. Adapters must be
executable before any mutation, because PATH lookup skips a noexec mount and
could otherwise select the global nft binary. The canonical AWG target owns
private executable scratch under /var/tmp and removes it on exit.

The AWG dual-stack native lane uses exact pinned AWG TUN peers and the complete
canonical nftables render. Its owned namespaces exercise nondefault and multiple
instances, constrained MTU, DNS A/AAAA, bidirectional TCP/UDP, source spoofing,
cross-instance denial, revocation and native fallback denial. Measured counters
and traffic distinguish that Linux proof from Android emulator/native-core,
physical-client and fleet acceptance.

Runtime publisher tests verify retained directory descriptors remain valid
inside normal and predictive transactions and close after success, exceptions,
interrupts and failed entry or lock acquisition.

AWG device tests use real SOPS/age round trips for selected pool issuance,
revocation and interrupted/unsafe publication. The named native binding target
owns isolated namespaces and exact pinned AWG builds; it proves two devices'
TCP/UDP traffic, wrong keys/headers and selected revocation with the other
instance still working. Portable mocks never stand in for this runtime proof.
Atomic enrollment Bats cases run actual encrypted transactions too; their CI lane
installs the pinned Python environment and checksum-verified SOPS with age.
URI QR boundary tests consume actual encrypted issuance and inspect the exact
codec input; failure retains the private URI for recovery. Dash-prefixed device
names exercise both the shell wrapper and Make issuance/revocation surfaces.
Binding cases reject absent registry authority and cross-instance duplicate
devices. Shared encrypted/native fixtures contain complete matching recovery
keys and registry bindings for every device. Real encrypted Make defaults and AWG-only revoke/reissue cases preserve
non-AWG registry fields; schema tests share runtime interface-name boundaries.
FIFO sources must refuse promptly and release the writer lock. Make audit
regressions decrypt actual age envelopes and require no event for failed
transactions; first-time token entries must satisfy the complete secrets schema.
Multi-host refresh tests use distinct per-host documents and keys, retaining
explicit AWG delivery selection despite missing or conflicting ambient input.
Mutation tests preserve ciphertext when any unrelated registry relationship is
broken; de-onboarding rejects rebound provider/environment identities. Isolated
inventory fixtures copy the shared AWG registry module with the secrets validator.

XHTTP endpoint acceptance is a separate complete target within the native job.
Its cases and the existing native/RTA lanes form a disjoint complete collection,
with selected skips fatal. Both served ports exercise actual pinned clients,
conflicting forwarding headers, private backend peer observations, discovery,
complete native candidate refusal and Hysteria's owned TLS proxy. ARM64
native runs require the repository-pinned base and exact ARM64 runtime checksums;
emulated executable identities cannot stand in for native authority. Runtime
upgrade fixtures share one admitted path-free origin between canonical identity
and Hysteria input; a trailing slash is a path and refuses before acquisition.

Payload-classification fixtures control elapsed time independently of curl
completion. Uniform and spiking RTT scenarios execute the real classifier;
the clock shim delegates every other Python invocation to the pinned interpreter.

Destination fixture gateways claim both TCP and UDP sockets on the same native
gateway port before accepting a candidate. Cross-protocol address collisions
release both candidate sockets within a finite allocation bound; other errors
propagate. The regression creates a real conflicting UDP lease.

Native Hysteria validation checks root-private transient unit permissions before forced publisher death; portable recovery rejects even an exact recorded public-unit claim before touching the service or lease resources.

Sender queue regressions preserve the pinned atomic metadata and empty initial-chunk staging forms, reject invalid names/sizes, and bound live inode-change retries separately from foreign-authority refusal.

Sender activation regressions include the handler-flush boundary after a rescued first cutover. Adapter timer notifications require durable sender acceptance before unit installation.

The enabled collector scenario verifies 42,000 current, 24-hour historical and
churn samples from ten fixture node labels through the managed sender, including
exact values/timestamps after durable-queue restart and unchanged resource/public
nginx boundaries. It is a bounded cardinality workload, not ten enrolled hosts or
seven-day capacity. The Kuma CI role job also runs its pinned upstream image
with network disabled, verifying missing-signal timing, restart persistence and
age-encrypted isolated restore. External notification receipt remains unverified.

**Monitoring regressions cross the real boundary** — consume actual private
watchdog output, age frozen producer evidence with the pinned PromQL evaluator,
and compare declared units to partially missing native series. Long generated
alert URLs and realistic returned Message bodies exercise relay limits.
Grouped required-service failure and missing-evidence notifications retain each
unit's validated role through firing, recovery and exact omission accounting.
Observer termination tests execute the production backup/recovery helper;
fixture-only signal cleanup cannot prove the installed service's restoration behavior.
Pinned receiver readiness retries only expected startup HTTP 503 and refused or
timed-out loopback connections within one deadline; unexpected errors propagate.

Set fault-injection permissions explicitly when rejection depends on mode; restrictive CI umasks can otherwise create a safe node instead of the intended unsafe fixture.

Pytest module basenames must be unique across `tests/unit`, `scripts/tests` and
`vpnd/tests`: the full collection and shard-consistency checks import them together.

Runtime audit regressions cover guarded and unguarded Xray log rotation, exact
producer-owned metric files with foreign-owner, symlink, hardlink and ancestor
refusal, and named AWG observers including a failed secondary instance. Native
Linux cases clear both IPv6 neighbor caches before strict-firewall exchanges and
retire metrics written by a real service account. Portable checks do not replace
these native systemd and packet checks.
Local Ansible observer fixtures set `become: false` and isolate Ansible config.
Task slices after AWG normalization supply its names-only output explicitly;
the dedicated AWG test executes the actual normalization prerequisite.
Retirement owner-map tests execute the actual consumer role variable declarations
and stdin expression through Ansible; YAML mapping keys do not expand Jinja.
Collector authority rotation tests isolate Ansible settings and enable local
connection pipelining. Their subprocess budget covers the complete Ansible
transaction; production readiness deadlines and rollback assertions stay intact.
Cascade and deploy parity fixtures use the same isolated local connection policy;
their complete transaction budgets do not change explicit deadline tests.
Bounded command tests exercise real pipe backpressure and exited-child cleanup
without suppressing live-process or repeated signal permission failures.
Schema-client regressions use real owned children and local Docker command
adapters to test blocked input, partial-write integrity, one shared deadline,
client shutdown before removal and uncertain cleanup refusal. The timeout
fixture waits for client readiness before delivery; these tests do not contact
Docker or prove daemon or provider acceptance.

**Project audit regressions cover operator boundaries** — synthetic Git histories
isolate ambient Git configuration only in temporary repositories. SSH and runtime
release fixtures set their intended group explicitly. Runtime release fixtures
set the group on their owned temporary root before they create child directories.
Installer tests reject invalid checksums and provenance before execution.
Host-selection tests cross the actual CLI and
shell boundaries; token refresh, private locks and promotion tests exercise
rejection and concurrent callers. These checks do not establish live host,
provider, release or Linux systemd acceptance.

Registry issuance uses a fake SOPS consumer that reads the complete document
before writing output, as the real parser does. A partial-JSON EOF regression
retains exact output bytes. Issuer calls have a 30-second deadline and reclaim
only their owned process session before reporting timeout or failure.

**Operator incident verbs run real Ansible guards** — `test_operator_verb_scope.py` derives each play head (hosts, serial, any_errors_fatal, pre_tasks) from the shipped playbook and runs it with real `ansible-playbook` against a local inventory for no limit, a node list, a one-host group and a one-host pattern, asserting the marker task never runs on refusal. It also checks rotation against an inventory `env` that differs from `ENV`, uses the real `make require-exact-node` recipe and `make -n` wiring, and compares the alias grammar of both the Make guard and the vpnd rotation builder (`vpnd.runner.ansible.rotate`) with the play guard's, which cannot be tested from `vpnd/tests` because mutation copies lack `ansible/`. It also covers hostile `ANSIBLE_LIMIT` spellings (the marker is never created and the text never appears in `make -n` output) and refusal of any other goal in the same invocation. Recording `ansible-playbook` and `ansible-inventory` stand-ins show that inherited `ANSIBLE_SKIP_TAGS` and `ANSIBLE_RUN_TAGS` are scrubbed and that verbs sharing an invocation run one at a time under `-j4`, and a recording `make` stand-in runs the four guarded blocks the runbooks print, under `bash` only like their fences: the per-node revocation sequence of `RUNBOOK-rotate.md` and `RUNBOOK-deploy.md` and the REALITY keypair and restic password sections of `RUNBOOK-rotate.md`. Each is a subshell whose EXIT trap runs `make clean`. The revocation cases assert that every node is rotated and verified, the visible stop messages, that one `e` assignment sets the environment of every call (the harness reruns the block as staging), that the sequence exits zero on success and with the failing step's own status otherwise (the cleanup does not mask it), and that SIGINT, SIGQUIT, SIGTERM and SIGHUP delivered during a rotation, whether to the subshell alone or to its whole process group as a terminal does, or SIGINT during decrypt, stop the loop with `make clean` still the last step and a non-zero status. The two deploy sections assert that cleanup runs last with the failing status for decrypt, deploy and verify failures and for signals delivered to the subshell during deploy, and that a failed decrypt never reaches deploy. All four blocks also run with a `make clean` that fails (exit 1 after a successful run, the failing step's own status after a failure) and with a second signal of each kind delivered to the whole process group while `make clean` runs after an interrupt, which must still complete. SIGKILL and power loss cannot run cleanup and are not simulated. This establishes source behaviour only, not live host selection or SSH reachability.

**Recovery clock tests isolate their time facade** — copy the adapter's time
interface before patching sleep or clocks. Subprocess polling keeps real time,
so candidate validation cannot advance synthetic worker timestamps.

**Transport boundary proof uses real protocol paths** — portable tests cover typed authority and socket contracts; disconnected Linux native tests use the pinned gateways, sealed libc/NSS, real REALITY/Vision and XHTTP TLS frontends, and Hysteria TCP/UDP. Kernel tests count forbidden endpoint contacts after earlier ACCEPT and DNAT, while public traffic remains positive. Active lifetime and quiet quarantine are measured once in the common helper lane. An owned TUN fixture does not establish vendor WARP registration or live acceptance.

Native fixture configuration is written to private `0600` candidates and atomically published; TUN contexts yield only after setup and namespace restoration succeed. Peer, initial and replacement TUNs, capture sockets and bounded packet workers have lexical ownership; worker teardown precedes descriptor closure on success and failure. Private TUN fixture configs start as `0600` before writing and receive the gateway group only after complete serialization.

**Temporary validation reporting uses actual localhost Ansible** — two runs
execute the owned candidate lifecycle and retain accepted config/helper/unit/TLS
bytes and metadata. Real Hysteria semantic refusal must clean up without
publication. Predictive check-mode changes and a genuine persistent change must
remain visible to the installed Molecule idempotence parser. The portable Xray
candidate uses its real Python semantic admission function; this reporting test
does not establish native parser, protocol, or TLS acceptance.

**Interrupted protected ingress runs through the production tasks** — `test_transport_site_transaction.py` splices the real detection, helper-admission, adoption and refusal tasks from `transport-ingress-begin.yml` into the localhost harness, replacing only the journal, `pending.json`, outer-helper, outer-state-directory and `outer.json` `stat` paths, the state directory's root-owner condition (retargeted at the test user) and the outer status command, and drives the real nginx publication helper. The shared transport-egress `helper-authority.yml` task runs verbatim except that its interpreter, state root, helper directory, ancestry walk and root-ownership checks are retargeted at the harness tree and the test user. The egress quiesce and rollback tasks are stubbed, and the event stubs set `check_mode: false` so a check-mode run that wrongly quiesced is logged; separately, the retargeted outer status command writes a `status-ran` marker if it ever executes. It proves compensation order for an open, closed and absent egress outer route, next-run convergence, check-mode refusal without mutation, a pending-only `pending.json` journal that refuses dry-run as `interrupted-nginx-publication` (not the protected-ingress category) and is recovered by one deploy, refusal of a symlinked, group-writable, hard-linked or writable-directory outer helper before it runs, categorical outer-status refusal and a retained malformed journal, which with an open outer route quiesces the candidates but never resumes the accepted generation. A missing outer helper adopts the journal with the route treated as closed only when its state directory is absent or a root-owned 0700 directory without `outer.json` (the harness covers an empty one and one holding the accepted receipt); a state directory holding `outer.json` (as a file, a dangling link or a directory), that is a symlink or not a directory, or that is unsafe (a foreign owner or a mode wider than private) refuses as `egress-outer-helper-missing` before adoption, with no status helper run, no compensation and the journal retained, and a contract assertion ties those paths to the runtime helper's own. The real egress quiesce and rollback behavior remains native and Molecule evidence.

**Protected frontend lifecycle has one owner** — rotation selects the canonical
Xray/Hysteria roles under staging and invokes their guarded activation once.
Changed units, configs and TLS authority retain validate/snapshot/rollback
ordering. Actual localhost publication plus handler flush cannot dispatch a
second frontend restart; native role scenarios retain final readiness proof.
AWG rotation source checks follow the complete firewall/role lifecycle. Actual
Ansible listener admission covers both callers, matching and missing/drifted
contracts, disabled/subscription selection and check mode before mutation.

Native normalizer recovery also retains live authenticated TCP and UDP controls when killing the process. Both accepted TCP tuples must enter TIME_WAIT before one immediate restart with the original readiness deadline; fresh public TCP/UDP and zero forbidden contacts remain required. Closed-probe recovery alone cannot establish listener rebinding under active traffic. UDP tuple quarantine and gateway generation reset retain their separate authority.

**Shared transport semantics use real boundaries** —
`test_transport_semantics.py` covers accepted inputs, typed malformed values,
ambiguous client-name refusal, routed versus device claims, key reuse, prefix
collisions, privacy and actual
localhost Ansible preflight in normal/check mode. `test_transport_semantics_native.py`
requires an isolated Linux root/TUN host, exact source-commit AWG ELF outputs,
pinned Xray with adjacent GeoIP and checksum-pinned Hysteria. It fails missing
prerequisites rather than skipping. Native synthetic credentials are valid
runtime keys/UUIDs; source placeholders cannot prove parser acceptance.

**Review regressions preserve first-use boundaries** — invalid CI configuration
publishes categorical results before deployment; blue-green waits for bootstrap
after pinning and refuses before recovery instructions when readiness fails.

**Disposable trust tests exercise real boundaries** — build and inspect a real
private ext4 seed and verify its SSH identity; the native lane mounts its loop
block device in a private mount namespace and runs the guest installer. The
native sentinel test starts a real pinned loopback SSH daemon, rejects an altered
pin and stops only its owned unit. These tests supplement orchestration and
mock-provider checks; they do not claim a provider deployment.

**Audit regressions use executable boundaries** — localhost Ansible tests exercise synthetic-key redaction, DNS and forwarding transitions, canonical Xray drift, and rollback validation/activation failures. Saved-plan tests replace the original after inspection and verify apply still uses the inspected private snapshot. These prove local behavior, not provider or guest acceptance. Construct time-sensitive lease inputs at test execution, so a long collection-to-execution delay cannot turn an overlong lease into a valid one.

**Subscription first check mode covers planned service boundaries** — evaluate
loaded, absent, unplanned and failed systemd discovery plus restart handlers.
Real role convergence and first-host dry-run remain separate acceptance gates.

**Packaged SSH ownership has positive and interruption coverage** — cloud-init
tests consume the exact password-disabled image fragment, verify idempotence,
reject altered content and unsafe files, restore it after validation failure,
and repeat after process death at its removal boundary.

**Bootstrap classification follows real producer boundaries** — inventory
  carries the Terraform build label separately from workspace identity.
  Regressions exercise named production selection, contradictory inventory,
  duplicate or missing guest markers, and the emitted private request contract.
  The permanent-workspace bootstrap regression runs the real inventory renderer
  with synthetic Terraform output, then consumes its INI through bootstrap's
  custom parser. Handwritten unquoted labels cannot cover that codec boundary.
  Inventory Base64 regressions wrap real encoder output with CRLF, inspect raw
  INI bytes and require exact payload decoding for listeners and topology.

**Bootstrap failure diagnostics exercise the real child process** — assert
that failed installer output reaches stderr, structured stdout stays empty,
and the ambient enrollment key never reaches the Ansible child or output.

**Recovery check mode covers services and timers separately** — evaluate the
role's guards with loaded units absent from service facts, planned and unplanned
missing units, and failed load-state discovery. These unit inputs supplement
real systemd and post-convergence staging checks.

**Coverage claims follow contracts** — `test_governance_counts.py` checks role
and template inventories plus hosted scenarios. Suite sizes come from runner
output for a specific revision; this test does not recollect the suite.

**Workspace discovery uses real Git histories** — `test_workspace_status.py`
exercises linked/detached worktrees, divergent and missing main refs, rename and
dirty counts with disabled/limited ambient rename detection, non-UTF-8 index paths,
quoted control characters, fsmonitor hook isolation and an unchanged index.
The sanitized Make entry bypasses inherited inputs and an invalid `.fleet.mk`;
task-pointer checks use the real `taskctl` portfolio API. A real blobless clone
with a recording upload-pack hook proves status cannot demand-fetch objects.
Active clean/process filters and child-submodule filters are refused before
execution; unused configured filters remain supported. Empty selected task IDs
fail instead of silently becoming an unspecified task.

**`ci-fast` is the portable pre-PR gate** — runs the credential-free required
CI checks, including workflow/YAML/shell lint, cloud-init schema, all Terraform
tests, pytest/bats, Go helper integration, and vpnd Python tests, lint/type
checks, baseline parity, packages and dependency policy. `make check` adds
Terraform fmt/validate, gitleaks, and ansible-lint. Native Linux runtime integration, Molecule, GitHub-native
security services, and credentialed deploy jobs remain CI-only or explicit.

**Snapshots, not mocks, for templates** — `tests/snapshot/golden/` holds
the expected output of every Jinja render against fixtures. Drift is
visible in PR diffs.

**Baseline parity outlives planning** — the vpnd transfer gate reads its
permanent package inventory. Test it without an active OpenSpec directory;
task archival must not remove executable regression obligations.
Role-render tests reuse `scripts/template_render.py` for named-template escaping
and Ansible filters. Local HTTPS fixtures explicitly require TLS 1.2 or newer.
HTML/XML names include their compound `.html.j2`/`.xml.j2` suffixes; markup
values escape, while embedded JSON remains parseable and script-safe. JSON,
shell, unit, nginx and explicitly named text fragments retain artifact quoting
and exact credential characters. Recovery conditions use the same environment
policy even though expression evaluation does not produce markup.

**Client configs need an upstream parser gate** — CI installs a sha256-pinned
official sing-box binary and checks the complete standard emitter output.
Shape-only assertions supplement this gate; they do not replace it.

**Xray CI consumers share one verified installer** — template and sentinel
validation use `.github/actions/install-xray`. Keep its version/archive hash
together and aligned with the example version. Verify before extracting or
executing; install the runtime and its bundled geodata together after its
version command succeeds. Template routing rules need the adjacent data files.

**Pytest groups use measured durations** — four `pytest-split` groups share a
committed Linux profile. Keep `pytest unit tests` as the required aggregate: it
checks identical collections/profiles, disjoint selections and full execution.
Refresh the profile from the verified artifact; local `test-unit` stays complete.
Give clock-dependent parameter values stable IDs so collection agrees across runners.

**Promotion proof covers aliased temp roots** — the controller's snapshots
must reach the evaluator through canonical private paths even when the OS
returns a symlinked temporary root.
Provider promotion tests include an instruction symlink and generated cache in
`terraform/shared`; they must be ignored while the required shared inputs stay
regular, pinned files. A non-default workspace test also checks that Terraform's
first directory setup cannot violate the private snapshot mode floor.
Public-listener verifier fixtures use literal source addresses or complete
named-set objects; a dangling `@set` reference is intentionally rejected.
Disposable de-onboarding tests also exercise a reissued cleanup manifest after
firewall promotion and reject a foreign server UUID before any local deletion.
Disposable de-onboarding fixtures use the current UpCloud schema-3 absence
receipt and reject an obsolete version before mutation. Its registry fixture
uses the installer's exact sorted JSON format.
Unbound-retirement fixtures must start with registered pre-destroy state and
then write different empty state. Exercise copied/inode-replaced authority,
unclaimed absence and post-destroy state replacement before SOPS publication.
Prepared-executor tests require a completed real client retirement transaction,
profile marker/configuration/context guards, assignment races and interrupted
stop/delete retry; fixture success remains source evidence only.
Exercise real SOPS retirement both with and without optional Snell collections;
an absent section is valid, while malformed or partial configured state refuses.

**Disposable observability acceptance is evidence-class strict** — focused
schema-2 tests cover co-hosted VPN capabilities, one collector, independent
Kuma placement, exact push-monitor bindings and rejection of old host classes.
PKI tests exercise real OpenSSL IP-SAN verification, scoped revocation and SOPS
encryption/decryption, including strict certificate-chain checks with explicit
key identifiers. Refresh the encrypted synthetic fixture whenever its plaintext
counterpart changes. Tests that isolate HOME need real SOPS on PATH, not a
version-manager shim whose trust state depends on the original home directory.
Real pinned Kuma runtime timing is separate from mocked
push or Telegram tests; no synthetic receipt proves human notification.
Sender replacement checks use the actual pinned vmagent parser and persistent
queue behavior. Clean and abrupt restart evidence must query pre-restart sample
timestamps at the collector; queue files, empty buffers and fresh samples alone
cannot pass. Byte/block drop counters are not interchangeable with sample counts.
Historical dedicated-host
selector tests prove staging-only enablement, disabled production, required
explicit secret scope, and mixed-scope refusal before Terraform or publication.
The old global boolean must fail, not become an implicit compatibility path.
Focused
unit tests keep the fixed staging row order, exact-host and private-file
boundaries, real one-hour critical reminder program, interruption restoration,
durable receipt reconciliation, human-observation gate, complete-set cleanup
plans, provider-specific absence and redacted terminal schemas separate. The
rollback tests distinguish retained last-known-good inputs from the active
candidate, and invalid-candidate credit requires an exact one-field mutation
plus the typed first role-guard failure; another Ansible failure is never
accepted. Typed-refusal capture tests enforce the fixed 64 KiB streaming cap,
redacted failure, deadline, and owned-process cleanup. Authenticated negative
ingestion probes require an explicit HTTP
status while only plaintext and missing-identity TLS probes accept transport
refusal. The
local input preparer is contract-locked to that row order and proves no-clobber
private roots, fail-closed draft approvals/bindings, schema-valid SOPS runtime
fragments, secure sticky-only writable ancestry, descriptor-bound refusal on
root substitution, and real OpenSSL certificate purposes without provider or
Telegram access. A
fixture executor or synthetic HTTP status is source evidence only; it never
marks a live Telegram or provider action complete.

**Molecule per role > monolithic test** — role-level scenarios catch
config drift inside a role. Full-stack catches order/handler interactions.
The two full-stack scenarios run on separate matrix runners with fail-fast
disabled; `required checks` requires both to succeed.
Tailnet role Molecule also asks the real `systemd-analyze` in a PID 1 container
to parse the complete recovery/SSH dependency graph and fails on diagnostics
even when `verify` returns zero. This is static graph evidence only: its inert
`tailscaled.service` fixture is not vendor-unit, activation, or reboot evidence.
Its native OpenSSH check hides `/run` in a private mount namespace, requires
the real `-T` runtime refusal, and compares complete cold `-G` policy with
the ordinary dump and warm `-T` output. Preparation must not create `/run/sshd`.

**CI Python tooling shares one cached setup** — `setup-ci-python` always checks
hash-pinned requirements, even on a pip cache hit. Galaxy consumers set the same
absolute `ANSIBLE_COLLECTIONS_PATH` as the action's isolated collection cache.
OS, architecture, Python and both requirements files determine its exact key.
The `python validators` job preserves seven checks behind one required context.
The native lane consumes this setup through `setup-disposable-ci`; cache
coverage follows that composite and includes its required Galaxy installation.

**CI selection follows complete consumers** — common Python/static checks always
run; costly PR lanes follow the selector's path graph. Docs are bundled into
Python vpnd. Keep Ansible scenarios together for cross-role inputs, and full CI for
main/manual/shared/unknown changes. The final gate requires every selected job
and permits only planned skips; adding a job must update the selector and tests.

**Cloud-init schema uses Ubuntu package sources only** — its installer selects
the runner's `ubuntu.sources` for both APT operations. An unrelated preinstalled
repository cannot block this gate. Missing Ubuntu sources and failed updates
remain fatal; package signatures and the real schema validator stay enforced.

Runtime acceptance has a separate canonical-role Linux lab. It uses exact checksum-pinned runtimes, generated dedicated client/TLS authority and an owned routed namespace canary. Credential mount propagation is established before creating namespace references, so parent bind mounts cannot hide those references at cleanup. Upgrade, retry, check mode, failure compensation and real process-death cases must retain actual authenticated traffic and fail selected skips. Portable inode/state tests complement that lab and never claim service or client acceptance. The operator runtime rollback case asserts frontend and generation-selected gateway unit text, accepted claims and native `/proc/<MainPID>/exe` identity. A real gateway sandbox refusal and SIGKILL after gateway publication or adoption must restore all exact original unit inodes and authenticated forwarding. A following ordinary converge with the newer pin restores the whole generation and retains the rolled-back release as `previous`. Portable tests cover direct-only and paired gateway candidate selection, validated topology refusal and the sole publication lane. The isolated native lab exercises its selected direct gateway; this is not vendor tunnel or production acceptance. Native retirement follows the re-converged receipt. First-adoption interruption failures retain only bounded task/frame categories, the last static task and owned publication-state booleans for diagnosis. Keep the real interruption predicate and deadline intact.

## What's done well

- **Cloud-init encoding crosses the real Terraform boundary** — scalar tests
  run Terraform templatefile and YAML parsing for ordinary, punctuation, multiline
  and Unicode inputs, then compare the fixed CI renderer's parsed result. Legacy
  XHTTP tests select legacy mode explicitly and verify the previous port disappears.
  Null bootstrap strings remain refused. Native serialization functions are
  explicitly registered in the exact executable-coverage assertion.

- **Provider identity tests retain real mock state** — native lifecycle tests
  include positive unchanged plans; the subprocess harness shares legacy/current
  state, asserts safe attachment forgetting and exact identity refusal, including
  first adoption. `make tf-test` runs that harness explicitly; no synthetic
  provider result is live resource or guest proof. Policy tests execute real
  Conftest, while operator gate tests cover private snapshot reuse and cleanup.

- **Skill decisions have held-out scenarios** — `tests/fixtures/skill-evaluation-cases.json` contains requests, observed-input facts and separate assessment criteria. Independent evaluation receives only requests/facts and the skills; integrity tests do not stand in for observed behavior or live evidence. Private intent preparation tests execute real local publication and Make expression boundaries using synthetic inputs, without opening credentials or contacting providers.

- **Provider example parity is checked** — every explicit staging/prod listener
  example includes the default nginx HTTP redirect, so a copied environment
  reaches the same fail-closed runtime contract as the provider roots.

- **Contract-named tests** — `test_xhttp_endpoint_contract.py` rejects old
  trailing-slash paths and origin disagreement; its native companion exercises
  the admitted endpoints rather than asserting renderer text alone.
- **`snapshot-update` is explicit** — never updates on assertion failure;
  requires an operator running `make snapshot-update` after an intentional
  template change. CI never auto-updates.
- **`shellcheck` in CI** — every `.sh` file. Warnings break the build.

**Native acceptance fixture authority** — Runtime acceptance tests use actual checksum-pinned clients, owned TLS peers and Linux systemd/network namespaces. Real SIGKILL tests run the publisher in a separate process and require authenticated positive forwarding after recovery. Canonical role fixtures keep only source inputs from the render fixture; computed runtime paths and numeric identity projections must not override real role discovery.

AWG reconnect fixtures restore the same tunnel identities and both default routes after Linux link-down removes IPv6 addresses and routes. Server-compensation probes preserve the original client session and allow the pinned protocol's 15-second handshake recovery plus TCP retransmission within one bounded socket invocation.
Constrained-path acceptance observes the initial connection and three subsequent
reconnects for every member and both families.
Revocation keeps the original IPv4 and IPv6 UDP sockets open across claim removal
and key removal, requiring positive echoes first and no datagram delivery afterward.

Read-only sender admission is also executed through actual Ansible argv/stdin templating. Sender queue regression tests perform real private-file copies and in-place restoration across interruption checkpoints and partial cleanup; they assert historical bytes, original root inode, no-follow authority, exact backup identities and fail-before-mutation admission. Service mocks are portable orchestration evidence only. The enabled native Molecule scenario requires the exact historical nonce and pre-cutover timestamp to reach the authenticated receiver after an actual rejected candidate.

Authenticated topology acceptance runs exact Xray and Hysteria clients against an owned HTTPS canary in a disconnected namespace. Wrong password, SAN, CA and obfuscation never substitute listener readiness for traffic. XHTTP observes both frontend paths and preserves the nginx PID through backend loss. Warm AWG acceptance republishes the pinned ELF to a new inode and runs actual role notifications/handlers; it observes the new process and unit sandbox, then requires unchanged convergence to preserve the PID. Source acquisition remains the native builder's separate responsibility.
Warm AWG fixtures stage the exact tools and quick script outside the source checkout before unit activation. CI source trees live under `/home`, which the production unit hides through `ProtectHome=yes`; preserve that sandbox during acceptance.

## Pitfalls

- Ubuntu Molecule consumers use one immutable digest from the repository-owned,
  security-gated publication. Refresh every consumer and pin regression together;
  never waive fixable HIGH or CRITICAL image findings.

- **Selected skips fail required pytest lanes** — portable tests use
  `make test-unit` (both `tests/unit/` and `scripts/tests/`);
  `native_runtime` tests run separately with pinned
  Terraform/Alertmanager and UID/GID capabilities on a disposable Linux runner.
  Both use `--fail-on-skip`. Never run the full workstation suite as root.
- **Compiled helper coverage is real Go execution** — `ci-fast` includes
  `make test-probe-matrix-mtproto`; Python driver tests cannot replace it.

- **Release SBOM is the locked Python inventory** — CI and publication share
  `.github/actions/vpnd-sbom`, which stages `dist/sbom.json`. The deployment
  example emitter serves `make emit-sbom` and is not the vpnd release SBOM.

- **Mutation CI distinguishes findings from execution failure** — only exit
  0 (caught) and 2 (survivors reported) are successful runs. The runtime tests
  exercise actual workflow shell error propagation and disposable-copy cleanup;
  real mutmut baseline and mutation execution remain the acceptance gate.

- **Snapshot files are committed** — never gitignore `tests/snapshot/golden/`.
  PR diff is the review surface.
- **Molecule needs Docker** — CI runners and operator workstations vary.
  Failing-to-find-docker is a setup error, not a test failure; the harness
  surfaces it explicitly.
- **State-changing test calls precede assertions** — capture retirement or
  retry results first, then assert them so optimized Python cannot omit the call.
- **Recovery readiness observes periodic work** — exercise successful completion
  of the same invocation, failure, contention, timeout, and identity changes.
  Waiting never starts a replacement worker or accepts cached success.
  Exercise apply activation through the real baseline planner and adapter as
  well: observing a current worker must precede the fresh proof, and both
  phases consume one deadline. Fixtures are not native systemd acceptance.
- **Cold Tailnet recovery has one readiness budget** — cover `NoState` and
  `Starting` before owned logout and after it, exhaustion and late replies,
  invalid status, reinitialization during identity verification, foreign
  identity and strict non-recovery callers. A fake
  monotonic clock proves bounds; the actual vendor cold boot remains staging
  acceptance, independent of these domain tests.
- **`validate-secrets.py` runs against the **schema**, not your real
  secrets** — by design. Strict mode (`--strict`) loads `VPN_SECRETS_FILE`
  and is operator-only.
- **Don't snapshot the diff of binaries** — QR PNGs, restic repos, etc.
  Snapshot the inputs, render the binary fresh, hash-assert if needed.

- Legacy bootstrap kernel tests use a disposable root-owned directory under
  `/var/lib` and a private network namespace. Their service fixture does not
  establish PID1, identity, Tailnet, or live client acceptance.

- Sentinel onboarding tests cover standalone XHTTP, REALITY, Hysteria2, AWG-only
  and mixed format selection. An unsupported unused emitter refuses in the
  fixture; required emitter failures must precede remote writes. These tests
  are orchestration evidence, not live authentication.

Native P2 check-mode coverage executes the complete enabled agent role against
valid generated TLS authority in fresh and retained namespaces. It compares the
owned filesystem before/after and performs no runtime download or activation;
ordinary Molecule/native runtime acceptance remains separate. The private
receiver snapshot CLI regression restores every mutable authority file and the
prior service-state record without rewinding replay or incident state.

Release-publication fixtures must explicitly chmod directories to the tested
contract after mkdir: the shared build gate uses a restrictive umask, so
mkdir's requested 0755 alone cannot establish the helper's ownership boundary.
Task-source readers follow enabled task files and recursively inspect real
publication blocks; dispatcher files cannot prove mutation or activation order.

The shared Molecule transport canary serves HTTPS with an exact numeric SAN and
container-local trust. Full-stack watchdog validation keeps requiring HTTPS;
standalone rollback fixtures prepare canonical consumer recovery before `begin`.
Portable publisher and validation-lease tests use private user-owned temporary
ancestry; Linux `/tmp` is deliberately outside the production authority contract.
Numeric canary startup bypasses reverse DNS inside its disconnected namespace.
Complete consumer transactions run in a pinned fresh systemd container on a
separate native runner, retaining refusal of foreign runtime and firewall
authority from the runner host or other fixtures.

The native policy lifecycle fixture requires a root-owned executable parent
without group/world write permissions. A disposable runner may start with
0777, so the fixture saves the mode, establishes trusted ancestry and restores
it in cleanup. Production retirement validation keeps rejecting unsafe ancestry.

Alerting regressions cross operator payloads into the real relay parser and renderer, and match exact send receipts. Lost canary responses and interrupted receipt writes must leave freshness absent while the next attempted sequence advances. A pinned real Prometheus receiver checks reordered queue batches without relaxing historical sample assertions.

Client drift tests exercise real test-only SOPS/age documents and the shared
in-memory renderer, including consumed and unrelated edits, exact canonical
delivery, refresh expiry, lost/rotated/malformed authority, unsafe file types,
and encryption-failure preservation. Endpoint lookup and remote publication
are isolated, so this evidence does not claim live fleet delivery. Copied
emitter fixtures must include the Python renderer and its shared dependencies
and explicitly establish private source modes.

Delivery failures exercise actual isolated writes before failed acknowledgements,
local replacement/sync failure and interruption, including unchanged refresh.
Require reconciliation diagnostics after external mutation starts; preflight
refusal retains the ordinary error and the prior encrypted authority.
The canonical delivered bundle must validate against the published dual-stack
schema. Real encrypted drift cases change each address family and MTU; missing
families, scalar claims and out-of-range MTU stay unknown without publication.

REALITY identity/deadline regressions use real local CA certificates, TLS/HTTP
sockets and stalled process trees. Monitor state/alert fixtures inject categorical
collector observations; they do not claim network proof. The dedicated REALITY
native lane additionally runs the exact checksum-pinned browser-shaped client
and an owned service through its explicit ingress address. Its complete Make
target fails on skips and missing client prerequisites.

The REALITY collector no longer parses shell TLS transcripts. Its large-certificate
regression completes a real trusted handshake beyond ordinary pipe-buffer sizes;
metadata failure classification remains covered by the shared monitor tests.

Bulk four-transport probes supply the canonical driver socket timeout explicitly;
they retain its three-second default while expanding byte payloads.

The required four-transport CI matrix runs core coverage and two complete,
disjoint compensation partitions in independent owned containers. Each phase
retains its 40-minute bound; the local default executes their complete union.
A real collection regression rejects gaps and overlaps as native cases expand.

The four-transport runner reuses canonical runtime, endpoint, device binding
and source-pair labs. Keep selected native cases complete: overrides, empty
JUnit, skips and resource identity differences fail. Publish only case names,
results, source/engine hashes and cleanup status; raw pytest logs stay private.
Create diagnostic siblings exclusively and set permissions on the open descriptor;
existing files and symlinks belong to other work and must remain intact.

Copied native CI source trees must be root-owned before admission. A Git
`safe.directory` exception for the top-level checkout does not admit its nested
pinned AWG source clones; preserve normal ownership checks instead.

A nested native lab that creates namespaces for systemd must join its root
network namespace with `nsenter --net`. `ip netns exec` also isolates mounts,
so the manager cannot open nested namespace handles created by that process.

The complete native lane checks resource retirement after every case and suite.
Its explicit pytest flag enables OS inventory only in that isolated lane;
portable checks retain their ordinary fixture behavior. Evidence exposes only
changed resource categories and counts, with private identities kept local.
