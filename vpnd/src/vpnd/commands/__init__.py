"""Shared command safety contracts."""

import sys
from ..runner.make import target
from ..wizard import confirm

__all__ = ["confirm", "finish_with_cleanup", "ensure_host_in_registry", "render_summary", "require_review"]


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


def require_review(ctx, label):
    """Gate a mutation on a reviewed plan; --yes never answers this prompt."""
    if not ctx.explain and not confirm(label, default=False):
        raise RuntimeError("review declined; stopped before mutation")


def ensure_host_in_registry(ctx, registry, host):
    if host is not None:
        registry.resolve_for(host, ctx.env, ctx.provider)


def render_summary(title, entries):
    print(title, file=sys.stderr)
    for key, value in entries:
        print(f"  {key}: {value}", file=sys.stderr)
