---
task_id: MON-1790650904289505
change: staging-observability-telegram-acceptance
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: "Two-vantage authenticated VPN-profile proof is an explicit non-goal; the canary is telemetry source evidence, not client-path acceptance."
artifact: required
artifact_evidence: null
---

# Verification

This document starts as an evidence plan. A result changes to `passed` only
after the named command or observation has run against the exact recorded
protected-main revision. Source tests, fixtures, API responses, and component
status are never promoted to human Telegram receipt or external VPN evidence.
Archive is forbidden while any required category or mapped requirement remains
`required`, `blocked`, or failed.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-STG-OBS-ENABLEMENT | MON-1790793779569506 | Staging positive inventory and strict secrets; disabled production; malformed and mixed-scope refusal before provider access | required |
| REQ-STG-OBS-TOPOLOGY | MON-1790651217409733 | Reviewed UpCloud/Hetzner/Scaleway plans; three exact host classes and failure domains; cross-provider dead-man; topology/listener contracts; no public admin | required |
| REQ-STG-OBS-BOOTSTRAP | MON-1790652096462210 | Focused bootstrap/firewall tests and exact-host baseline, updates, guest firewall, loopback monitoring, and source-manifest convergence before component deployment | required |
| REQ-STG-OBS-PRIVATE-INPUTS | MON-1790651216954415 | Descriptor-bound private-root preparation and materialization; generated SSH, age, PKI and SOPS authorities; private-chat topic sentinel; non-sticky ancestor, symlink and path-substitution refusal | required |
| REQ-STG-OBS-AUTHORIZATION | MON-1790651216954415 | Private per-action approvals bind exact target, action, restore, deadline, cancellation, window, BotFather revocation, and post-evidence destructive-data authority | required |
| REQ-STG-OBS-OPERATOR | MON-1790652096934376 | Focused fail-before-mutation, staging-only, timeout/interruption, restore, receipt, redaction, central-query, critical-drill, fault, canary, and revocation-negative tests | required |
| REQ-STG-OBS-SOURCE | MON-1790651217861152 | Installed control-plane, dead-man, and canary source/generation digests matched to `commit_sha` | required |
| REQ-STG-OBS-CLEANUP | MON-1790652346357417 | UpCloud/Hetzner/Scaleway immutable account/state manifests covering every Terraform address and addressable provider identity, exact complete-set delete-only plan tests, provider-specific absence, and capability retirement | required |
| REQ-STG-OBS-METRICS | MON-1790651218327983 | Two advancing canary collection/write intervals; valid write accepted; wrong identity, path, method, plaintext, query, and admin requests rejected | required |
| REQ-STG-OBS-PRIMARY | MON-1790651218798773 | Categorical relay/API receipts plus owner-observed primary firing/reminder/resolved; `MON-1790652098418969` separately proves secondary detection and fresh-canary recovery of primary authority loss | required |
| REQ-STG-OBS-DEADMAN | MON-1790651219261781 | Secondary firing/reminder, replay/future/expired/invalid refusal, and fresh-pulse recovery; `MON-1790652097417200` separately proves control service and provider host/network loss | required |
| REQ-STG-OBS-FAILURE | MON-1790652097417200 | Separate control service and host/network rows meet bounds; `MON-1790652097923534` proves dead-man service loss and `MON-1790652098418969` proves primary authority loss; all restore baseline | required |
| REQ-STG-OBS-ROTATION | MON-1790651219743990 | Candidates work before revocation; authorized BotFather revocation; old-token checker records rejection; `still-valid` exits non-success, retains recovery material, and blocks rotation/cleanup | required |
| REQ-STG-OBS-ROLLBACK | MON-1790651220194212 | Invalid candidate pre-mutation refusal; digest-bound private manifest; exact prior control-plane generation, authority state, schedules, and retained storage restored | required |
| REQ-STG-OBS-EVIDENCE | MON-1790651221104630 | Redacted exact-SHA reconciliation; TSDB-preserving removal; rollback-window closure; exact destructive-data approval; guarded destroy/provider absence; local/hosted gates; explicit full-matrix/fleet/client/cutover exclusions | required |

## Evidence capture contract

Record only:

- exact Git revision and deployable or installed generation digests;
- technical host-role and failure-domain aliases;
- UTC start/end timestamps and bounded categorical results;
- metric family names with advancing timestamps, without label values that
  identify endpoints, users, or credentials;
- service and timer active/enabled categories and schedule counts;
- provider resource type plus present/absent category, never addresses or raw
  state;
- owner confirmation that each expected Telegram lifecycle message was visible
  in the intended private destination, without message body or destination ID.

Never record SOPS plaintext, PEM material, tokens, chat/topic identifiers,
provider credentials, public or Tailnet addresses, private inventory, raw
Terraform state, request/response bodies, process environments, or secret-
derived hashes.

## Planned category gates

### Local

- `./taskctl openspec cli validate
  staging-observability-telegram-acceptance --type change --strict
  --no-interactive`
- `./taskctl generate-board` and `./taskctl validate`
- targeted bootstrap, firewall, observability contract/operator, Telegram,
  dead-man, receipt, timeout, interruption, and redaction suites
- `build-gate -- make check` for the final repository revision

### Remote CI

- all required pull-request checks terminal green for the final candidate;
- `ci`, CodeQL, Scorecard, and release workflow terminal green for the exact
  protected-main revision used by staging;
- no queued, skipped-required, superseded, or unrelated SHA credited.

### Dry-run

- UpCloud, Hetzner, and Scaleway `ENV=staging` plans reviewed before apply;
- inventory/topology validation with one VPN canary, one control plane, one
  dead-man, distinct failure domains, and two declared sentinel signatures;
- `observability-validate` and `observability-render` for each exact host with
  private mode-0600 vars/secrets and strict known-hosts;
- exact-host baseline/firewall check mode and provider/guest listener parity
  with no public admin or query surface.

### Staging

- exact-host deployment in dependency order;
- healthy component status plus fresh advancing canary metrics;
- serial component/Telegram rows, including distinct control service,
  control host/network, dead-man service, and primary authority loss, with
  baseline restoration after each row;
- serial credential rotations and exact last-known-good rollback;
- TSDB-preserving component removal, explicit rollback-window closure,
  separately approved exact-resource destruction, and provider absence.

### Live

- owner visibly observes primary firing, one-hour reminder, and resolved;
- owner visibly observes independent secondary control-plane-loss, one-hour
  reminder, and stable recovery;
- owner observes primary dead-man-service loss/recovery and secondary primary-
  authority-loss/recovery through their independent routes;
- API success, local receipt, or screenshot text copied into Git is not used as
  a substitute.

### Client

Not applicable to this change. REALITY, XHTTP, Hysteria2, and AmneziaWG
two-vantage authenticated traffic remains a separate portfolio step.

### Artifact

- redacted verification maps every requirement to its execution step and exact
  observed evidence;
- cleanup receipts prove approval-bound exact resources and independent absence
  while omitting provider identifiers and capabilities;
- final handoff states that the remaining two-vantage protocol-liveness row,
  full staging matrix, fleet rollout, and production paging cutover remain
  unaccepted.
