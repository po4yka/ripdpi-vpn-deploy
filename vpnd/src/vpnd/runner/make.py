"""All Make values pass per-key expansion-safe allowlists before spawn."""

import ipaddress
import re
import unicodedata
from .process import Cmd


def validate_kv(key, value):
    value = str(value)
    if key == "HOST":
        rule = "IPv4 literal"
        try:
            ipaddress.IPv4Address(value)
            valid = True
        except ipaddress.AddressValueError:
            valid = False
    elif key in {"MATRIX_CONFIG", "PLAN"}:
        rule = "absolute path [A-Za-z0-9._/-] without .. components"
        valid = (
            value.startswith("/")
            and bool(re.fullmatch(r"[A-Za-z0-9._/-]+", value))
            and ".." not in value.split("/")
        )
    elif key == "SECRETS_FILE":
        rule = "runtime path without make, shell metacharacters, or whitespace"
        valid = value.startswith("/") and all(
            not c.isspace() and unicodedata.category(c) != "Cc" and c not in "$`\"';|&<>()\\#"
            for c in value
        )
    else:
        rule = "identifier [A-Za-z0-9._-]"
        valid = bool(re.fullmatch(r"[A-Za-z0-9._-]+", value))
    if not valid:
        rendered = "(redacted)" if key == "SECRETS_FILE" else repr(value)
        raise ValueError(
            f"refusing to spawn make: variable {key} value {rendered} fails the {rule} rule — make expands command-line variable values inside recipe shells"
        )


def target(ctx, name):
    secrets = str(ctx.secrets_file)
    for key, value in (("ENV", ctx.env), ("PROVIDER", ctx.provider), ("SECRETS_FILE", secrets)):
        validate_kv(key, value)
    return (
        Cmd.new("make")
        # Each invocation is an independent operator transaction. Inherited
        # recursion flags add directory banners to structured stdout; other
        # Make controls can inject files, flags or parent command variables.
        .env_remove("MAKELEVEL", "MAKEFLAGS", "MAKEFILES", "MFLAGS", "GNUMAKEFLAGS")
        .args([name, f"ENV={ctx.env}", f"PROVIDER={ctx.provider}", f"SECRETS_FILE={secrets}"])
        .sensitive(secrets)
        .sensitive(str(ctx.sops_file))
        .cwd(ctx.root)
        .describe(f"make {name} ENV={ctx.env} PROVIDER={ctx.provider}")
    )


def target_with(ctx, name, kvs):
    if isinstance(kvs, dict):
        kvs = list(kvs.items())
    for key, value in kvs:
        validate_kv(key, value)
    return target(ctx, name).args([f"{k}={v}" for k, v in kvs])
