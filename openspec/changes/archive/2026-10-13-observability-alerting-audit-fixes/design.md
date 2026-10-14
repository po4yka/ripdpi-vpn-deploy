## Context

The source audit identified boundary defects in the active existing-host monitoring implementation. This change repairs source behavior; resource admission, replacement-agent acceptance, real alert drills and human receipt remain owned by the existing rollout task.

## Goals / Non-Goals

- Goal: current bounded alerts and actual producer evidence pass their consumers; absent, frozen and malformed evidence stays observable.
- Goal: restore a previously active independent observer after an interrupted backup without restarting an intentionally disabled observer.
- Non-goal: deployment, provider or inventory access, real notification traffic, transport changes, new dependencies, credentials or listeners.

## Decisions

- Bound webhook requests as a whole; accept string generator URLs inside that bound and never render/fetch/log them. Separate the message character ceiling from a finite 64 KiB returned-Message byte ceiling.
- Read the canonical owner-private watchdog budget. Validate scalar JSON types before membership checks so malformed inputs publish categorical failure over old success.
- Keep producer timestamps in the bounded metric contract and compare them to central evaluation time. Frozen exposition is not fresh evidence merely because the exporter still works; absent/future timestamps fail closed. Completion freshness is independent of the underlying backup/restore cadence.
- Evaluate expected presence against the actual reviewed required families. A configured but unscheduled generic state renderer cannot establish runtime coverage. Keep per-family absence detection and distinguish it from confirmed failure.
- Render declared required node/unit expectations with the effective node profile and compare every pair to observed systemd data; another active unit cannot hide a missing required unit. Do not infer desired services solely from currently discovered units.
- Fully write and fsync restart intent in an owner-private same-directory staging file, then atomically publish it and fsync the directory before observer stop inside the cleanup boundary. Interrupted staging never becomes canonical intent; retained canonical intent is never overwritten under the lifecycle lock. Graceful termination enters restoration; systemd ExecStopPost calls a credential-independent recovery action under the same lifecycle lock to cover forced death and timeout. Remove intent only after successful restoration. A new backup resolves retained intent before quiescing again.
- Reserve each canary attempt sequence durably while revoking prior edit freshness; failed attempts may leave gaps, but only confirmed edits publish freshness.
- Operator drills use the verified controller source generation, supply required node and evidence annotations, and poll a bounded receipt keyed to that exact drill before resolution. No real notification is part of source validation.
- Accept reordered remote-write samples within the configured seven-day collector window relative to the global TSDB maximum timestamp, not wall-clock queue age. The pinned sender can append an unsent worker block after later queue blocks on stop. Preserve exact timestamps, labels, private authentication and resource bounds; out-of-window HTTP discards remain delivery loss and the disposable one-hour collector uses the matching finite policy. Small receiver tests do not establish measured late-history replay resource admission.
- Preserve timer-stop, backup-stop/recovery, then final observer lifecycle ordering for disable and rotation. Recovery has bounded shutdown time sufficient for its existing bounded service start.
- Repair confirmed local-gate boundaries without weakening production checks: owned temporary roots use the expected process group; real Ansible fixtures isolate controller paths and bound the complete transaction. Passive pipe collection retries transient backpressure within its existing deadline and byte limits. Process-group cleanup retries a permission failure only after reaping an exited child and still refuses a live child or repeated failure.

## Contracts and ownership

- Delivery worker owns relay implementation/tests, observer backup helper, units, lifecycle fixtures/tests and observer role notes.
- Monitoring worker owns agent evidence parsing, freshness/metric contract, expected-target and service coverage, their producer/consumer tasks/templates and focused tests, plus agent role notes.
- Primary owns task/OpenSpec files, collector role notes, operator documentation, shared snapshots, validation, review, commit and PR. Shared snapshots and task state are serialized after worker source changes.
- No Terraform, cloud-init, vpnd, secrets schema or credential issuance changes are intended. Any necessary metric-contract change updates all in-repository validators/consumers; no compatibility shim.

## Risks / Trade-offs

- Central deadlines differ by evidence source; real producer-output rule tests cover aging, absent/future evidence and valid recovery rather than fabricating generic healthy states.
- Required-unit expectations must exclude intentionally disabled profile services; partial and complete evidence loss receive distinct bounded coverage outcomes.
- Backup recovery failure retains intent for explicit inspection; deadline/termination tests execute the actual helper, preserving existing least-privilege units and serialization.
- Local and disposable Linux results cannot prove VPN non-regression, deployed timing or human notification receipt.

## Migration Plan

Deliver one source-only PR with focused regressions, reviewed snapshots, affected-role Molecule scenarios, the full credential-free make check gate and independent security review. The deployment hold remains. Any future authorized convergence updates matching producer, metric and evaluator contracts together; rollback restores their previous source/configuration generation as one reviewed change. No retained monitoring data or credentials are removed by this PR.
