from .process import Cmd


def decrypt(ctx):
    return (
        Cmd.new("sops")
        .args(["--decrypt", "--output", ctx.secrets_file, ctx.sops_file])
        .sensitive(ctx.secrets_file)
        .sensitive(ctx.sops_file)
        .describe("sops --decrypt → (runtime plaintext — never logged)")
    )
