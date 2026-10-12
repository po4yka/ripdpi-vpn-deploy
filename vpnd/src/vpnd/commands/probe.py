import sys
from ..runner import Cmd
from ..runner.make import target, target_with
from ..state import Registry, ipv4_limit


async def run(ctx, args):
    registry = Registry.load()
    address = (
        ipv4_limit(args.host, registry.resolve_for(args.host, ctx.env, ctx.provider))
        if args.host is not None
        else None
    )
    steps: list[Cmd] = []
    if args.profile in {"p0", "all"}:
        if address is not None:
            print("note: validate-target and tspu-canary check configured external targets; they are not host-specific", file=sys.stderr)
        steps.extend(
            target(ctx, name) for name in ("validate-target", "probing-summary", "tspu-canary")
        )
    if args.profile in {"p1", "all"}:
        if address is not None:
            steps.append(target_with(ctx, "test-tls-policing", [("HOST", address)]))
        else:
            print("note: skipping P1 TLS policing test — needs --host", file=sys.stderr)
    if args.profile in {"p2", "all"}:
        steps.extend(target(ctx, name) for name in ("burn-check", "asn-drift"))
    for command in steps:
        if address is not None and command.argv[0] in {"probing-summary", "burn-check", "asn-drift"}:
            command.env("IP", address)
        await command.run(ctx.explain)
