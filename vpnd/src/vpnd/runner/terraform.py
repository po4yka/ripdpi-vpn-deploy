from pathlib import Path
import os

from .process import Cmd


def base(ctx):
    return (
        Cmd.new(ctx.root / "scripts/terraform-env.sh")
        .env("PROVIDER", ctx.provider)
        .env("ENV", ctx.env)
    )


def init(ctx):
    return base(ctx).arg("init").describe(f"tofu init for {ctx.provider}/{ctx.env}")


def plan(ctx):
    external = os.environ.get("TFVARS_ROOT")
    if external and not Path(external).is_absolute():
        raise ValueError("TFVARS_ROOT must be an absolute path")
    directory = Path(external) / ctx.provider if external else Path("environments")
    tfvars = directory / f"{ctx.env}.tfvars"
    return (
        base(ctx)
        .args(["plan", f"-var-file={tfvars}", f"-out={ctx.env}.tfplan"])
        .describe(f"tofu plan -out={ctx.env}.tfplan")
    )


def apply(ctx):
    return (
        base(ctx).args(["apply", f"{ctx.env}.tfplan"]).describe(f"tofu apply {ctx.env}.tfplan")
    )


def output(ctx):
    return base(ctx).args(["output", "-json"]).describe("tofu output -json")
