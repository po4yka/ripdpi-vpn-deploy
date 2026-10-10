from ..runner.make import target, target_with


def rotation_target(ctx, plan, resume, dry_run):
    plan = plan.resolve(strict=True)
    kvs = [("PLAN", str(plan))]
    if resume:
        kvs.append(("RESUME", "1"))
    if dry_run:
        kvs.append(("DRY_RUN", "1"))
    return target_with(ctx, "fleet-rotate", kvs)


async def run(ctx, args):
    command = (
        rotation_target(ctx, args.plan, args.resume, args.dry_run)
        if args.action == "rotate"
        else target(ctx, "fleet-status" if args.action == "status" else "drift-since-tag")
    )
    await command.run(ctx.explain)
