from dataclasses import asdict
import json
import sys
from ..state import Host, Registry


async def run(ctx, args):
    registry = Registry.load()
    if args.action == "list":
        if args.json:
            print(
                json.dumps(
                    [dict(name=name, **asdict(host)) for name, host in registry.hosts.items()],
                    separators=(",", ":"),
                )
            )
        elif not registry.hosts:
            print(
                "(no hosts registered — run `vpnd host add <name> --env … --provider …`)",
                file=sys.stderr,
            )
        else:
            print("name | env | provider | ipv4 | ipv6 | deployed_with")
            for name, host in registry.hosts.items():
                print(" | ".join([name] + [str(v or "") for v in asdict(host).values()]))
    elif args.action == "show":
        record = registry.get(args.name)
        if record is None:
            raise ValueError(f"no such host: {args.name}")
        print(
            json.dumps(
                asdict(record),
                indent=None if args.json else 2,
                separators=(",", ":") if args.json else None,
            )
        )
    elif args.action == "add":
        if ctx.explain:
            print(f"would add '{args.name}' to the local host registry", file=sys.stderr)
            return
        registry.upsert(args.name, Host(args.host_env, args.host_provider, args.ipv4, args.ipv6))
        registry.save()
        print(f"✓ added '{args.name}'", file=sys.stderr)
    else:
        if registry.get(args.name) is None:
            raise ValueError(f"no such host: {args.name}")
        if ctx.explain:
            print(f"would remove '{args.name}' from the local host registry", file=sys.stderr)
            return
        registry.remove(args.name)
        registry.save()
        print(f"✓ removed '{args.name}'", file=sys.stderr)
