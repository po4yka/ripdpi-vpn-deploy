from .process import Cmd


def base(ctx):
    return (
        Cmd.new(ctx.root / "scripts/terraform-env.sh")
        .env("PROVIDER", ctx.provider)
        .env("ENV", ctx.env)
    )


def init(ctx):
    return base(ctx).arg("init").describe(f"terraform init for {ctx.provider}/{ctx.env}")


def plan(ctx):
    return (
        base(ctx)
        .args(["plan", f"-var-file=environments/{ctx.env}.tfvars", f"-out={ctx.env}.tfplan"])
        .describe(f"terraform plan -out={ctx.env}.tfplan")
    )


def apply(ctx):
    return (
        base(ctx).args(["apply", f"{ctx.env}.tfplan"]).describe(f"terraform apply {ctx.env}.tfplan")
    )


def output(ctx):
    return base(ctx).args(["output", "-json"]).describe("terraform output -json")
