"""Render the recipient page with mandatory HTML autoescaping."""

from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path
from jinja2 import Environment, StrictUndefined


@dataclass
class Link:
    label: str
    url: str


@dataclass
class AppCard:
    platform: str
    primary: Link
    also: list[Link] = field(default_factory=list)


@dataclass
class RecipientCtx:
    client_name: str
    host: str
    env: str
    provider: str
    subscription_url: str
    singbox_deeplink: str
    ripdpi_deeplink: str
    apps: list[AppCard] = field(default_factory=list)


def render(ctx: RecipientCtx) -> str:
    packaged = files("vpnd").joinpath("data/recipient.html")
    if packaged.is_file():
        template = packaged.read_text(encoding="utf-8")
    else:
        template = (Path(__file__).resolve().parents[3] / "templates/recipient.html").read_text()
    return (
        Environment(autoescape=True, undefined=StrictUndefined)
        .from_string(template)
        .render(**asdict(ctx))
    )
