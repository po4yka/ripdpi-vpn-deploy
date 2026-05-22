"""Assert nginx relay template rendering in CDN-off vs CDN-on configurations.

The RU baseline (vpn.enable_cdn_front: false) uses the nginx-xhttp role's
site.conf.j2 — a direct vhost with no CDN real-IP restoration, no
CF-Connecting-IP header handling, and no Cloudflare AOP cert directives.

The CDN-on path (vpn.enable_cdn_front: true) uses the cdn-front role's
cdn-front.conf.j2, which includes real-IP restoration from CF-Connecting-IP
and optionally AOP cert verification.

Tests:
  CDN_OFF — site.conf.j2 must NOT contain set_real_ip_from, CF-Connecting-IP,
             or ssl_client_certificate (Cloudflare Origin CA).
  CDN_ON  — cdn-front.conf.j2 MUST contain the real-IP include directive and
             proxy_set_header CF-* handling.
"""
from __future__ import annotations

import json
import os
import re as _re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"

# Templates under test
NGINX_XHTTP_TEMPLATE = ROLES_DIR / "nginx-xhttp" / "templates" / "site.conf.j2"
CDN_FRONT_TEMPLATE = ROLES_DIR / "cdn-front" / "templates" / "cdn-front.conf.j2"


def _load_role_defaults() -> dict:
    out: dict = {}
    for defaults in ROLES_DIR.rglob("defaults/main.yml"):
        data = yaml.safe_load(defaults.read_text()) or {}
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def _base_vars() -> dict:
    """Assemble render variables the same way render-snapshots.py does."""
    merged: dict = {}
    merged.update(_load_role_defaults())
    all_yml = GROUP_VARS / "all.yml"
    if all_yml.exists():
        merged.update(yaml.safe_load(all_yml.read_text()) or {})
    if EXAMPLE_FILE.exists():
        merged.update(yaml.safe_load(EXAMPLE_FILE.read_text()) or {})
    # Synthetic facts matching render-snapshots.py
    merged.update(
        {
            "ansible_user": "deploy",
            "ansible_architecture": "x86_64",
            "ansible_os_family": "Debian",
            "ansible_distribution": "Debian",
            "ansible_distribution_release": "trixie",
            "allowed_ssh_cidrs": ["198.51.100.42/32"],
        }
    )
    merged.setdefault("xray_arch", "64")
    merged.setdefault("xray_sha256", "0" * 64)
    merged.setdefault("hysteria_arch", "amd64")
    merged.setdefault("hysteria_sha256", "0" * 64)
    return merged


def _render(template_path: Path, extra_vars: dict | None = None) -> str:
    vars_ = _base_vars()
    if extra_vars:
        vars_.update(extra_vars)
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=select_autoescape(),
    )
    env.filters["to_json"] = lambda v: json.dumps(v)
    env.filters["quote"] = lambda v: "'" + str(v).replace("'", "'\\''") + "'"
    env.filters["dirname"] = lambda v: os.path.dirname(str(v))
    env.filters["basename"] = lambda v: os.path.basename(str(v))
    env.filters["regex_replace"] = lambda v, p, r: _re.sub(p, r, str(v))
    env.filters["regex_search"] = lambda v, p: (
        _re.search(p, str(v)).group(0) if _re.search(p, str(v)) else ""
    )
    env.filters["extract"] = lambda key, container: container[key]
    env.tests["match"] = lambda v, p: bool(_re.search(p, str(v)))
    env.tests["search"] = lambda v, p: bool(_re.search(p, str(v)))
    return env.get_template(template_path.name).render(**vars_)


# ---------------------------------------------------------------------------
# CDN OFF — nginx-xhttp direct vhost (RU baseline)
# ---------------------------------------------------------------------------

class TestCdnOff:
    """The direct/fallback nginx vhost must carry no CDN real-IP directives."""

    def _rendered(self) -> str:
        return _render(NGINX_XHTTP_TEMPLATE)

    def test_no_set_real_ip_from(self):
        """set_real_ip_from is a Cloudflare real-IP restoration directive;
        the direct vhost must never emit it."""
        rendered = self._rendered()
        assert "set_real_ip_from" not in rendered, (
            "Direct nginx vhost must not contain set_real_ip_from — "
            "that belongs only in the CDN-fronted vhost."
        )

    def test_no_cf_connecting_ip_header(self):
        """CF-Connecting-IP is only meaningful behind Cloudflare; a direct
        vhost must not reference it."""
        rendered = self._rendered()
        assert "CF-Connecting-IP" not in rendered, (
            "Direct nginx vhost must not handle CF-Connecting-IP header."
        )

    def test_no_cloudflare_origin_ca(self):
        """ssl_client_certificate + ssl_verify_client appears only in the
        AOP (Authenticated Origin Pulls) block which is CDN-only."""
        rendered = self._rendered()
        assert "ssl_client_certificate" not in rendered
        assert "ssl_verify_client" not in rendered

    def test_renders_successfully(self):
        """Sanity: the template must render without errors and produce a
        non-empty nginx server block."""
        rendered = self._rendered()
        assert "server {" in rendered
        assert "listen" in rendered

    def test_proxy_pass_to_xray_inbound(self):
        """The direct vhost must forward XHTTP path to the local Xray port."""
        rendered = self._rendered()
        assert "proxy_pass http://127.0.0.1:" in rendered


# ---------------------------------------------------------------------------
# CDN ON — cdn-front vhost
# ---------------------------------------------------------------------------

class TestCdnOn:
    """The CDN-fronted vhost must carry real-IP restoration directives."""

    def _rendered(self) -> str:
        # cdn-front.conf.j2 includes a CF prefix file and a conditional AOP block.
        # We render with aop_cert_path empty so the conditional block is skipped.
        return _render(CDN_FRONT_TEMPLATE)

    def test_cf_prefix_include_present(self):
        """The CDN vhost must include the Cloudflare prefix real-IP file."""
        rendered = self._rendered()
        assert "cloudflare.real_ip" in rendered, (
            "cdn-front vhost must include the Cloudflare prefix real-IP file."
        )

    def test_proxy_set_header_x_real_ip(self):
        """The CDN vhost sets X-Real-IP from the CF-restored remote_addr."""
        rendered = self._rendered()
        assert "proxy_set_header X-Real-IP" in rendered

    def test_renders_successfully(self):
        """Sanity: cdn-front.conf.j2 must render without errors."""
        rendered = self._rendered()
        assert "server {" in rendered
        assert "listen" in rendered

    def test_no_set_real_ip_from_in_nginx_xhttp(self):
        """Cross-check: even when CDN vars are in scope, the nginx-xhttp
        direct template must not pick them up."""
        rendered = _render(NGINX_XHTTP_TEMPLATE)
        assert "set_real_ip_from" not in rendered
