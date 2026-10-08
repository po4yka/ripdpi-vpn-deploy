# Exploration examples

Use the example matching the entry point; these are illustrations, not a script.
They authorize no code, artifact or infrastructure writes.

## Vague idea

User: "I'm thinking about improving reachability diagnostics."

Read the relevant current code and contracts, then distinguish questions that
could lead to different designs: local node health, an authenticated client path,
or an independent observer. Compare evidence each could provide and identify
the unresolved requirement. Offer to capture a proposal once the user chooses.

## Concrete failure

User: "The configuration flow is difficult to follow."

Trace the current input-to-validation-to-consumer path. Show the actual
integration points and identify where the contract or ownership becomes unclear.
Recommend an option with its cost and benefit, grounded in what the code does.
A diagnosis alone ends with findings; it does not authorize the fix.

## Implementation obstacle

User: "$openspec-explore <change> — this integration is more complex than expected."

Resolve status and read the current artifact paths. Compare the planned behavior
with the newly discovered constraint. Identify which requirement, design decision
or execution step would change. If the user requests artifact updates, use
`$openspec-update-change`; if they explicitly request a fix, complete validated
planning and resume through `$openspec-apply-change` within that request's bounds.

## Comparing approaches

User: "Should this state live in a file or a database?"

Establish the actual constraints, such as concurrency, atomicity, recovery and
query needs, then compare the approaches against those constraints. A small
comparison table is useful when the tradeoffs are parallel. If the recommendation
depends on an unknown, say which fact would change it and inspect that fact when
possible.

## Optional close

A useful short close names the problem, the supported approach and remaining
unknowns. Offer capture when it would help; if capture or implementation is
already requested, perform the relevant handoff instead of offering it again.
