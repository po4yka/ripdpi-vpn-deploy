"""HTTP transport that keeps authenticated requests on their admitted origin."""

from __future__ import annotations

import ipaddress
import re
from urllib import parse, request


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def open_no_redirect(outbound, *, timeout):
    return request.build_opener(NoRedirect()).open(outbound, timeout=timeout)


def https_origin(value: str) -> str:
    """Admit an HTTPS origin, without credentials, path or URL control fields."""
    if (any(ord(char) <= 32 or ord(char) == 127 for char in value)
            or any(char in value for char in "?#\\%")):
        raise ValueError("https-origin")
    origin = parse.urlsplit(value)
    host = origin.hostname
    if (
        origin.scheme != "https" or not host or origin.username is not None
        or origin.password is not None or origin.path not in {"", "/"}
        or origin.query or origin.fragment
        or (origin.port is not None and not 1 <= origin.port <= 65535)
    ):
        raise ValueError("https-origin")
    authority = f"[{host}]" if ":" in host else host
    if origin.port is not None:
        authority += f":{origin.port}"
    if origin.netloc.lower() != authority.lower():
        raise ValueError("https-origin")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise ValueError("https-origin") from None
        if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
               for label in host.split(".")):
            raise ValueError("https-origin")
    return value.rstrip("/")
