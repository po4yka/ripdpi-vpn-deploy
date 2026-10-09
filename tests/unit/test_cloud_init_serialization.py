"""Shared bootstrap scalars stay data through real Terraform and CI rendering."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "render_cloud_init_ci", ROOT / "scripts/render-cloud-init-ci.py"
)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

CASES = (
    {},
    {"admin_ssh_public_key": 'ssh-ed25519 AAAATESTKEY owner: laptop # "quoted" \\ path'},
    {
        "admin_user": 'deploy: "quoted" \\ user',
        "admin_ssh_public_key": "ssh-ed25519 AAAATESTKEY note\nruncmd: [unexpected]",
        "build_env": 'ci\nruncmd: [unexpected]\nlabel: "quoted" \\ ${literal}',
    },
    {"admin_ssh_public_key": "ssh-ed25519 AAAATESTKEY <>& unicode \u2028 \u2029"},
)


def assert_scalar_document(document, values):
    baseline = yaml.safe_load(renderer.render())
    assert set(document) == set(baseline)
    assert document["runcmd"] == baseline["runcmd"]
    assert document["users"][1]["name"] == values["admin_user"]
    assert document["users"][1]["ssh_authorized_keys"] == [values["admin_ssh_public_key"]]
    files = {item["path"]: item for item in document["write_files"]}
    assert set(files) == {item["path"] for item in baseline["write_files"]}
    assert files["/etc/vpn-build-id"]["content"] == (
        "provisioned_by=cloud-init\nnext_stage=ansible\n"
        f"build_env={values['build_env']}\n"
    )
    assert files["/usr/local/libexec/vpn-bootstrap-sshd-ownership.py"]["content"] == (
        values["bootstrap_ssh_ownership_b64"]
    )


@pytest.mark.parametrize("edits", CASES, ids=("ordinary", "key-comment", "multiline", "unicode"))
def test_ci_renderer_preserves_scalar_values(edits):
    values = dict(renderer.VALUES, **edits)
    assert_scalar_document(yaml.safe_load(renderer.render(values)), values)


def test_ci_renderer_refuses_unrecognized_template_expression(monkeypatch, tmp_path):
    template = tmp_path / "unknown.tftpl"
    template.write_text("${jsonencode(unrecognized)}\n")
    monkeypatch.setattr(renderer, "TEMPLATE", template)
    with pytest.raises(KeyError, match="unrecognized"):
        renderer.render()


@pytest.mark.parametrize("name", ("admin_user", "admin_ssh_public_key", "build_env"))
def test_ci_renderer_refuses_null_bootstrap_scalars(name):
    with pytest.raises(TypeError, match="scalar inputs must be strings"):
        renderer.render(dict(renderer.VALUES, **{name: None}))


def terraform_render(values, tmp_path):
    environment = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR"}
    }
    configuration = tmp_path / "empty.tfrc"
    configuration.write_text("")
    environment.update(
        TF_CLI_CONFIG_FILE=str(configuration),
        TF_IN_AUTOMATION="1",
        CHECKPOINT_DISABLE="1",
    )
    inputs = tmp_path / "values.json"
    inputs.write_text(json.dumps(values))
    expression = (
        "jsonencode(templatefile("
        + json.dumps(str(ROOT / "terraform/shared/cloud-init.yaml.tftpl"))
        + ", jsondecode(file(" + json.dumps(str(inputs)) + "))))\n"
    )
    return subprocess.run(
        ["terraform", "console", "-no-color"], input=expression,
        cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=30,
    )


@pytest.mark.native_runtime
@pytest.mark.parametrize("edits", CASES, ids=("ordinary", "key-comment", "multiline", "unicode"))
def test_actual_terraform_render_matches_ci_scalar_document(edits, tmp_path):
    values = dict(renderer.VALUES, **edits)
    result = terraform_render(values, tmp_path)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(json.loads(result.stdout))
    document = yaml.safe_load(rendered)
    assert_scalar_document(document, values)
    assert document == yaml.safe_load(renderer.render(values))


@pytest.mark.native_runtime
@pytest.mark.parametrize("name", ("admin_user", "admin_ssh_public_key", "build_env"))
def test_actual_terraform_render_refuses_null_bootstrap_scalars(name, tmp_path):
    result = terraform_render(dict(renderer.VALUES, **{name: None}), tmp_path)
    assert result.returncode != 0
    assert "null value" in result.stderr
