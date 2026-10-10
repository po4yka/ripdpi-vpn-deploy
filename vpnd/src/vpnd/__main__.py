"""CLI dispatch; parse errors happen before context or external invocation."""

import asyncio
import importlib
import signal
import sys
from .cli import parse_args
from .config import Context


async def execute(args):
    module = importlib.import_module(".commands." + args.command.replace("-", "_"), package="vpnd")
    if args.command == "completions":
        result = module.run(args)
        if hasattr(result, "__await__"):
            await result
        return
    if args.command == "update" and args.explain:
        print(
            "# vpnd update would query:\n  GET https://api.github.com/repos/po4yka/ripdpi-vpn-deploy/releases/latest"
        )
        return
    ctx = Context.discover(args)
    await module.run(ctx, args)


async def dispatch(args):
    if args.command != "doctor":
        await execute(args)
        return 0
    loop = asyncio.get_running_loop()
    interrupted = loop.create_future()

    def signal_seen(sig: int) -> None:
        if not interrupted.done():
            interrupted.set_result(128 + sig)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_seen, sig)
    task = asyncio.create_task(execute(args))
    try:
        done, _ = await asyncio.wait((task, interrupted), return_when=asyncio.FIRST_COMPLETED)
        if interrupted in done:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return interrupted.result()
        await task
        return 0
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        if not interrupted.done():
            interrupted.cancel()


def main(argv=None):
    args = parse_args(argv)
    # Interactive dispatch keeps the kernel's terminal signal behavior,
    # including while synchronous token reads and confirmations block.
    previous = {}
    if args.command not in {"doctor", "probe-matrix"}:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, signal.SIG_DFL)
    try:
        return asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        code = getattr(error, "exit_code", None)
        return code() if callable(code) else code if isinstance(code, int) else 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
