"""Test for scripts/render-inventory.sh.

Feeds tf-output-sample.json through the script via a custom terraform stub
that handles the `console` subcommand (needed for allowed_ssh_cidrs) and
asserts the stdout matches inventory-sample.ini byte-for-byte.

render-inventory.sh writes to ansible/inventory/generated.ini AND cats it to
stdout.  We capture stdout for the comparison.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
SCRIPT = REPO_ROOT / "scripts" / "render-inventory.sh"
WAIT_SCRIPT = REPO_ROOT / "scripts" / "wait-cloud-init.sh"
EXPECTED_INVENTORY = FIXTURES / "inventory-sample.ini"


def _make_stub(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _build_terraform_stub(bin_dir: Path, fixture: Path) -> None:
    """Write a terraform stub that handles all subcommands used by render-inventory.sh.

    The standard stub handles `output -raw <key>` and `output -json` but
    returns nothing for `console`.  render-inventory.sh calls:

        terraform -chdir=<dir> console -no-color -var-file=<f> <<< "jsonencode(var.allowed_ssh_cidrs)"

    and pipes the result through `jq -r .` then `jq -c .`.
    We return `"[\\"203.0.113.0/24\\"]"` (a JSON-encoded JSON string) so that
    the two jq calls decode it to `["203.0.113.0/24"]`.

    We hardcode the fixture path so the stub works from any directory.
    """
    fixture_path = str(fixture)
    body = f"""
STUB_LOG="${{STUB_LOG:-/dev/null}}"
printf 'STUB: terraform %s\\n' "$*" >> "${{STUB_LOG}}"

FIXTURE="{fixture_path}"

# Consume all leading -chdir=... flags (terraform allows them anywhere).
while true; do
  case "${{1:-}}" in
    -chdir=*) shift ;;
    *) break ;;
  esac
done

case "${{1:-}}" in
  output)
    shift
    if [ "${{1:-}}" = "-json" ]; then
      if [ -n "${{2:-}}" ]; then
        python3 -c "
import json, sys
d = json.load(open('${{FIXTURE}}'))
print(json.dumps(d[sys.argv[1]]['value'], separators=(',', ':')))
" "${{2}}"
      else
        cat "${{FIXTURE}}"
      fi
      exit 0
    fi
    if [ "${{1:-}}" = "-raw" ]; then
      key="${{2:-}}"
      python3 -c "
import json, sys
d = json.load(open('${{FIXTURE}}'))
k = sys.argv[1]
if k in d:
    print(d[k]['value'], end='')
else:
    sys.exit(1)
" "$key"
      exit 0
    fi
    exit 0
    ;;
  console)
    # Return a JSON-encoded JSON array for allowed_ssh_cidrs.
    # jq -r . decodes the outer quotes → ["203.0.113.0/24"]
    # jq -c . compacts it  → ["203.0.113.0/24"]
    printf '"[\\\\"203.0.113.0/24\\\\"]"\\n'
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""
    _make_stub(bin_dir, "terraform", body)


def test_render_inventory_matches_fixture(tmp_path):
    """render-inventory.sh output must match inventory-sample.ini exactly.

    The script requires:
      - terraform binary (stubbed via PATH)
      - jq binary (real)
      - terraform/providers/upcloud/environments/prod.tfvars to exist (file
        presence check in shell, before terraform is invoked)
      - ansible/inventory/ directory to exist (for generated.ini)

    We create prod.tfvars temporarily and restore all touched files on exit.
    """
    import shutil as _shutil
    if not _shutil.which("jq"):
        pytest.skip("jq not found on PATH")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _build_terraform_stub(stub_bin, FIXTURES / "tf-output-sample.json")

    # The script checks for the tfvars file before invoking terraform.
    # Create a minimal placeholder (content is irrelevant — only existence matters
    # because our terraform stub ignores it).
    tfvars_path = REPO_ROOT / "terraform" / "providers" / "upcloud" / "environments" / "prod.tfvars"
    tfvars_existed = tfvars_path.exists()
    tfvars_original = tfvars_path.read_bytes() if tfvars_existed else None
    if not tfvars_existed:
        tfvars_path.write_text("# test fixture placeholder\n")

    generated_ini = REPO_ROOT / "ansible" / "inventory" / "generated.ini"
    had_generated = generated_ini.exists()
    original_content = generated_ini.read_bytes() if had_generated else None

    env = os.environ.copy()
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    env["ANSIBLE_SSH_PRIVATE_KEY_FILE"] = "/tmp/test-ssh-key"
    env["PROVIDER"] = "upcloud"
    env["ENV"] = "prod"
    env.pop("HOSTS", None)
    env.pop("COHORTS", None)
    env.pop("AWG_EVIDENCE_MODES", None)
    env["STUB_LOG"] = str(tmp_path / "stub.log")

    try:
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
    finally:
        # Restore generated.ini.
        if had_generated and original_content is not None:
            generated_ini.write_bytes(original_content)
        elif not had_generated and generated_ini.exists():
            generated_ini.unlink()
        # Restore prod.tfvars.
        if not tfvars_existed and tfvars_path.exists():
            tfvars_path.unlink()
        elif tfvars_existed and tfvars_original is not None:
            tfvars_path.write_bytes(tfvars_original)

    if result.returncode != 0:
        pytest.fail(
            f"render-inventory.sh exited {result.returncode}:\n"
            f"stdout: {result.stdout[:1000]}\nstderr: {result.stderr[:500]}"
        )

    # The script prints "wrote ...\n--\n" before the inventory content.
    # Extract just the inventory portion (everything after "--\n").
    stdout = result.stdout
    separator = "--\n"
    if separator in stdout:
        inventory_out = stdout[stdout.index(separator) + len(separator):]
    else:
        inventory_out = stdout

    expected = EXPECTED_INVENTORY.read_text()
    assert inventory_out == expected, (
        f"Inventory output does not match fixture.\n"
        f"--- expected ---\n{expected}\n"
        f"--- got ---\n{inventory_out}"
    )


def test_vultr_inventory_waits_for_secondary_ipv4_guest_convergence(tmp_path):
    """Never publish the Vultr honeypot address before the guest owns it."""
    import shutil as _shutil

    if not _shutil.which("jq"):
        pytest.skip("jq not found on PATH")

    fixture_data = json.loads((FIXTURES / "tf-output-sample.json").read_text())
    fixture_data["honeypot_ipv4"]["value"] = "198.51.100.20"
    fixture = tmp_path / "vultr-output.json"
    fixture.write_text(json.dumps(fixture_data), encoding="utf-8")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _build_terraform_stub(stub_bin, fixture)
    _make_stub(
        stub_bin,
        "ssh",
        'printf "STUB: ssh %s\\n" "$*" >> "${STUB_LOG}"\n'
        'exit "${SSH_GUEST_HAS_IP:-1}"',
    )

    tfvars_path = REPO_ROOT / "terraform" / "providers" / "vultr" / "environments" / "prod.tfvars"
    tfvars_existed = tfvars_path.exists()
    tfvars_original = tfvars_path.read_bytes() if tfvars_existed else None
    if not tfvars_existed:
        tfvars_path.write_text("# test fixture placeholder\n")

    generated_ini = REPO_ROOT / "ansible" / "inventory" / "generated.ini"
    had_generated = generated_ini.exists()
    original_content = generated_ini.read_bytes() if had_generated else None

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{stub_bin}:{env['PATH']}",
            "ANSIBLE_SSH_PRIVATE_KEY_FILE": "/tmp/test-ssh-key",
            "PROVIDER": "vultr",
            "ENV": "prod",
            "STUB_LOG": str(tmp_path / "stub.log"),
            "VULTR_GUEST_IPV4_ATTEMPTS": "1",
            "VULTR_GUEST_IPV4_DELAY_SECONDS": "0",
            "SSH_GUEST_HAS_IP": "1",
        }
    )
    env.pop("HOSTS", None)
    env.pop("COHORTS", None)
    env.pop("AWG_EVIDENCE_MODES", None)

    try:
        not_converged = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert not_converged.returncode != 0
        assert "secondary IPv4 is not configured in the guest" in not_converged.stderr

        env["SSH_GUEST_HAS_IP"] = "0"
        converged = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert converged.returncode == 0, converged.stderr
        assert "honeypot_listen_addr=198.51.100.20" in converged.stdout
        ssh_log = (tmp_path / "stub.log").read_text()
        assert "198.51.100.20" in ssh_log
        assert "-p 2222" in ssh_log
    finally:
        if had_generated and original_content is not None:
            generated_ini.write_bytes(original_content)
        elif not had_generated and generated_ini.exists():
            generated_ini.unlink()
        if not tfvars_existed and tfvars_path.exists():
            tfvars_path.unlink()
        elif tfvars_existed and tfvars_original is not None:
            tfvars_path.write_bytes(tfvars_original)


def test_wait_cloud_init_uses_terraform_ssh_port() -> None:
    source = WAIT_SCRIPT.read_text()

    assert "output -raw ssh_port" in source
    assert source.count('-p "$SSH_PORT"') == 2


def _isolated_inventory_repo(tmp_path):
    import shutil

    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for script in ("render-inventory.sh", "terraform-env.sh"):
        shutil.copy(REPO_ROOT / "scripts" / script, root / "scripts" / script)
    for provider in ("upcloud", "hetzner"):
        envdir = root / "terraform" / "providers" / provider / "environments"
        envdir.mkdir(parents=True)
        (envdir / "test.tfvars").write_text("")
    (root / "ansible" / "inventory").mkdir(parents=True)
    (root / "ansible" / "inventory" / "generated.ini").write_text("last-good\n")
    (root / "ansible" / "group_vars").mkdir()
    (root / "ansible" / "group_vars" / "vpn-p0.yml").write_text("---\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _build_terraform_stub(bindir, FIXTURES / "tf-output-sample.json")
    _make_stub(bindir, "ssh", "echo unexpected SSH call >&2; exit 99")
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "ANSIBLE_SSH_PRIVATE_KEY_FILE": "/tmp/test-key",
        "PROVIDER": "upcloud",
        "ENV": "test",
        "HOSTS": "upcloud:test",
        "COHORTS": "",
        "AWG_EVIDENCE_MODES": "",
        "STUB_LOG": str(tmp_path / "terraform.log"),
    }
    return root, env


@pytest.mark.parametrize("cohort", ["missing", "../p0", "p0]"])
def test_unknown_cohort_fails_before_terraform_and_preserves_inventory(tmp_path, cohort):
    root, env = _isolated_inventory_repo(tmp_path)
    env["COHORTS"] = cohort
    result = subprocess.run(
        ["bash", str(root / "scripts/render-inventory.sh")],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "unknown or invalid cohort" in result.stderr
    assert not Path(env["STUB_LOG"]).exists()
    assert (root / "ansible/inventory/generated.ini").read_text() == "last-good\n"


def test_duplicate_host_alias_preserves_last_inventory(tmp_path):
    root, env = _isolated_inventory_repo(tmp_path)
    env["HOSTS"] = "upcloud:test,hetzner:test"
    result = subprocess.run(
        ["bash", str(root / "scripts/render-inventory.sh")],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert "duplicate inventory alias" in result.stderr
    assert "upcloud:test" in result.stderr and "hetzner:test" in result.stderr
    assert (root / "ansible/inventory/generated.ini").read_text() == "last-good\n"
