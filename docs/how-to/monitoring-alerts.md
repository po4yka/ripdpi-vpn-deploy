# Runbook — monitoring alerts

> **Status:** Current · **Type:** how-to · **Tier:** CORE

## Purpose and scope

Find what a primary Telegram alert means and what to check first. Each alert links to the section below that has the name of its `incident_family`. For loss of service, use the [incident matrix](incident.md#decision-matrix).

## Authorization

Commands that use inventory, SSH or decrypted secrets need authorization for this environment and node before they run ([decision boundaries](../../AGENTS.md#decision-boundaries)). An alert does not supply this authorization.

## Alert families

### observability-pipeline

Synthetic rule-to-relay freshness receipt. It proves that rule evaluation reaches the relay.

First check: No action. This is the synthetic delivery canary.

### observability-external-coverage

An independent heartbeat producer stopped reporting success. The VPN can be healthy, but no independent signal shows it.

First check: Open the private Kuma panel and find the monitor that is down. VPN state is unknown until coverage returns.

### observability-delivery-loss

The sender or the collector relay discarded telemetry. Monitoring history has a gap for this period.

First check: Run make observability-status. Check the sender queue and collector disk. History has a gap for this period.

### node-cpu

Sustained CPU use is above the warning ratio.

First check: Find the top process on the node. If a VPN service is the cause and load stays high, move clients or add capacity.

### node-memory

Available memory is below the warning ratio.

First check: Find the largest process on the node. Low memory can cause out-of-memory kills of VPN services.

### node-swap

Swap use is above the warning ratio for the hold period.

First check: Find the process that uses the memory. Sustained swap use slows tunnels.

### node-disk

Free space on the root filesystem is below a threshold. At the critical threshold, services can fail to write.

First check: Free space on the root filesystem. Check the journal, the metrics queue and old releases.

### node-inodes

Free inodes on the root filesystem are below a threshold.

First check: Find the directory with the most files on the root filesystem and remove stale files.

### required-service

Fresh telemetry shows that a service required by the node profile is not active.

First check: Read systemctl status and the journal for the named service. If the fault stays, redeploy or replace the node.

### required-service-evidence

A service required by the node profile has no systemd evidence. Its health is unknown.

First check: Service health is unknown. Run make verify for this node, then check the node exporter systemd collector.

### node-clock

The node wall clock differs from the control-plane evaluation time. Clock skew breaks TLS and alert freshness.

First check: Check time synchronization on the node with timedatectl.

### certificate-expiry

A managed certificate is inside its expiry warning or critical window.

First check: Renew the certificate named by role. Use make check-certs for transport certificates and make observability-rotate for observability-sender.

### certificate-health

The certificate expiry collector failed, so expiry data is not current.

First check: Expiry data is missing. Read the journal of observability-agent-health-adapter.service on this node.

### node-network

A network interface reports sustained receive or transmit errors.

First check: Check interface counters on the node. If errors continue, contact the provider or replace the node.

### node-filesystem

The root filesystem is read only. This usually shows a disk fault.

First check: Do not repair in place. Replace the node with the recreation procedure.

### service-restart-loop

The watchdog made its hourly limit of restarts on this node. The count covers all services and all attempts, including successful ones.

First check: Read the watchdog journal on the node to see which services restarted and why.

### detector-health

A detector failed to collect data or stopped updating its results.

First check: Find which detector metric failed, then read the journal of that unit on the node.

### detector-input

Detector input advances, but no line matches a known policy event. The log format can have changed.

First check: Read the policy-ratelimit journal on the node and check for a log format change after a release.

### detector-error

A detector reports input errors.

First check: Find which detector metric reports errors, then read the journal of that unit on the node.

### detector-events

A security or reachability detector crossed its event threshold.

First check: For probing events run make probing-summary with IP of this node. For burn failures run make burn-check. Then use the incident matrix.

### producer-evidence

A node or collector adapter has not published valid evidence. Monitoring health is unknown for this source.

First check: Monitoring data is unknown here. Run make observability-status and check the agent units on the node.

### watchdog-evidence

Watchdog results are missing or stale.

First check: Check the watchdog timer and journal on the node.

### watchdog-recovery

The local watchdog tried recovery, and the service is still unhealthy.

First check: Run make verify for this node, then decide to repair or replace it.

### backup-evidence

Backup results are missing or stale.

First check: Check the backup timer and journal on the node.

Recovery from a backup is in the [restore runbook](restore.md).

### backup-stage

A stage of the backup job reported failure.

First check: Read the backup unit journal on the node and repair the failed stage before the next run.

Recovery from a backup is in the [restore runbook](restore.md).

### restore-readiness

The isolated restore drill result is stale, so restore readiness is not proven.

First check: Check the restore drill timer and journal on the node.

Recovery from a backup is in the [restore runbook](restore.md).

### expected-target-family

A required metric family is absent for an expected target.

First check: Run make observability-status. Check that the agent on this target publishes the named family.

### expected-target-absence

An expected target publishes none of its required metric families.

First check: The target sends no data. Check its agent and its private path to the collector.

### target-evidence-freshness

Evidence from an expected target stopped updating.

First check: Check the agent and adapter timers on this target.

### source-identity

The node manifest reports a source revision or deployable digest that differs from the expected candidate. A rollout causes this until every node has the new revision.

First check: Expected during a rollout. If it persists after the deploy, run make verify for this node.

### control-plane-health

Control-plane capacity or the expected-target pipeline is unhealthy.

First check: Run make observability-status. Check collector disk use and the expected-target adapter.
