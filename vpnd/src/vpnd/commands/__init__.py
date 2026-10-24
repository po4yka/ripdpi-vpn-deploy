"""Shared command safety contracts."""

import asyncio
import signal
import sys
from ..runner.make import target
from ..wizard import confirm, confirm_async

__all__ = [
    "confirm",
    "finish_with_cleanup",
    "ensure_host_in_registry",
    "render_summary",
    "require_review",
    "StopSignals",
]


async def finish_with_cleanup(ctx, outcome=None):
    # Shield the retained cleanup task. Later cancellation must not detach it
    # or replace a failure from the pipeline.
    cleanup_task = asyncio.create_task(target(ctx, "clean").run(ctx.explain))
    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as cancelled:
            if outcome is None:
                outcome = cancelled
        except Exception:
            break
    try:
        cleanup_task.result()
    except Exception as cleanup:
        if outcome is None:
            raise
        print(f"warn: cleanup also failed: {cleanup}", file=sys.stderr)
    if outcome is not None:
        print("error: pipeline failed — attempted secrets cleanup (make clean)", file=sys.stderr)
        raise outcome


# Terminal interrupts, a dropped session and service stops all end the review.
REVIEW_SIGNALS = (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP)


class OperationInterrupted(RuntimeError):
    """A signal stopped a pipeline while decrypted secrets could exist."""

    def __init__(self, number: int, step_error=None):
        detail = "" if step_error is None else f"; the step reported: {step_error}"
        super().__init__(f"interrupted by signal {number}; stopped before the next step{detail}")
        self.exit_code = 128 + number


class StopSignals:
    """Turn REVIEW_SIGNALS into a stop at the next pipeline step boundary.

    Dispatch keeps default terminal signals, which would end vpnd before its
    cleanup boundary. While active, the event loop only records the first
    signal. vpnd does not kill the running Make step: terminal signals reach
    it directly, and a killed Make could leave a child that writes plaintext
    after `make clean`. Run cleanup through `cleanup` so it stays guarded.

    An ignored signal (for example SIGHUP under nohup) stays ignored: a caught
    signal resets to the default action in every Make child, so guarding it
    would let a lost session kill a running apply.
    """

    def __init__(self):
        self.received = None
        self._previous = {}
        self._stopped = asyncio.Event()

    def __enter__(self):
        loop = asyncio.get_running_loop()
        for number in REVIEW_SIGNALS:
            previous = signal.getsignal(number)
            if previous == signal.SIG_IGN:
                continue
            loop.add_signal_handler(number, self._record, number)
            self._previous[number] = previous
        return self

    def __exit__(self, *_exc):
        loop = asyncio.get_running_loop()
        while self._previous:
            number, previous = self._previous.popitem()
            loop.remove_signal_handler(number)
            signal.signal(number, previous)

    def _record(self, number):
        if self.received is None:
            self.received = number
            self._stopped.set()

    async def wait(self):
        await self._stopped.wait()

    def check(self):
        if self.received is not None:
            raise OperationInterrupted(self.received)

    def outcome(self, error):
        """Report a recorded signal in place of the step failure it caused."""
        if isinstance(error, asyncio.CancelledError):
            return error
        if self.received is not None and getattr(error, "exit_code", None) is None:
            interrupted = OperationInterrupted(self.received, error)
            interrupted.__cause__ = error
            return interrupted
        return error

    async def cleanup(self, ctx, error):
        """Run `make clean` under the guard and report a signal it received."""
        try:
            await finish_with_cleanup(ctx, error)
        except Exception as failure:
            mapped = self.outcome(failure)
            if mapped is failure:
                raise
            raise mapped from failure
        self.check()


async def require_review(ctx, label, stop):
    """Gate mutation on terminal approval, with recorded signals taking priority."""
    if ctx.explain:
        return
    stop.check()
    answer = asyncio.create_task(confirm_async(label, default=False))
    interrupted = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait((answer, interrupted), return_when=asyncio.FIRST_COMPLETED)
        stop.check()
        if not answer.result():
            raise RuntimeError("review declined; stopped before mutation")
    finally:
        primary = sys.exception()
        for task in (answer, interrupted):
            if not task.done():
                task.cancel()
        # Retain both waits through repeated caller cancellation. The reader's
        # synchronous finalizer releases its descriptor before cleanup starts.
        waits = asyncio.gather(answer, interrupted, return_exceptions=True)
        cancellation = None
        while not waits.done():
            try:
                await asyncio.shield(waits)
            except asyncio.CancelledError as error:
                cancellation = error
        if cancellation is not None and primary is None:
            raise cancellation
    stop.check()


def ensure_host_in_registry(ctx, registry, host):
    if host is not None:
        registry.resolve_for(host, ctx.env, ctx.provider)


def render_summary(title, entries):
    print(title, file=sys.stderr)
    for key, value in entries:
        print(f"  {key}: {value}", file=sys.stderr)
