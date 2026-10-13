# operations/observability-alerting-reliability Specification

## Purpose
Make bounded alert delivery, producer freshness, desired coverage and observer backup recovery truthful at the actual runtime boundaries.
## Requirements
### Requirement: REQ-ALERT-URL — Accept actual bounded alert URLs

The relay MUST accept the generated URLs of current Prometheus rules within its bounded webhook request, without rendering those URLs or following them.

#### Scenario: Long expression fires or resolves

- **WHEN** a current long-expression alert produces a generator URL above 256 characters
- **THEN** the authenticated bounded webhook is accepted for both firing and resolved delivery and the URL does not appear in Telegram output.

### Requirement: REQ-ALERT-RESPONSE — Bound actual Telegram Message responses

The relay MUST allow successful Message responses for every accepted rendered message, including multibyte text and JSON encoding overhead, while retaining a finite response byte ceiling and categorical diagnostics.

#### Scenario: Near-limit notification is acknowledged

- **WHEN** an accepted grouped message returns a valid success response larger than 4096 bytes
- **THEN** delivery succeeds once; an oversized response beyond the reviewed ceiling still fails.

### Requirement: REQ-WATCHDOG-PRIVATE — Consume canonical private producer state

The health adapter MUST consume owner-private 0600 watchdog state from the actual producer and retain its ownership, ancestry and link checks.

#### Scenario: Normal write and mode migration

- **WHEN** the watchdog writes a fresh normal state or migrates an existing accepted legacy budget
- **THEN** the resulting private state yields the actual failure/recovery evidence without a collection error; unsafe authority still refuses.

### Requirement: REQ-EVIDENCE-TYPED — Replace malformed scalar evidence

The health adapter MUST classify list/object backup results and restore source identities as malformed evidence and publish bounded failure metrics over previous success.

#### Scenario: Nested scalar arrives after success

- **WHEN** a formerly healthy producer publishes a list or object in a scalar result or source field
- **THEN** no traceback or source values escape and previous successful evidence is replaced by collection failure.

### Requirement: REQ-EVIDENCE-EXPIRY — Expire producer evidence centrally

Central evaluation MUST use bounded producer/completion timestamps rather than fresh scrape timestamps to detect expired, absent or future evidence. Repeated scrapes of a frozen successful textfile MUST NOT prolong its validity.

#### Scenario: Adapter stops while exporter continues

- **WHEN** an adapter stops or cannot publish and its previous successful metrics continue arriving
- **THEN** evaluation reports evidence unavailable after the reviewed producer-specific deadline; fresh valid recovery resolves the incident.

### Requirement: REQ-TARGET-PRESENCE — Match expected targets to actual families

Expected-target presence MUST be derived from the reviewed required producer families or a genuinely installed adaptation, without assuming unscheduled generic evidence-state output.

#### Scenario: Actual healthy target is observed

- **WHEN** all required families from a real health adapter arrive for an enabled node and role
- **THEN** no target-missing incident fires; required-family disappearance and never-started targets remain detectable.

### Requirement: REQ-UNIT-PRESENCE — Detect absent required service evidence

Evaluation MUST detect absent required node/unit pairs independently of other healthy units, respecting declared profile expectations and distinguishing absent evidence from an observed service failure.

#### Scenario: One required unit disappears

- **WHEN** one declared required unit is absent while another is active
- **THEN** a bounded missing-service-evidence incident fires; intentionally excluded units do not alert and complete recovery resolves the incident.

### Requirement: REQ-OBSERVER-RECOVERY — Restore after interrupted backups

Observer backup lifecycle MUST retain the prior running state and restore it after stop errors, graceful termination or deadline/forced termination, with durable recovery and serialized disable/rotation ordering. Backup failures MUST NOT fabricate backup success.

#### Scenario: Interrupted quiesced backup

- **WHEN** the actual backup helper fails or is terminated after stopping a previously active observer
- **THEN** lifecycle recovery restores the observer; disabling or rotating waits for backup recovery before its own final service action and a previously inactive observer stays inactive.

#### Scenario: Intent publication is interrupted before observer stop

- **WHEN** writing, flushing, syncing or publishing the recovery intent fails before the observer-stop boundary
- **THEN** the observer remains running and no partial canonical marker poisons recovery or the next locked backup. A fully published marker remains recoverable if directory syncing fails; retained intent is never overwritten.

### Requirement: REQ-SOURCE-VALIDATION — Preserve source-only acceptance bounds

Regression and role validation MUST exercise the real changed producer/consumer behavior with synthetic credentials and disposable runtimes. Source/CI proof MUST remain separate from deployment and human receipt.

#### Scenario: Repair PR is prepared

- **WHEN** all local checks and source review complete
- **THEN** the PR records exact-source check results and remaining hosted/runtime gaps, without a deployment, real Telegram send or claim of live acceptance.

### Requirement: REQ-CANARY-ACK — Recover after ambiguous edits

The relay MUST reserve each delivery-canary attempt sequence durably before upstream work. It MUST publish edit freshness only after a valid successful edit response. A lost acknowledgement or process restart MUST NOT cause the next attempt to repeat accepted text.

#### Scenario: Accepted edit loses its acknowledgement

- **WHEN** Telegram accepts an edit but the response or final receipt write is lost
- **THEN** the next attempt uses different text and can recover without waiting for a new daily send; failed attempts do not prove freshness.

### Requirement: REQ-OPERATOR-DRILL — Verify the complete drill path

Operator drills MUST supply the current relay payload contract and distinguish submission from confirmed API delivery. They MUST resolve only after a bounded delivery observation for their exact drill, and MUST fail when the relay rejects or cannot deliver it.

#### Scenario: Synthetic drill passes or fails delivery

- **WHEN** a scoped drill is submitted through the authenticated gateway
- **THEN** current node, evidence and source fields reach the relay; a confirmed API send permits resolution and a rejected or failed send cannot produce a successful drill result.

### Requirement: REQ-QUEUE-ORDER — Accept bounded reordered queue replay

The collector MUST accept reordered remote-write samples within its configured seven-day window relative to the global TSDB maximum timestamp. It MUST preserve original timestamps and labels, reject samples outside the finite window, and keep private authentication and resource bounds. This is not a wall-clock queue-age guarantee; rejected HTTP batches MUST remain observable as delivery loss. The isolated one-hour collector MUST use a matching one-hour policy. Small receiver regressions MUST NOT replace measured late-history replay resource admission before rollout.

#### Scenario: An unsent worker block is replayed after newer samples

- **WHEN** the pinned sender restores an older mixed-series batch after a newer batch
- **THEN** the collector accepts in-window historical samples and their exact identity is observable; out-of-window samples still fail.
