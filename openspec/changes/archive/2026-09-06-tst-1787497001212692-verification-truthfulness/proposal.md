# Change: Make verification reflect deployed state

Task ID: `TST-1787497001212692`

## Why

Verification drifts from what deploy actually produces: verify.yml and smoke-test.yml are unusable on subscription-only hosts because transport assertions ignore the subscription-only skip contract; source-drift never compares the deployed source revision it already loads; the Hysteria listener check hardcodes UDP/443 while fallback listeners deployed and firewall-opened by the same play are never asserted at all. The molecule layer has the same honesty gap: the full-stack scenarios — the repo's key integration tests — omit the idempotence phase that the repo declares contractual, the xray scenario omits it without documentation, the amneziawg scenario renders templates by hand instead of executing role tasks so regressions there are invisible, and docs/TESTING.md misstates what several scenarios run while omitting reality-self-steal entirely.

## What Changes

- Transport assertions in verify.yml and every smoke-test block gain `not vpn_subscription_only` gating, mirroring existing sibling conditions.
- source-drift adds the missing revision equality to its parity assert.
- The Hysteria UDP check parameterizes on `hysteria_port`; conditional listener assertions are added for both deployed fallback ports.
- Full-stack and full-stack-published test sequences include an idempotence phase.
- The xray scenario gains an idempotence phase and stops rewriting the public runtime symlink with a fixture file on every converge.
- The amneziawg converge runs the actual role (include_role) against explicitly synthetic local source/build fixtures and no-TUN tools instead of re-implementing the render or preinstalling role outputs.
- TESTING.md matrix rows match observed sequences; reality-self-steal joins the matrix.
- A post-converge assertion verifies exactly one SSH listener exists per host (socket/service reconciliation guard).

## Capabilities

### New Capabilities

- `testing/verification-truthfulness`: Observable contract that verification tooling asserts the state deploy produced for every supported host class, that idempotence is actually tested where declared, that scenario descriptions match reality, and that first-boot listen-surface guarantees are machine-checked.

### Modified Capabilities

- None

## Impact

- ansible/playbooks/verify.yml, smoke-test.yml, source-drift.yml.
- ansible/molecule/{full-stack,full-stack-published}, roles/{xray,amneziawg}/molecule, docs/TESTING.md.
- No production runtime behavior changes; gates may newly fail where they previously lied.
