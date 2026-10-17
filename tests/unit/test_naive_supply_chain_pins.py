"""Naive build inputs must be immutable and checksum-verified."""

from pathlib import Path


def test_naive_forwardproxy_is_commit_pinned_and_checksum_required():
    root = Path(__file__).resolve().parents[2]
    defaults = (root / "ansible/roles/naive/defaults/main.yml").read_text()
    tasks = (root / "ansible/roles/naive/tasks/enable.yml").read_text()
    assert "forwardproxy@c096d6a00cb28e019cc1995b04bdc6a9311d8024" in defaults
    assert "naive.xcaddy_sha256 is match" in tasks


def test_naive_request_bearing_error_logs_are_excluded():
    import json
    from scripts.template_render import merge_render_vars, render_template

    root = Path(__file__).resolve().parents[2]
    document = json.loads(
        render_template(
            root / "ansible/roles/naive/templates/caddy.json.j2", merge_render_vars()
        )
    )
    default_log = document["logging"]["logs"]["default"]
    assert "http.log.error" in default_log["exclude"]
    assert "http.log.access" in default_log["exclude"]
    assert set(document["logging"]["logs"]) == {"default"}
    assert "logs" not in document["apps"]["http"]["servers"]["srv0"]
