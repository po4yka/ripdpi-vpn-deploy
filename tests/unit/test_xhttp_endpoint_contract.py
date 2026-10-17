"""Admission and rendering agree on the direct XHTTP endpoint authority."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest
import yaml

from scripts.template_render import merge_render_vars, render_template
from transport_semantics import origin_valid, transport_errors

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "xhttp_extra_vars_validator", ROOT / "scripts/validate-ansible-extra-vars.py")
extra_vars = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extra_vars)

INVALID_PATHS = [
    "/", "/sync/", "//sync", "/sync//chunk", "/sync?mode=1", "/sync#chunk",
    "/sync%2fchunk", "/sync/../chunk", "/sync/./chunk", "/sync;return 200",
    "/sync\n", "/sync\u00a0", "/sync{chunk}", "/sy nc", "/" + "a" * 256,
]


def inputs(path="/sync", port=8443, origin=None):
    document = {
        "xray": {"clients": [{"name": "device", "short_id": "aabb"}], "xhttp_path": path},
        "nginx_xhttp": {"server_name": "edge.example.test"},
    }
    context = {
        "vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": True},
        "nginx_xhttp_public_port": port,
        "public_site_canonical_url": origin or (
            "https://edge.example.test" + ("" if port == 443 else f":{port}")),
    }
    return document, context


@pytest.mark.parametrize("path", INVALID_PATHS)
def test_schema_rejects_noncanonical_paths(path):
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(path, schema["properties"]["xray"]["properties"]["xhttp_path"])


@pytest.mark.parametrize("path", INVALID_PATHS)
def test_transport_preflight_rejects_noncanonical_paths_without_values(path):
    errors = transport_errors(*inputs(path))
    assert any(field == "xray.xhttp_path" for field, _ in errors)
    assert path not in json.dumps(errors)


@pytest.mark.parametrize("path", ["/sync", "/app-sync", "/sync_v2/packet-1"])
@pytest.mark.parametrize("port", [443, 8443])
def test_canonical_path_and_served_origin_are_accepted(path, port):
    assert not transport_errors(*inputs(path, port))


@pytest.mark.parametrize("origin", [
    "https://edge.example.test", "https://edge.example.test:443",
    "https://edge.example.test:2083", "https://other.example.test:8443",
])
def test_origin_must_match_the_effective_primary_host_and_port(origin):
    errors = transport_errors(*inputs(origin=origin))
    assert any(field == "public_site_canonical_url" for field, _ in errors)


@pytest.mark.parametrize("value", [
    "https://edge.example.test/", "https://edge.example.test?",
    "https://edge.example.test#", "https://edge.example.test:443",
    "https://edge.example.test:08443", "https://edge.example.test:",
    "https://user@edge.example.test", "https://edge.example.test:65536",
])
def test_origin_has_one_canonical_representation(value):
    assert not origin_valid(value)


@pytest.mark.parametrize("port", [8443, 2083, 65535])
def test_extra_vars_accept_nondefault_https_ports(tmp_path, port):
    path = tmp_path / "extra-vars.yml"
    path.write_text(yaml.safe_dump({
        "public_site_canonical_url": f"https://edge.example.test:{port}"}))
    extra_vars.validate(path)


def test_both_direct_frontends_overwrite_forwarding_authority():
    variables = merge_render_vars()
    variables["nginx_xhttp"]["fallback_enabled"] = True
    nginx = render_template(ROOT / "ansible/roles/nginx-xhttp/templates/site.conf.j2", variables)
    assert nginx.count("proxy_set_header X-Forwarded-For $remote_addr;") == 2
    assert nginx.count("proxy_set_header X-Real-IP $remote_addr;") == 2
    assert "$proxy_add_x_forwarded_for" not in nginx
    xray = json.loads(render_template(ROOT / "ansible/roles/xray/templates/config.json.j2", variables))
    inbound = next(row for row in xray["inbounds"] if row["tag"] == "vless-xhttp-localhost")
    assert inbound["streamSettings"]["sockopt"]["trustedXForwardedFor"] == ["X-Forwarded-For"]


@pytest.mark.parametrize("case", ["accepted", "path", "origin"])
@pytest.mark.parametrize("check_mode", [False, True])
def test_actual_nginx_preflight_refuses_before_mutation_without_private_values(tmp_path, case, check_mode):
    document, context = inputs()
    if case == "path":
        document["xray"]["xhttp_path"] = "/private-marker/"
    if case == "origin":
        context["public_site_canonical_url"] = "https://private-marker.example.test:2083"
    marker = tmp_path / "mutation"
    role = ROOT / "ansible/roles/nginx-xhttp"
    first = yaml.safe_load((role / "tasks/enable.yml").read_text())[0]
    assert first["vars"]["transport_input_sections"] == ["xhttp"]
    play = tmp_path / "preflight.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {**document, **context, "role_path": str(role), "ansible_python_interpreter": sys.executable},
        "tasks": [first, {"name": "Publish mutation marker", "ansible.builtin.copy": {
            "dest": str(marker), "content": "mutated", "mode": "0600"}}],
    }]))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nhost_key_checking = true\nretry_files_enabled = false\n[connection]\npipelining = true\n")
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play), *(["--check"] if check_mode else [])],
                            env={**os.environ, "ANSIBLE_CONFIG": str(config)}, cwd=tmp_path,
                            capture_output=True, text=True, timeout=40)
    assert (result.returncode == 0) is (case == "accepted"), result.stdout + result.stderr
    assert marker.exists() is (case == "accepted" and not check_mode)
    assert "Validate enabled transport semantics before mutation" in result.stdout
    assert "private-marker" not in result.stdout + result.stderr
    if case != "accepted":
        assert "Publish mutation marker" not in result.stdout


def test_optional_cdn_consumer_never_appends_incoming_source_authority():
    variables = merge_render_vars()
    rendered = render_template(ROOT / "ansible/roles/cdn-front/templates/cdn-front.conf.j2", variables)
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in rendered
    assert "$proxy_add_x_forwarded_for" not in rendered
    assert "access_log off;" in rendered and "error_log /dev/null crit;" in rendered


@pytest.mark.parametrize("port", [443, 8443])
def test_site_metadata_keeps_hostname_identity_and_port_aware_urls(port):
    variables = merge_render_vars()
    origin = "https://edge.example.test" + ("" if port == 443 else f":{port}")
    variables["public_site_canonical_url"] = origin
    page = render_template(ROOT / "ansible/roles/nginx-xhttp/templates/public-site/index.html.j2", variables)
    assert '"alternateName": ["edge.example.test"]' in page
    assert f'"url": "{origin}/"' in page and f'"url": "{origin}/logo.svg"' in page


@pytest.mark.parametrize("port", ["8443", "443", "`touch injected`", '8443"; touch injected; : "',
                                  "$(shell touch injected)", "$(touch injected)"])
def test_make_bootstrap_transports_port_literally_before_validation(tmp_path, port):
    (tmp_path / "Makefile").write_bytes((ROOT / "Makefile").read_bytes())
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    recorder = scripts / "bootstrap-secrets.sh"
    recorder.write_text("#!/bin/sh\nexec python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' \"$@\"\n")
    recorder.chmod(0o700)
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS"}}
    result = subprocess.run(["make", "--no-print-directory", "bootstrap-secrets", "TARGET=mirror.example.test:443",
                             "SERVER_NAME=mirror.example.test", "XHTTP_PORT=" + port], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    arguments = json.loads(result.stdout.splitlines()[-1])
    assert arguments[-2:] == ["--xhttp-port", port]
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize("scenario", ["full-stack", "full-stack-published"])
def test_full_stack_origins_pass_the_real_transport_admission(scenario):
    document = yaml.safe_load((ROOT / "ansible/molecule/full-stack/test-secrets.yaml").read_text())
    inventory = yaml.safe_load((ROOT / f"ansible/molecule/{scenario}/molecule.yml").read_text())
    groups = inventory["provisioner"]["inventory"]["group_vars"]
    context = {**yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text()),
               **groups["all"], **groups["vpn"]}
    assert not transport_errors(document, context, sections=["xhttp", "hysteria"])
