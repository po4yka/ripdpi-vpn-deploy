from ..runner.make import target


def required_steps(ctx, skip_certs):
    return [
        target(ctx, name)
        for name in ["validate-secrets", "spot-check-secrets", "audit-permissions"]
        + ([] if skip_certs else ["check-certs"])
    ]


async def run(ctx, args):
    if not ctx.secrets_file.is_file():
        await target(ctx, "decrypt").run(ctx.explain)
        ctx.secure_secrets_file()
    for command in required_steps(ctx, args.skip_certs):
        await command.run(ctx.explain)
