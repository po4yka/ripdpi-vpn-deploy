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


def test_plain_http_servers_never_log_the_request_path():
    plain = [block for block in blocks(render_every_bearer_surface(), r"^server \{")
             if re.search(r"^\s*listen 80\b", block, re.M)]
    # The primary hostname, the distinct fallback hostname and the default server.
    assert len(plain) == 3
    for block in plain:
        assert all(directive in block for directive in SILENT), block


def render_routing_lists(enabled: bool) -> str:
    variables = merge_render_vars()
    variables["nginx_xhttp"] = {**variables["nginx_xhttp"], "fallback_enabled": True,
                                "fallback_server_name": "alternate.example.invalid",
                                "routing_lists": {"enabled": enabled}}
    return render_template(SITE, variables)


def test_routing_token_stays_out_of_every_tls_access_log():
    rendered = render_routing_lists(True)
    assert "map $request_uri $vpn_public_loggable {" in rendered
    assert "~^/routing/ 0;" in rendered
    # The route regex has braces of its own, so read the body from its alias onward.
    body = rendered.split("alias /var/lib/vpn-routing-lists/", 1)[1].split("}", 1)[0]
    assert all(directive in body for directive in SILENT)
    # error_page and near misses reach these server-level logs with the original request line.
    logs = re.findall(r"^\s*access_log /var/log/nginx/\S+ vpn_public(.*);$", rendered, re.M)
    assert logs == [" if=$vpn_public_loggable"] * 2


def test_disabled_routing_lists_keep_request_uri_protection():
    rendered = render_routing_lists(False)
    assert "alias /var/lib/vpn-routing-lists/" not in rendered
    assert rendered.count("if=$vpn_public_loggable;") == 2
    assert '"$request_method - $server_protocol" $status' in rendered
    assert '"$request" ' not in rendered
    https = [block for block in blocks(rendered, r"^server \{") if "if=$vpn_public_loggable;" in block]
    assert len(https) == 2
    for block in https:
        body = block.split("location = /404.html {", 1)[1].split("}", 1)[0]
        assert "internal;" in body and "access_log " not in body


def test_snell_evaluation_location_never_logs_its_token_path():
    rendered = render_every_bearer_surface()
    locations = blocks(rendered, r"^\s*location ~ \^/synthetic_token_0123456789/")
    assert len(locations) == 1
    assert all(directive in locations[0] for directive in SILENT), locations[0]
    assert r"~^/synthetic_token_0123456789(?:/|\?|$) 0;" in rendered
