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
        jq -c --arg key "${{2}}" '.[$key].value' "${{FIXTURE}}"
      else
        cat "${{FIXTURE}}"
      fi
      exit 0
    fi
    if [ "${{1:-}}" = "-raw" ]; then
      key="${{2:-}}"
      jq -jr --arg key "$key" \
        'if has($key) then .[$key].value else halt_error(1) end' \
        "${{FIXTURE}}"
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
    assert '"$IP" "$SSH_USER" "$SSH_PORT"' in source
    assert "bootstrap_readiness.py" in source


def _isolated_wait_script(tmp_path):
    """Run the real wait and remote shell; substitute only TF, SSH and the marker path."""
    import shutil
    import sys

    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(WAIT_SCRIPT, root / "scripts/wait-cloud-init.sh")
    controller = root / "scripts/bootstrap_readiness.py"
    shutil.copyfile(REPO_ROOT / "scripts/bootstrap_readiness.py", controller)
    controller.write_text(
        controller.read_text().replace(
            "import time\n",
            'import time\n\nwith open(os.environ["WAIT_CONTROLLER_LOG"], "a", encoding="utf-8") as stream:\n'
            '    stream.write("controller\\n")\n',
            1,
        )
    )
    _make_stub(root / "scripts", "terraform-env.sh",
               'case "$3" in server_ipv4) printf 192.0.2.1;; '
               'admin_user) printf deploy;; ssh_port) printf 2222;; *) exit 99;; esac')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _make_stub(bindir, "cloud-init",
               'printf "called\\n" >> "$WAIT_CLOUD_LOG"; '
               'printf "synthetic-cloud-private-output\\n"; '
               'printf "synthetic-cloud-private-error\\n" >&2; '
               'if [ "$WAIT_CLOUD_CODE" = hang-once ]; then '
               'if [ "$(wc -l < "$WAIT_CLOUD_LOG")" -eq 1 ]; then sleep 30; fi; exit 0; fi; '
               'exit "$WAIT_CLOUD_CODE"')
    ssh = bindir / "ssh"
    ssh.write_text("#!" + sys.executable + "\n" + '''
import json, os, subprocess, sys, time
from pathlib import Path
with open(os.environ["WAIT_SSH_LOG"], "a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[-1] == "true":
    sys.exit(0)
if os.environ.get("WAIT_SSH_FAULT") == "hang":
    child = subprocess.Popen(["sleep", "60"])
    pids = Path(os.environ["WAIT_SSH_PIDS"])
    pids.with_suffix(".tmp").write_text(json.dumps([os.getpid(), child.pid, os.getpgrp()]))
    pids.with_suffix(".tmp").replace(pids)
    time.sleep(60)
if os.environ.get("WAIT_SSH_FAULT") == "disconnect":
    sys.exit(255)
marker_boundary = 'test() { if [ "$1" = -f ] && [ "$2" = /var/lib/cloud-init-vpn-bootstrap.done ]; then builtin test -f "$WAIT_MARKER"; else builtin test "$@"; fi; }; '
sys.exit(subprocess.run(["bash", "-c", marker_boundary + sys.argv[-1]]).returncode)
''')
    ssh.chmod(0o700)
    assert shutil.which("timeout"), "GNU timeout is required for the remote wait regression"
    environment = {**os.environ, "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                   "PROVIDER": "upcloud", "ENV": "test", "ANSIBLE_SSH_PRIVATE_KEY_FILE": "fixture-key",
                   "WAIT_CLOUD_CODE": "0", "WAIT_MARKER": str(tmp_path / "bootstrap.done"),
                   "WAIT_CLOUD_LOG": str(tmp_path / "cloud.log"), "WAIT_SSH_PIDS": str(tmp_path / "pids.json"),
                   "WAIT_SSH_LOG": str(tmp_path / "ssh.jsonl"),
                   "WAIT_CONTROLLER_LOG": str(tmp_path / "controllers.log")}
    return root / "scripts/wait-cloud-init.sh", environment


@pytest.mark.parametrize("cloud_code,expected", [(0, None), (1, "cloud-init error"),
                                                 (2, "cloud-init recoverable error")])
def test_wait_requires_error_free_cloud_init_even_with_marker(tmp_path, cloud_code, expected):
    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_CLOUD_CODE"] = str(cloud_code)
    Path(environment["WAIT_MARKER"]).touch()
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) == (expected is None), result.stdout + result.stderr
    if expected:
        assert expected in result.stderr
    assert "synthetic-cloud-private" not in result.stdout + result.stderr
    calls = [json.loads(line) for line in Path(environment["WAIT_SSH_LOG"]).read_text().splitlines()]
    assert len(calls) == 2
    assert all("BatchMode=yes" in call for call in calls)
    assert all(call[call.index("-p") + 1] == "2222" for call in calls)
    assert all("StrictHostKeyChecking=accept-new" in call for call in calls)
    assert Path(environment["WAIT_CONTROLLER_LOG"]).read_text().splitlines() == ["controller"]


@pytest.mark.parametrize("cloud_code", [124, 137])
def test_wait_retries_remote_deadline_then_reports_cloud_timeout(tmp_path, cloud_code):
    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_CLOUD_CODE"] = str(cloud_code)
    Path(environment["WAIT_MARKER"]).touch()
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "cloud-init timeout" in result.stderr
    assert "SSH session timeout" not in result.stderr
    assert len(Path(environment["WAIT_CLOUD_LOG"]).read_text().splitlines()) == 30
    assert "synthetic-cloud-private" not in result.stdout + result.stderr


def test_wait_retries_a_real_remote_timeout_then_accepts_completed_bootstrap(tmp_path):
    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_CLOUD_CODE"] = "hang-once"
    Path(environment["WAIT_MARKER"]).touch()
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(Path(environment["WAIT_CLOUD_LOG"]).read_text().splitlines()) == 2
    assert "bootstrap ready" in result.stdout
    assert "synthetic-cloud-private" not in result.stdout + result.stderr


@pytest.mark.parametrize("fault,expected", [("marker", "bootstrap marker missing"),
                                           ("disconnect", "SSH transport failure"),
                                           ("unavailable", "cloud-init status unavailable")])
def test_wait_failure_categories_do_not_claim_readiness(tmp_path, fault, expected):
    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_SSH_FAULT"] = fault
    if fault == "unavailable":
        environment["WAIT_CLOUD_CODE"] = "127"
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert expected in result.stderr
    assert "bootstrap ready" not in result.stdout
    assert "synthetic-cloud-private" not in result.stdout + result.stderr


def test_wait_bounds_connected_ssh_and_kills_its_descendants(tmp_path):
    import signal

    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_SSH_FAULT"] = "hang"
    process = subprocess.Popen(["bash", str(script)], env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    pids_file = Path(environment["WAIT_SSH_PIDS"])
    try:
        try:
            stdout, stderr = process.communicate(timeout=13)
        except subprocess.TimeoutExpired:
            pytest.fail("connected SSH exceeded its production session deadline")
        assert process.returncode != 0
        assert "SSH session timeout" in stderr
        assert "cloud-init timeout" not in stderr
        assert "synthetic-cloud-private" not in stdout + stderr
        for pid in json.loads(pids_file.read_text())[:2]:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
            assert not state.stdout.strip() or state.stdout.strip().startswith("Z"), "SSH descendant still running"
    finally:
        groups = {process.pid}
        if pids_file.exists():
            groups.add(json.loads(pids_file.read_text())[2])
        for group in groups:
            assert group != os.getpgrp()
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                # Deadline/cancellation cleanup may already have removed this group.
                pass
        process.communicate()


@pytest.mark.parametrize("interrupt", ["SIGTERM", "SIGINT"])
def test_wait_interruption_kills_only_its_ssh_process_group(tmp_path, interrupt):
    import signal
    import time

    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_SSH_FAULT"] = "hang"
    process = subprocess.Popen(["bash", str(script)], env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    pids_file = Path(environment["WAIT_SSH_PIDS"])
    try:
        # Synchronize at the SSH boundary; setup may use the 15s readiness budget.
        # The actual interruption-to-cleanup bound below remains three seconds.
        deadline = time.monotonic() + 20
        while not pids_file.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pids_file.exists(), "SSH fixture did not start"
        process.send_signal(getattr(signal, interrupt))
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 128 + getattr(signal, interrupt)
        assert "bootstrap ready" not in stdout + stderr
        for pid in json.loads(pids_file.read_text())[:2]:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
            assert not state.stdout.strip() or state.stdout.strip().startswith("Z"), "SSH descendant still running"
    finally:
        groups = {process.pid}
        if pids_file.exists():
            groups.add(json.loads(pids_file.read_text())[2])
        for group in groups:
            assert group != os.getpgrp()
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                # Deadline/cancellation cleanup may already have removed this group.
                pass
        process.communicate()


def test_wait_cancellation_during_spawn_cleans_the_real_child(tmp_path):
    """Inject SIGTERM at Popen return before production code can assign its child."""
    import signal
    import sys

    script, environment = _isolated_wait_script(tmp_path)
    environment["WAIT_SSH_FAULT"] = "hang"
    spawned = tmp_path / "spawned.pid"
    environment["WAIT_SPAWNED_PID"] = str(spawned)
    runtime = tmp_path / "bin/python3"
    runtime.write_text(f'''#!{sys.executable}
import os, runpy, signal, subprocess, sys
from pathlib import Path
if not sys.argv[1].endswith("bootstrap_readiness.py"):
    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
sys.argv = sys.argv[1:]
original = subprocess.Popen
def interrupted_spawn(command, **kwargs):
    child = original(command, **kwargs)
    if command[-1] != "true":
        Path(os.environ["WAIT_SPAWNED_PID"]).write_text(str(child.pid))
        os.kill(os.getpid(), signal.SIGTERM)
    return child
subprocess.Popen = interrupted_spawn
runpy.run_path(sys.argv[0], run_name="__main__")
''')
    runtime.chmod(0o700)
    process = subprocess.Popen(["bash", str(script)], env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        process.communicate(timeout=5)
        assert process.returncode != 0
        child_pid = int(spawned.read_text())
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)], capture_output=True, text=True)
        assert not state.stdout.strip() or state.stdout.strip().startswith("Z"), "spawned SSH escaped cleanup"
    finally:
        groups = {process.pid}
        if spawned.exists():
            groups.add(int(spawned.read_text()))
        for group in groups:
            assert group != os.getpgrp()
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                # Deadline/cancellation cleanup may already have removed this group.
                pass
        process.communicate()


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
