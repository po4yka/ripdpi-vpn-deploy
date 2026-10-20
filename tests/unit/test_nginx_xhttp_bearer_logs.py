"""nginx-xhttp never logs a request path that can carry a bearer token."""

import re
from pathlib import Path

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "ansible/roles/nginx-xhttp/templates/site.conf.j2"
SILENT = ("access_log off;", "error_log /dev/null crit;")


def render_every_bearer_surface() -> str:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_snell": True}
    variables["snell"] = {**variables.get("snell", {}), "evaluation_enabled": True,
                          "evaluation_root": "/var/lib/snell-evaluation"}
    variables["snell_secrets"] = {**variables.get("snell_secrets", {}),
                                  "evaluation_path_token": "synthetic_token_0123456789"}
    variables["nginx_xhttp"] = {**variables["nginx_xhttp"], "fallback_enabled": True,
                                "fallback_server_name": "alternate.example.invalid"}
    return render_template(SITE, variables)


def blocks(text: str, opener: str) -> list[str]:
    """Return each brace-balanced block that starts at a line matching `opener`."""
    found = []
    for match in re.finditer(opener, text, re.M):
        depth, start = 0, text.index("{", match.start())
        for index in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            if depth == 0:
                found.append(text[match.start():index + 1])
                break
    return found


def test_plain_http_redirects_never_log_the_request_path():
    redirects = [block for block in blocks(render_every_bearer_surface(), r"^server \{")
                 if re.search(r"^\s*listen 80;", block, re.M)]
    # The primary and the distinct fallback hostname each have a redirect server.
    assert len(redirects) == 2
    for block in redirects:
        assert "$request_uri" in block
        assert all(directive in block for directive in SILENT), block


def test_snell_evaluation_location_never_logs_its_token_path():
    locations = blocks(render_every_bearer_surface(), r"^\s*location ~ \^/synthetic_token_0123456789/")
    assert len(locations) == 1
    assert all(directive in locations[0] for directive in SILENT), locations[0]
