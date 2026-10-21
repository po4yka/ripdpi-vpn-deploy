"""Shared command safety contracts."""

import asyncio
import signal
import sys
from ..runner.make import target
from ..wizard import confirm

__all__ = [
    "confirm",
    "finish_with_cleanup",
    "ensure_host_in_registry",
    "render_summary",
    "require_review",
    "StopSignals",
]


async def finish_with_cleanup(ctx, outcome=None):
    try:
        await target(ctx, "clean").run(ctx.explain)
    except Exception as cleanup:
        if outcome is None:
            raise
        print(f"warn: cleanup also failed: {cleanup}", file=sys.stderr)
    if outcome is not None:
        print("error: pipeline failed — attempted secrets cleanup (make clean)", file=sys.stderr)
        raise outcome


class ReviewInterrupted(RuntimeError):
    """A signal ended the review while decrypted secrets existed."""

    def __init__(self, number: int):
        super().__init__(f"review interrupted by signal {number}; stopped before mutation")
        self.exit_code = 128 + number


def _interrupt_review(number, _frame):
    raise ReviewInterrupted(number)


# Terminal interrupts, a dropped session and service stops all end the review.
REVIEW_SIGNALS = (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP)


class OperationInterrupted(RuntimeError):
    """A signal stopped a pipeline while decrypted secrets could exist."""

    def __init__(self, number: int):
        super().__init__(f"interrupted by signal {number}; stopped before the next step")
        self.exit_code = 128 + number


class StopSignals:
    """Turn REVIEW_SIGNALS into a stop at the next pipeline step boundary.

    Dispatch keeps default terminal signals, which would end vpnd before its
    cleanup boundary. While active, the event loop only records the first
    signal. vpnd does not kill the running Make step: terminal signals reach
    it directly, and a killed Make could leave a child that writes plaintext
    after `make clean`. Keep the guard active through cleanup.
    """

    def __init__(self):
        self.received = None
        self._installed = []

    def __enter__(self):
        loop = asyncio.get_running_loop()
        for number in REVIEW_SIGNALS:
            loop.add_signal_handler(number, self._record, number)
            self._installed.append(number)
        return self

    def __exit__(self, *_exc):
        loop = asyncio.get_running_loop()
        while self._installed:
            loop.remove_signal_handler(self._installed.pop())

    def _record(self, number):
        if self.received is None:
            self.received = number

    def check(self):
        if self.received is not None:
            raise OperationInterrupted(self.received)

    def outcome(self, error):
        """Report a recorded signal in place of the step failure it caused."""
        if self.received is not None and getattr(error, "exit_code", None) is None:
            return OperationInterrupted(self.received)
        return error


def require_review(ctx, label):
    """Gate a mutation on a reviewed plan; --yes never answers this prompt.

    Dispatch keeps default terminal signals, which would kill the process with
    plaintext on disk. During the review a signal becomes an ordinary failure,
    so the caller's cleanup boundary still runs `make clean`.
    """
    if ctx.explain:
        return
    previous = {number: signal.signal(number, _interrupt_review) for number in REVIEW_SIGNALS}
    try:
        approved = confirm(label, default=False)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    if not approved:
        raise RuntimeError("review declined; stopped before mutation")


def ensure_host_in_registry(ctx, registry, host):
    if host is not None:
        registry.resolve_for(host, ctx.env, ctx.provider)


def render_summary(title, entries):
    print(title, file=sys.stderr)
    for key, value in entries:
        print(f"  {key}: {value}", file=sys.stderr)
