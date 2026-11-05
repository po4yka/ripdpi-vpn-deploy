# Runbook — add a fallback VPS

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-11-04

## Purpose and scope

Add an explicitly approved hot spare or another transport failure domain. The service already supports a split fleet: P0 REALITY, P1 XHTTP and P2 UDP can run on separate hosts. See the dated [deployment snapshot](../reference/deployment-status.md) for the accepted fleet. An additional host is not required to use the existing TCP reserves.

## Preconditions

- A working primary path and a measured reason for another endpoint.
- An exact provider/environment, resource plan, cost limit and cleanup plan.
- Separate scoped secrets for the new host and separate device credentials. A different address does not isolate credentials copied from the primary.
- The selected [deployment profile](../reference/deploy-profiles.md), explicit public listener contract and matching Terraform inputs.
- A compatible client and a plan to deliver its new per-device profile.

## Authorization

Every target that uses cloud credentials, inventory, SSH or decrypted secrets needs authorization for the selected environment and exact target. Review the plan before mutation. A new resource needs an explicit cost bound; existing-node deployment approval does not authorize it. Follow the [decision boundaries](../../AGENTS.md#decision-boundaries).

## Steps

1. Select the required failure domain and role. A same-provider spare supports replacement. Another provider can reduce a shared provider failure. A TCP endpoint can cover UDP-path failure; another port on the same address does not cover address-wide blocking.
2. Prepare the separate provider environment and scoped SOPS authority through the [quickstart](../tutorials/quickstart.md). Review its Terraform plan before apply. Preserve active environment state and encrypted recovery copies.
3. Complete [fresh-node recovery and enrollment](tailnet-management.md) before ordinary runtime deployment. Verify the exact SSH identity and host pins.
4. Select explicit cohorts in the private fleet configuration, then render inventory through the [profile guide](../reference/deploy-profiles.md#how-to-use). The reusable split profiles are `vpn-p0-minimal`, `vpn-p1-web` and `vpn-p2-udp`. Do not edit the shared playbook or run a bare Ansible command to bypass the canonical controller.
5. Run the reviewed [deployment transaction](deploy.md#ordinary-re-deploy-recipe) for the new exact alias. Review the dry-run before deploy. Stop on failed verification; retain the accepted primary configuration.
6. Use the [device lifecycle](device-lifecycle.md) to prepare and deliver a fresh per-device artifact across the selected hosts. Review the candidate set before publishing it. Keep unique device authority and the recovery path.
7. Choose the client selection contract. Ordinary sing-box `urltest` uses HEAD/latency; it does not verify useful payload bytes. For the paired RIPDPI selector, explicitly configure the [payload policy](../reference/ripdpi-bundle.md#ripdpipayload_failover), accept its two owned HTTPS controls and install the compatible client first.

The paired client checks TCP reserves first after active Hysteria2 payload failure under that policy. Recovery requires verified bytes, thresholds and cooldown. All-candidate failure retains the last encrypted selection. AmneziaWG is outside this selector pool. A merged feature or reachable alternate alone does not prove automatic failover on a recipient device.

## Verification

Require exact-source verification, security/smoke results and authenticated traffic plus tunnel DNS through the new endpoint. Test primary failure and recovery on the intended client under a separately approved fault scope. Record candidate choice, payload proof and recovery timing. A successful alternate does not establish that the primary recovered. Do not interrupt the primary merely to complete this documentation procedure.

## Rollback

Restore the previous accepted recipient profile through the canonical device workflow. Retain the new host and encrypted recovery material until the rollback passes. Resource destruction is a separate approved delete-only plan; follow [the rollback runbook](rollback.md). If the fallback was exposed and held copied primary authority, destroying it does not revoke that authority. Rotate the affected credentials using [rotation](rotate.md).

## Evidence to record

Record the approved target and cost scope, role and failure domain, exact source, reviewed plan, host admission, deployment receipts, device delivery and observed failover/recovery. Keep endpoints, device identifiers and raw diagnostics in the private kit. Keep server reachability and device acceptance separate.
