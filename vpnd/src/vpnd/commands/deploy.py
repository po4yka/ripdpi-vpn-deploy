"""Deploy delegates the canonical ordered Make pipeline."""

import sys
from ..runner.make import target, target_with
from . import confirm, finish_with_cleanup, render_summary


def plan_steps(ctx, args):
    steps = [
        target(ctx, name)
        for name in (
            "check-prereqs",
            "validate",
            "decrypt",
            "init",
            "plan",
            "apply",
            "inventory",
            "wait",
        )
    ]
    steps.append(
        target_with(ctx, "deploy", [("SKIP_PRECHECK", "1")])
        if args.skip_precheck
        else target(ctx, "deploy")
    )
    steps.append(
        target_with(ctx, "verify", [("TAG_ON_SUCCESS", "1")])
        if args.tag_on_success
        else target(ctx, "verify")
    )
    return steps + [target(ctx, "smoke-test")]


def build_plan_summary(ctx, args):
    return [
        ("env", ctx.env),
        ("provider", ctx.provider),
        ("repo", "<checkout root>"),
        ("sops file", "(sops-managed store)"),
        ("secrets file", "(runtime plaintext — never logged)"),
        ("skip precheck", "yes" if args.skip_precheck else "no"),
        ("tag on success", "yes" if args.tag_on_success else "no"),
    ]


async def run(ctx, args):
    print(
        "Deploy wizard\nBundles: validate → decrypt → plan → apply → inventory → wait → preflight → site → verify.",
        file=sys.stderr,
    )
    render_summary("Deploy plan", build_plan_summary(ctx, args))
    if not ctx.yes and not ctx.explain and not confirm("Proceed with these settings?"):
        print("aborted by user", file=sys.stderr)
        return
    steps = plan_steps(ctx, args)
    error = None
    try:
        for cmd in steps:
            await cmd.run(ctx.explain)
    except Exception as outcome:
        error = outcome
    await finish_with_cleanup(ctx, error)
    if not ctx.explain:
        print(
            f"\nDeploy complete.\n\n  active profiles:  P0 REALITY, P1 nginx-xhttp, P2 hysteria + amneziawg (per group_vars)\n  env:              {ctx.env}\n  provider:         {ctx.provider}\n\n  next:\n    share a client: vpnd share <name> --qr\n    diagnose: vpnd doctor\n    re-deploy: vpnd reconverge\n\n  runbooks: docs/RUNBOOK-deploy.md, docs/RUNBOOK-rollback.md, docs/RUNBOOK-incident.md"
        )
