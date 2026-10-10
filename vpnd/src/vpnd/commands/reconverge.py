import sys
from ..runner import ansible
from ..runner.make import target
from ..state import Registry
from ..state.version import warn_on_skew
from . import confirm, finish_with_cleanup, render_summary


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
    if not ctx.yes and not ctx.explain and not confirm("Proceed?"):
        print("aborted by user", file=sys.stderr)
        return
    error = None
    try:
        await target(ctx, "decrypt").run(ctx.explain)
        ctx.secure_secrets_file()
        for name in ("init", "plan"):
            await target(ctx, name).run(ctx.explain)
        await target(ctx, "dry-run").env("ANSIBLE_LIMIT", limit).run(ctx.explain)
        if args.dry_run:
            print("dry-run only — stopping before apply", file=sys.stderr)
        else:
            for name in ("deploy", "verify"):
                await target(ctx, name).env("ANSIBLE_LIMIT", limit).run(ctx.explain)
    except Exception as outcome:
        error = outcome
    await finish_with_cleanup(ctx, error)
    if not ctx.explain:
        print("\nReconverge complete.")
