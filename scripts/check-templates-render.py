#!/usr/bin/env python3
"""Render every Jinja2 template against synthetic vars + example secrets.

This catches:
 - Jinja2 syntax errors that ansible-lint misses
 - JSON-invalid Xray config produced by the template
 - nginx config that won't pass `nginx -t` (we run the syntax checker if
   nginx is installed; otherwise skip)
 - Templates that crash on default cohort settings

Doesn't substitute for molecule; it's a fast pre-flight.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import UndefinedError

try:
    from template_render import REPO_ROOT, ROLES_DIR, merge_render_vars, render_template
except ModuleNotFoundError:  # Loaded by importlib from the repository root in tests.
    from scripts.template_render import (
        REPO_ROOT,
        ROLES_DIR,
        merge_render_vars,
        render_template,
    )


def validate_json(text: str, label: str) -> str | None:
    try:
        json.loads(text)
        return None
    except json.JSONDecodeError as exc:
        return f"{label}: invalid JSON — {exc}"


def validate_xray(text: str, label: str) -> str | None:
    """Run `xray run -test -config <rendered>` to catch semantic errors that
    JSON parsing misses. Caught classes:
     - routing rule of "type": "field" with no selector (port/network/domain/
       ip/source/inboundTag/protocol). v26+ rejects with "this rule has no
       effective fields" and the role crashes mid-converge.
     - reality `serverNames`/`shortIds` shape errors.
     - inbound port collisions across cohorts.
    Skipped (no failure) if neither the `xray` binary nor the pinned docker
    image is available locally — keeps the script useful in stripped CI envs.
    """
    xray_bin = shutil.which("xray")
    docker_bin = shutil.which("docker") if not xray_bin else None
    image = "ghcr.io/xtls/xray-core:latest"

    if not xray_bin and docker_bin:
        # Use docker only if the image is cached; pulling 50MB inside a
        # template lint step is hostile to local-dev iteration.
        inspect = subprocess.run(
            [docker_bin, "image", "inspect", image],
            capture_output=True,
        )
        if inspect.returncode != 0:
            return None  # skip silently

    if not xray_bin and not docker_bin:
        return None  # skip silently

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, dir="/tmp"
    ) as fh:
        fh.write(text)
        cfg_path = fh.name
    try:
        if xray_bin:
            cmd = [xray_bin, "run", "-test", "-config", cfg_path]
        else:
            cmd = [
                docker_bin, "run", "--rm",
                "-v", f"{cfg_path}:/cfg.json:ro",
                image,
                "xray", "run", "-test", "-config", "/cfg.json",
            ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            msg = (result.stderr.strip() or result.stdout.strip()).splitlines()
            # Trim to last 4 lines — xray banners and log routing noise drown
            # the actual error otherwise.
            tail = "\n    ".join(msg[-4:]) if msg else "(no output)"
            return f"{label}: xray -test failed —\n    {tail}"
        return None
    except subprocess.TimeoutExpired:
        return f"{label}: xray -test timed out after 30s"
    finally:
        Path(cfg_path).unlink(missing_ok=True)


def validate_nginx(text: str, label: str) -> str | None:
    """nginx syntax check. ssl_certificate / ssl_certificate_key / listen
    *ssl* directives reference files that don't exist on the CI runner;
    strip them so the test exercises only the surrounding directives. The
    real `nginx -t` against a deployed cert chain is covered by molecule
    scenarios for nginx-xhttp and subscription-host.
    """
    nginx = shutil.which("nginx")
    if not nginx:
        return None  # silently skip when nginx isn't available

    import os as _os
    import re as _re

    # Strip TLS material — paths point at /etc/nginx/tls which doesn't exist
    # on the runner. Real nginx -t against deployed certs lives in molecule.
    stripped = _re.sub(
        r"^\s*ssl_(certificate|certificate_key|trusted_certificate|session_tickets|prefer_server_ciphers|protocols|ciphers|session_cache|session_timeout)\s+[^;]+;",
        "    # ssl_* directive stripped for syntax-only check",
        text, flags=_re.MULTILINE,
    )
    # Strip per-site access_log / error_log — they reference /var/log/nginx/
    # paths the test runner can't open.
    stripped = _re.sub(
        r"^\s*(access_log|error_log)\s+[^;]+;",
        "    # log directive stripped for syntax-only check",
        stripped, flags=_re.MULTILINE,
    )
    # Remove `listen 443 ssl http2;` ssl/quic flags so nginx doesn't expect cert
    stripped = _re.sub(
        r"(\blisten\s+\S+)\s+ssl(\s+http2)?(\s+http3)?",
        r"\1\2\3",
        stripped,
    )

    # Rewrite privileged listen ports (<1024) to high unprivileged ones.
    # nginx -t on Debian/Ubuntu probes SO_REUSEPORT availability and fails
    # `bind() to 0.0.0.0:80 failed (13: Permission denied)` for the unrooted
    # CI runner. Real binding happens at deploy time as root.
    def _lift_port(match: "_re.Match[str]") -> str:
        prefix, port_str = match.group(1), match.group(2)
        port = int(port_str)
        if port < 1024:
            port += 18000
        return f"{prefix}{port}"

    stripped = _re.sub(
        r"(\blisten\s+(?:\[::\]:)?)(\d+)\b",
        _lift_port,
        stripped,
    )

    # Use a writable prefix so nginx -t can open its default access/error logs
    # and pid file. Pass empty access/error logs via -e and -g pid.
    prefix = tempfile.mkdtemp(prefix="vpn-nginx-")
    _os.makedirs(_os.path.join(prefix, "logs"), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, dir=prefix) as fh:
        fh.write(
            "pid logs/nginx.pid;\n"
            "events {}\n"
            "http {\n"
            "    access_log logs/access.log;\n"
            "    error_log  logs/error.log warn;\n"
            f"{stripped}\n"
            "}\n"
        )
        path = fh.name
    try:
        result = subprocess.run(
            [nginx, "-t", "-p", prefix, "-c", path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return f"{label}: nginx -t failed — {result.stderr.strip()}"
        return None
    finally:
        Path(path).unlink(missing_ok=True)
        # leave dir; tempfile cleanup is best-effort


def main() -> int:
    vars_ = merge_render_vars()
    rendered = 0
    failures: list[str] = []

    for tpl in ROLES_DIR.rglob("*.j2"):
        rel = tpl.relative_to(REPO_ROOT)
        try:
            output = render_template(tpl, vars_)
        except UndefinedError as exc:
            failures.append(f"{rel}: undefined — {exc}")
            continue
        except Exception as exc:
            failures.append(f"{rel}: render error — {exc}")
            continue

        rendered += 1

        # Format-specific validation
        if tpl.name.endswith(".json.j2"):
            err = validate_json(output, str(rel))
            if err:
                failures.append(err)
            # Xray configs get an extra semantic pass via `xray run -test`.
            # This is what catches the "field rule with no selector" class
            # that JSON parsing happily accepts but xray v26+ rejects at
            # start time (and that the existing molecule converge only
            # surfaces ~10 min into a run).
            if tpl.parent.parent.name == "xray":
                err = validate_xray(output, str(rel))
                if err:
                    failures.append(err)
        elif "nginx" in tpl.parent.parent.name and tpl.name.endswith(".conf.j2"):
            err = validate_nginx(output, str(rel))
            if err:
                failures.append(err)

    if failures:
        print("Template render check FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"OK — {rendered} templates rendered cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
