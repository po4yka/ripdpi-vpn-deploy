"""Public HTTP behavior for the nginx XHTTP edge."""
from __future__ import annotations

import importlib.util
import re
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


def _render_site_page(name: str) -> str:
    variables = renderer.merge_render_vars()
    variables["public_site_canonical_url"] = "https://notes.example.test"
    return renderer.render_template(SITE_TEMPLATES / name, variables)


def test_primary_vhost_serves_static_site_and_keeps_xhttp_path_separate() -> None:
    rendered = _render()
    assert "root /var/www/public-site;" in rendered
    assert "location / {" in rendered
    assert "try_files $uri $uri/ =404;" in rendered
    assert "proxy_pass http://127.0.0.1:" in rendered
    assert rendered.index("# XHTTP path") < rendered.index("location / {")


def test_primary_and_fallback_vhosts_share_the_hardened_tls_http_identity() -> None:
    rendered = _render(fallback=True)
    assert "TLSv1.2" not in rendered
    assert rendered.count("ssl_protocols       TLSv1.3;") == 2
    assert rendered.count("ssl_ecdh_curve      X25519;") == 2
    for header in (
        'Content-Security-Policy "default-src \'self\'; base-uri \'none\'; form-action \'none\'; frame-ancestors \'none\'; object-src \'none\'"',
        'Permissions-Policy "camera=(), microphone=(), geolocation=()"',
        'Referrer-Policy "no-referrer"',
        'X-Content-Type-Options "nosniff"',
    ):
        assert rendered.count(header) == 2


def test_no_public_health_endpoint_on_primary_or_fallback_vhost() -> None:
    rendered = _render(fallback=True)
    assert "location = /health" not in rendered


def test_site_contains_normal_discovery_and_identity_files() -> None:
    expected_static = {
        "404.html",
        "favicon.svg",
        "assets/site.css",
    }
    actual = {
        str(path.relative_to(SITE_FILES))
        for path in SITE_FILES.rglob("*")
        if path.is_file()
    }
    assert actual == expected_static
    assert {path.name for path in SITE_TEMPLATES.glob("*.j2")} == {
        "_site.html.j2",
        "about.html.j2",
        "index.html.j2",
        "latency-throughput-context.html.j2",
        "methodology.html.j2",
        "reading-benchmark-results.html.j2",
        "repeatable-model-comparisons.html.j2",
        "robots.txt.j2",
        "sitemap.xml.j2",
        "updates.html.j2",
    }


def test_homepage_links_to_substantive_benchmark_guide() -> None:
    homepage = _render_site_page("index.html.j2")
    assert 'href="/notes/reading-benchmark-results.html"' in homepage

    guide = _render_site_page("reading-benchmark-results.html.j2")
    for heading in (
        "Start with the evaluation contract",
        "Read the score as a distribution",
        "Check contamination and prompt sensitivity",
        "A compact review checklist",
    ):
        assert heading in guide

    visible_text = re.sub(r"<[^>]+>", " ", guide)
    assert len(re.findall(r"\b[\w’-]+\b", visible_text)) >= 650


def test_homepage_links_to_substantive_inference_guide() -> None:
    homepage = _render_site_page("index.html.j2")
    assert 'href="/notes/latency-throughput-context.html"' in homepage

    guide = _render_site_page("latency-throughput-context.html.j2")
    for heading in (
        "Separate latency from throughput",
        "Record the workload envelope",
        "Measure a steady run",
        "Report quality and cost together",
    ):
        assert heading in guide

    visible_text = re.sub(r"<[^>]+>", " ", guide)
    assert len(re.findall(r"\b[\w’-]+\b", visible_text)) >= 650


def test_homepage_links_to_substantive_comparison_guide() -> None:
    homepage = _render_site_page("index.html.j2")
    assert 'href="/notes/repeatable-model-comparisons.html"' in homepage

    guide = _render_site_page("repeatable-model-comparisons.html.j2")
    for heading in (
        "Write the decision before the test",
        "Freeze the comparison manifest",
        "Use paired observations",
        "Publish a result bundle",
    ):
        assert heading in guide

    visible_text = re.sub(r"<[^>]+>", " ", guide)
    assert len(re.findall(r"\b[\w’-]+\b", visible_text)) >= 650


def test_about_page_explains_scope_and_maintenance() -> None:
    about = _render_site_page("about.html.j2")
    assert '<link rel="canonical" href="https://notes.example.test/about.html">' in about
    for heading in (
        "A small independent reference",
        "What this site covers",
        "How notes are maintained",
    ):
        assert heading in about

    visible_text = re.sub(r"<[^>]+>", " ", about)
    assert len(re.findall(r"\b[\w’-]+\b", visible_text)) >= 250


def test_methodology_page_defines_the_shared_evidence_standard() -> None:
    methodology = _render_site_page("methodology.html.j2")
    assert (
        '<link rel="canonical" href="https://notes.example.test/methodology.html">'
        in methodology
    )
    for heading in (
        "Prefer repeatable observations",
        "Define the question",
        "Record every moving part",
        "Retain raw observations",
        "State limits",
    ):
        assert heading in methodology

    visible_text = re.sub(r"<[^>]+>", " ", methodology)
    assert len(re.findall(r"\b[\w’-]+\b", visible_text)) >= 400


def test_updates_page_records_dated_revision_history() -> None:
    updates = _render_site_page("updates.html.j2")
    assert '<link rel="canonical" href="https://notes.example.test/updates.html">' in updates
    assert '<time datetime="2026-07-12">12 July 2026</time>' in updates
    assert '<time datetime="2026-07-16">16 July 2026</time>' in updates
    assert "Added three connected guides" in updates
    for path in (
        "/notes/reading-benchmark-results.html",
        "/notes/latency-throughput-context.html",
        "/notes/repeatable-model-comparisons.html",
    ):
        assert f'href="{path}"' in updates


def test_discovery_files_publish_every_canonical_page_with_lastmod() -> None:
    variables = renderer.merge_render_vars()
    variables["public_site_canonical_url"] = "https://notes.example.test"
    sitemap = renderer.render_template(SITE_TEMPLATES / "sitemap.xml.j2", variables)

    for path in (
        "/",
        "/about.html",
        "/methodology.html",
        "/updates.html",
        "/notes/reading-benchmark-results.html",
        "/notes/latency-throughput-context.html",
        "/notes/repeatable-model-comparisons.html",
    ):
        assert f"<loc>https://notes.example.test{path}</loc>" in sitemap
    assert sitemap.count("<lastmod>2026-07-16</lastmod>") == 7

    robots = renderer.render_template(SITE_TEMPLATES / "robots.txt.j2", variables)
    assert "Sitemap: https://notes.example.test/sitemap.xml" in robots


def test_site_copy_is_neutral_and_has_no_vpn_or_admin_surface() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (SITE_FILES, SITE_TEMPLATES)
        for path in root.rglob("*")
        if path.is_file() and path.name != "site.conf.j2"
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
    variables["public_site_canonical_url"] = "https://notes.example.test"
    for name in ("robots.txt.j2", "sitemap.xml.j2"):
        template = SITE_TEMPLATES / name
        rendered = renderer.render_template(template, variables)
        assert "notes.example.test" in rendered
        assert "chinallmodel.com" not in rendered


def test_molecule_exercises_live_http_semantics() -> None:
    verify = (REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "molecule" / "default" / "verify.yml").read_text()
    for behavior in (
        "%{redirect_url}",
        "--head",
        "%{http_code}",
        "Page not found",
        "robots.txt",
        "sitemap.xml",
        ".well-known/security.txt",
        "reading-benchmark-results.html",
        "latency-throughput-context.html",
        "repeatable-model-comparisons.html",
        "Content-Security-Policy",
        "TLSv1.3",
    ):
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
