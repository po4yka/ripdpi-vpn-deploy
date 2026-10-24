import asyncio
import sys
from ..runner import ansible
from ..runner.make import target
from ..state import Registry
from ..state.version import warn_on_skew
from . import StopSignals, confirm_async, render_summary, require_review


async def run(ctx, args):
    print(
        "Reconverge\nIdempotent re-deploy against an existing host. Bundles decrypt → plan → dry-run → apply if drifted.",
        file=sys.stderr,
    )
    host = None
    if args.host is not None:
        record = Registry.load().resolve_for(args.host, ctx.env, ctx.provider)
        warn_on_skew(args.host, record)
        host = (args.host, record)
    limit = await ansible.scoped_limit(ctx, host)
    render_summary(
        "Reconverge plan",
        [
            ("env", ctx.env),
            ("provider", ctx.provider),
            ("host", args.host or "(all in env)"),
            ("mode", "dry-run only" if args.dry_run else "apply if changed"),
        ],
    )
    if not ctx.yes and not ctx.explain and not await confirm_async("Proceed?"):
        print("aborted by user", file=sys.stderr)
        return
    error = None
    with StopSignals() as stop:
        try:
            await target(ctx, "decrypt").run(ctx.explain)
            stop.check()
            ctx.secure_secrets_file()
            for name in ("init", "plan"):
                await target(ctx, name).run(ctx.explain)
                stop.check()
            await target(ctx, "dry-run").env("ANSIBLE_LIMIT", limit).run(ctx.explain)
            stop.check()
            if args.dry_run:
                print("dry-run only — stopping before apply", file=sys.stderr)
            else:
                await require_review(ctx, "Review the dry-run above. Deploy it?", stop)
                stop.check()
                for name in ("deploy", "verify"):
                    await target(ctx, name).env("ANSIBLE_LIMIT", limit).run(ctx.explain)
                    stop.check()
        except (Exception, asyncio.CancelledError) as outcome:
            error = stop.outcome(outcome)
        await stop.cleanup(ctx, error)
    if not ctx.explain:
        print("\nReconverge complete.")
