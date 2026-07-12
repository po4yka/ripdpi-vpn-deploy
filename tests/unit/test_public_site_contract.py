"""Public HTTP behavior for the nginx XHTTP edge."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "templates" / "site.conf.j2"
HYSTERIA_TEMPLATE = REPO_ROOT / "ansible" / "roles" / "hysteria" / "templates" / "config.yaml.j2"
SITE_FILES = REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "files" / "public-site"
SITE_TEMPLATES = TEMPLATE.parent / "public-site"

spec = importlib.util.spec_from_file_location("public_site_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def _render(*, fallback: bool = False) -> str:
    variables = renderer.merge_render_vars()
    variables["nginx_xhttp"] = {
        **variables["nginx_xhttp"],
        "fallback_enabled": fallback,
    }
    return renderer.render_template(TEMPLATE, variables)


def test_primary_vhost_serves_static_site_and_keeps_xhttp_path_separate() -> None:
    rendered = _render()
    assert "root /var/www/public-site;" in rendered
    assert "location / {" in rendered
    assert "try_files $uri $uri/ =404;" in rendered
    assert "proxy_pass http://127.0.0.1:" in rendered
    assert rendered.index("# XHTTP path") < rendered.index("location / {")


def test_no_public_health_endpoint_on_primary_or_fallback_vhost() -> None:
    rendered = _render(fallback=True)
    assert "location = /health" not in rendered


def test_site_contains_normal_discovery_and_identity_files() -> None:
    expected = {
        "index.html",
        "about.html",
        "methodology.html",
        "updates.html",
        "404.html",
        "favicon.svg",
        "assets/site.css",
    }
    actual = {
        str(path.relative_to(SITE_FILES))
        for path in SITE_FILES.rglob("*")
        if path.is_file()
    }
    assert expected <= actual
    assert {path.name for path in SITE_TEMPLATES.glob("*.j2")} == {
        "robots.txt.j2",
        "sitemap.xml.j2",
        "security.txt.j2",
    }


def test_site_copy_is_neutral_and_has_no_vpn_or_admin_surface() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SITE_FILES.rglob("*")
        if path.is_file()
    ).lower()
    for forbidden in ("vpn", "proxy", "xray", "hysteria", "amnezia", "/admin", "/metrics", "/health"):
        assert forbidden not in text


def test_hysteria_masquerade_uses_the_owned_site_identity() -> None:
    variables = renderer.merge_render_vars()
    rendered = renderer.render_template(HYSTERIA_TEMPLATE, variables)
    assert f"url: https://{variables['nginx_xhttp']['server_name']}" in rendered
    assert "bing.com" not in rendered


def test_discovery_files_follow_the_configured_site_hostname() -> None:
    variables = renderer.merge_render_vars()
    variables["nginx_xhttp"] = {**variables["nginx_xhttp"], "server_name": "notes.example.test"}
    for template in SITE_TEMPLATES.glob("*.j2"):
        rendered = renderer.render_template(template, variables)
        assert "notes.example.test" in rendered
        assert "chinallmodel.com" not in rendered


def test_molecule_exercises_live_http_semantics() -> None:
    verify = (REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "molecule" / "default" / "verify.yml").read_text()
    for behavior in ("%{redirect_url}", "--head", "%{http_code}", "Page not found", "robots.txt", ".well-known/security.txt"):
        assert behavior in verify


def test_operator_healthcheck_probes_the_site_root_not_a_health_endpoint() -> None:
    script = (REPO_ROOT / "scripts" / "healthcheck.sh").read_text()
    assert "--head" in script
    assert '"https://${HTTP_HOST}:${HTTP_PORT}/"' in script
    assert "/health" not in script


def test_nginx_role_activates_validated_site_immediately() -> None:
    tasks = (REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "tasks" / "main.yml").read_text()
    validate_at = tasks.index("cmd: nginx -t")
    flush_at = tasks.index("ansible.builtin.meta: flush_handlers")
    ensure_at = tasks.index("name: Ensure nginx is enabled and started")
    assert validate_at < flush_at < ensure_at


def test_transport_profiles_share_one_canonical_site_identity() -> None:
    group_vars = REPO_ROOT / "ansible" / "group_vars"
    p1 = yaml.safe_load((group_vars / "vpn-p1-web.yml").read_text())
    p2 = yaml.safe_load((group_vars / "vpn-p2-udp.yml").read_text())
    secrets = yaml.safe_load((REPO_ROOT / "secrets" / "prod.secrets.example.yaml").read_text())

    assert p1["public_site_canonical_url"] == p2["public_site_canonical_url"]
    assert secrets["hysteria"]["masquerade_url"] == "https://vpn.example.com"
    tasks = (REPO_ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "main.yml").read_text()
    assert "hysteria.masquerade_url == public_site_canonical_url" in tasks
