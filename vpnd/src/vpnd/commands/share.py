"""Issue an opaque-token recipient handoff without exposing bearer URLs."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from vpnd.text import trim_whitespace
from vpnd.pages import qr, recipient
from vpnd.protected_file import open_private, write_private
from vpnd.runner import make
from vpnd.secrets import Secrets


@dataclass
class SubUrls:
    subscription_url: str
    singbox_deeplink: str
    qr_singbox: str
    qr_uri: str


def urlencode(value):
    # Match percent_encoding NON_ALPHANUMERIC, including punctuation urllib preserves.
    return "".join(
        chr(b) if (48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122) else f"%{b:02X}"
        for b in value.encode("utf-8")
    )


def build_sub_urls(base, segment):
    url = f"{base}/sub/{segment}"
    return SubUrls(
        url, "sing-box://import-remote-profile?url=" + urlencode(url + ".json"), url + ".json", url
    )


def validate_token(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError(
            "token must be non-empty and contain only base64url alphabet [A-Za-z0-9_-]"
        )


def load_token_file(path):
    with open_private(path) as handle:
        return handle.read().decode("utf-8")


def read_token(args):
    if args.token_stdin:
        token = sys.stdin.read()
        source = "stdin"
    elif args.token_file:
        token = load_token_file(args.token_file)
        source = "token file"
    else:
        raise ValueError("provide --token-stdin or --token-file")
    token = trim_whitespace(token)
    try:
        validate_token(token)
    except ValueError as error:
        raise ValueError(f"invalid token from {source}: {error}") from error
    return token


def per_platform_apps():
    return [
        recipient.AppCard(
            "iOS",
            recipient.Link("Streisand", "https://apps.apple.com/app/streisand/id6450534064"),
            [recipient.Link("v2RayTun", "https://apps.apple.com/app/v2raytun/id6476628951")],
        ),
        recipient.AppCard(
            "Android",
            recipient.Link("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest"),
            [recipient.Link("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest")],
        ),
        recipient.AppCard(
            "macOS / Windows / Linux",
            recipient.Link(
                "sing-box", "https://sing-box.sagernet.org/installation/package-manager/"
            ),
            [recipient.Link("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest")],
        ),
    ]


async def run(ctx, args):
    if not ctx.secrets_file.is_file():
        await make.target(ctx, "decrypt").run(ctx.explain)
        if not ctx.explain:
            ctx.secure_secrets_file()
    if ctx.explain:
        print("→ would emit: sing-box bundle, recipient page, QR (if --qr)", file=sys.stderr)
        return 0
    secrets = Secrets.load(ctx.secrets_file)
    client = secrets.find_client(args.client)
    if client is None:
        raise ValueError(f"client '{args.client}' not found in the decrypted secrets file")
    sub_host = secrets.subscription_host()
    fallback = secrets.nginx_xhttp.server_name
    sub_host = sub_host if sub_host and trim_whitespace(sub_host) else fallback
    if not sub_host or not trim_whitespace(sub_host):
        raise ValueError("missing subscription.server_name or nginx_xhttp.server_name in secrets")
    host = fallback if fallback and trim_whitespace(fallback) else sub_host
    token = read_token(args)
    port = secrets.subscription_port()
    base = f"https://{sub_host}" + (f":{port}" if port is not None and port != 443 else "")
    urls = build_sub_urls(base, token)
    singbox = await make.target_with(ctx, "emit-singbox", [("CLIENT", args.client)]).capture(False)
    out = Path(args.out) if args.out else ctx.root / "share" / args.client
    deep = "ripdpi://import?sub=" + urlencode(urls.subscription_url)
    page = recipient.render(
        recipient.RecipientCtx(
            client.name,
            host,
            ctx.env,
            ctx.provider,
            urls.subscription_url,
            urls.singbox_deeplink,
            deep,
            per_platform_apps(),
        )
    )

    def emit():
        out.mkdir(parents=True, exist_ok=True, mode=0o700)
        out.chmod(0o700)
        write_private(out / "config.singbox.json", singbox.stdout.encode())
        write_private(out / "index.html", page.encode())
        if args.qr:
            qr.write_svg(urls.qr_uri if args.type == "uri" else urls.qr_singbox, out / "qr.svg")
            qr.write_svg(deep, out / "qr-ripdpi.svg")

    await asyncio.to_thread(emit)
    print(
        f"\nshare bundle: {out}\n  recipient URL:  written only into the protected bundle\n  landing page:   {out / 'index.html'}"
    )
    if args.qr:
        print(f"  QR (svg):       {out / 'qr.svg'}")
    print("\n  Hand the recipient the URL — it has the QR, deep link, and per-platform app cards.")
    return 0
