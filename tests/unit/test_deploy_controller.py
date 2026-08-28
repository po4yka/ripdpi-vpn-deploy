"""Deploy controller behavior through Make, private files and real Ansible.

SSH/Ansible executables in the orchestration fixture record calls instead of
contacting hosts. Separate parity cases use the installed Ansible locally.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)
    return path


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path.resolve() / "repo"
    root.mkdir()
    (root / "Makefile").write_bytes((ROOT / "Makefile").read_bytes())
    for name in ("fleet_inspection.py", "deploy-source-identity.sh",
                 "validate-ansible-extra-vars.py", "deploy-controller.py", "bootstrap_readiness.py"):
        source = ROOT / "scripts" / name
        if source.exists():
            target = root / "scripts" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
    write(root / "ansible/ansible.cfg", "[defaults]\ninventory=inventory/generated.ini\n")
    write(root / "ansible/group_vars/all.yml", "vpn: {enable_xray_reality: true}\n")
    write(root / "ansible/group_vars/vpn.yml", "{}\n")
    write(root / "ansible/group_vars/vpn-p0.yml", "vpn: {enable_xray_reality: true}\n")
    write(root / "ansible/group_vars/vpn-p1p2.yml", "vpn: {enable_xray_reality: false}\n")
    for name in ("site", "source-drift"):
        write(root / f"ansible/playbooks/{name}.yml",
              "- hosts: vpn\n  gather_facts: false\n  tasks: []\n")
    home = tmp_path.resolve() / "home"
    key = write(home / ".ssh/identity", "synthetic-private-key\n")
    known_hosts = write(home / ".ssh/known_hosts", "synthetic-host-pin\n")
    inventory = write(root / "ansible/inventory/generated.ini",
                      "[vpn]\n"
                      "node-one ansible_host=192.0.2.1 ansible_user=deploy ansible_port=2222 provider=upcloud env=prod\n"
                      "node-two ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22 provider=vultr env=prod\n"
                      "[vpn-p0]\nnode-one\n[vpn-p1p2]\nnode-two\n"
                      f"[vpn:vars]\nansible_ssh_private_key_file={key}\nansible_python_interpreter=/usr/bin/python3\n")
    secrets = write(tmp_path.resolve() / "secrets.yaml", "fixture_secret: synthetic-private-value\n")
    calls = tmp_path.resolve() / "calls.jsonl"
    binary = tmp_path.resolve() / "bin"
    binary.mkdir()
    # These transport boundaries never inspect real keys, connect to hosts or
    # run runtime playbooks. Paths are fixed inside this fixture's scripts.
    program = f"""#!{sys.executable}
import json, pathlib, sys
with pathlib.Path({str(calls)!r}).open('a') as stream:
    stream.write(json.dumps({{'program': pathlib.Path(sys.argv[0]).name, 'args': sys.argv[1:]}}) + '\\n')
if pathlib.Path(sys.argv[0]).name == 'ansible-inventory':
    print(json.dumps({{'vpn': {{'hosts': ['node-one', 'node-two']}}}}))
sys.exit(0)
"""
    for name in ("ssh", "ansible-playbook", "ansible-inventory"):
        write(binary / name, program, 0o700)
    for name in ("validate-secrets.py", "spot-check-secrets.py", "check-certs.sh", "audit-log.sh"):
        write(root / "scripts" / name, program, 0o700)
    write(root / ".gitignore", "ansible/inventory/\n__pycache__/\n")
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("ANSIBLE_", "GIT_", "DEPLOY_", "BACKUP_"))
                   and k not in ("SKIP_PRECHECK", "MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "HOSTS", "COHORTS")}
    environment.update(HOME=str(home), PATH=str(binary) + os.pathsep + os.environ["PATH"],
                       INSPECT_KNOWN_HOSTS=str(known_hosts))
    for command in (["git", "init", "-q"], ["git", "config", "user.name", "Deploy fixture"],
                    ["git", "config", "user.email", "fixture@example.invalid"],
                    ["git", "add", "."], ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "test: fixture source"]):
        subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    return {"root": root, "home": home, "inventory": inventory, "key": key,
            "known_hosts": known_hosts, "secrets": secrets, "calls": calls, "env": environment}


def invoke(workspace, target="dry-run", limit="", **values):
    arguments = {"ANSIBLE_LIMIT": limit, "SECRETS_FILE": str(workspace["secrets"]), **values}
    return subprocess.run(["make", target, *(f"{key}={value}" for key, value in arguments.items())],
                          cwd=workspace["root"], env=workspace["env"], text=True,
                          capture_output=True, timeout=25)


def calls(workspace):
    path = workspace["calls"]
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("limit,expected", [
    ("", ["192.0.2.1", "192.0.2.2"]),
    ("node-one", ["192.0.2.1"]),
    ("vpn-p1p2", ["192.0.2.2"]),
    ("vpn-p0,node-two", ["192.0.2.1", "192.0.2.2"]),
])
def test_make_waits_for_exact_inventory_subset_before_ansible(workspace, limit, expected):
    result = invoke(workspace, limit=limit)
    assert result.returncode == 0, result.stderr
    observed = calls(workspace)
    ssh = [entry for entry in observed if entry["program"] == "ssh"]
    assert [entry["args"][-2] for entry in ssh] == expected
    play = next(index for index, entry in enumerate(observed) if entry["program"] == "ansible-playbook")
    assert all(entry["program"] != "ssh" for entry in observed[play:])
    assert not any(entry["program"] == "ansible-inventory" for entry in observed)
    assert "--check" in observed[play]["args"] and "--diff" in observed[play]["args"]


@pytest.mark.parametrize("limit", ["node-*", "vpn:!node-one", "@private-list", "unknown"])
def test_invalid_deploy_selection_refuses_before_any_transport(workspace, limit):
    result = invoke(workspace, limit=limit)
    assert result.returncode != 0
    assert not any(entry["program"] in ("ssh", "ansible-playbook", "ansible-inventory")
                   for entry in calls(workspace))


@pytest.mark.parametrize("target", ["deploy", "dry-run"])
def test_make_debug_refusal_precedes_git_and_ansible(workspace, target):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    git_marker = workspace["root"].parent / "git-called"
    real_git = shutil.which("git")
    write(binary / "git", f"#!/bin/sh\nprintf called >> '{git_marker}'\nexec '{real_git}' \"$@\"\n", 0o700)
    workspace["env"]["ANSIBLE_DEBUG"] = "true"
    result = invoke(workspace, target=target)
    assert result.returncode != 0 and "debug is not supported" in result.stderr
    assert not git_marker.exists()
    assert calls(workspace) == []


def test_dirty_source_cannot_be_hidden_by_ambient_git_routing(workspace):
    other = workspace["root"].parent / "other-repository"
    subprocess.run(["git", "init", "-q", str(other)], check=True, capture_output=True)
    workspace["env"].update(GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
    (workspace["root"] / "uncommitted.txt").write_text("uncommitted deployment change")
    result = invoke(workspace, target="deploy")
    assert result.returncode != 0 and "clean source required" in result.stderr
    assert calls(workspace) == []


def test_unchanged_selector_is_called_once_for_the_resolved_union(workspace):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    record = workspace["root"].parent / "selector.jsonl"
    write(binary / "python3", f"""#!{sys.executable}
import json, os, pathlib, runpy, sys
if not sys.argv[1].endswith('deploy-controller.py'):
    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
sys.argv = sys.argv[1:]
sys.path.insert(0, str(pathlib.Path(sys.argv[0]).resolve().parent))
def observe(frame, event, arg):
    if event == 'call' and frame.f_code.co_name == 'select_hosts' and frame.f_code.co_filename.endswith('/fleet_inspection.py'):
        with pathlib.Path({str(record)!r}).open('a') as stream:
            stream.write(json.dumps(frame.f_locals['selected']) + '\\n')
sys.setprofile(observe)
runpy.run_path(sys.argv[0], run_name='__main__')
""", 0o700)
    result = invoke(workspace, limit="vpn-p0,node-two")
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in record.read_text().splitlines()] == [["node-one", "node-two"]]


@pytest.mark.parametrize("field", ["ANSIBLE_LIMIT", "SECRETS_FILE", "ANSIBLE_EXTRA_VARS_FILE", "INSPECT_KNOWN_HOSTS"])
def test_make_inputs_do_not_expand_make_functions(workspace, field):
    marker = workspace["root"].parent / "expanded"
    result = invoke(workspace, **{field: "$(shell touch " + str(marker) + ")"})
    assert result.returncode != 0
    assert not marker.exists()
    assert not any(entry["program"] in ("ssh", "ansible-playbook") for entry in calls(workspace))


@pytest.mark.parametrize("field", ["ENV", "PROVIDER"])
@pytest.mark.parametrize("target", ["deploy", "backup-configure"])
def test_make_labels_do_not_expand_before_controller_privacy_guard(workspace, field, target):
    marker = workspace["root"].parent / "early-label-expansion"
    workspace["env"]["ANSIBLE_DEBUG"] = "true"
    if target == "backup-configure":
        shutil.copy2(ROOT / "scripts/backup-configure.py", workspace["root"] / "scripts/backup-configure.py")
    result = invoke(workspace, target=target, **{field: "$(shell touch " + str(marker) + ")"})
    message = "ansible-debug-not-supported" if target == "backup-configure" else "debug is not supported"
    assert result.returncode != 0 and message in result.stderr
    assert not marker.exists()
    assert calls(workspace) == []


@pytest.mark.parametrize("fault", ["second-key", "known-hosts", "secrets-yaml", "cohort-yaml"])
def test_every_local_input_is_validated_before_first_ssh(workspace, fault):
    if fault == "second-key":
        second_key = write(workspace["home"] / ".ssh/unsafe", "synthetic-key", 0o644)
        text = workspace["inventory"].read_text().replace("node-two ansible_host=", f"node-two ansible_ssh_private_key_file={second_key} ansible_host=")
        # Per-host keys must not ambiguously override a [vpn:vars] key.
        text = text.replace(f"ansible_ssh_private_key_file={workspace['key']}\n", "")
        text = text.replace("node-one ansible_host=", f"node-one ansible_ssh_private_key_file={workspace['key']} ansible_host=")
        workspace["inventory"].write_text(text)
    elif fault == "known-hosts":
        workspace["known_hosts"].unlink()
    elif fault == "secrets-yaml":
        workspace["secrets"].write_text("broken: [\n")
    else:
        (workspace["root"] / "ansible/group_vars/vpn-p1p2.yml").write_text("broken: [\n")
    result = invoke(workspace)
    assert result.returncode != 0
    assert not any(entry["program"] in ("ssh", "ansible-playbook") for entry in calls(workspace))


def test_private_read_only_ssh_key_remains_usable(workspace):
    workspace["key"].chmod(0o400)
    result = invoke(workspace, limit="node-one")
    assert result.returncode == 0, result.stderr
    assert any(entry["program"] == "ssh" for entry in calls(workspace))


def commit_fixture(workspace):
    subprocess.run(["git", "add", "."], cwd=workspace["root"], env=workspace["env"], check=True, capture_output=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "test: configure fixture"],
                   cwd=workspace["root"], env=workspace["env"], check=True, capture_output=True)


@pytest.mark.parametrize("dirty_source", [False, True])
def test_deploy_freezes_inventory_and_rechecks_source_before_convergence(workspace, dirty_source):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    # Source and inventory mutation happens at the first actual SSH boundary,
    # after the controller must have finished all local validation.
    ssh = binary / "ssh"
    program = ssh.read_text()
    change = workspace["root"] / "changed.txt"
    injected = (f"pathlib.Path({str(workspace['inventory'])!r}).write_text('[vpn]\\ninjected\\n')\n"
                + (f"pathlib.Path({str(change)!r}).write_text('source became dirty')\n" if dirty_source else ""))
    ssh.write_text(program.replace("sys.exit(0)", injected + "sys.exit(0)"))
    recorder = binary / "ansible-playbook"
    program = recorder.read_text()
    recorder.write_text(program.replace("sys.exit(0)", f"""
inventory = pathlib.Path(sys.argv[sys.argv.index('-i') + 1])
assert inventory.name == 'selected.ini'
assert inventory.stat().st_mode & 0o777 == 0o600
document = json.loads(pathlib.Path(sys.argv[1]).read_text())
with pathlib.Path({str(workspace['calls'])!r}).open('a') as stream:
    stream.write(json.dumps({{'program': 'snapshot', 'inventory': str(inventory),
                            'bytes': inventory.read_text(), 'play': document[-1]['import_playbook']}}) + '\\n')
sys.exit(0)
"""))
    result = invoke(workspace, target="deploy", limit="node-one")
    observed = calls(workspace)
    if dirty_source:
        assert result.returncode != 0 and "clean source required" in result.stderr
        assert not any(entry["program"] in ("ansible-playbook", "audit-log.sh") for entry in observed)
    else:
        assert result.returncode == 0, result.stderr
        snapshots = [entry for entry in observed if entry["program"] == "snapshot"]
        assert len(snapshots) == 2 and snapshots[0]["inventory"] == snapshots[1]["inventory"]
        assert snapshots[0]["bytes"] == snapshots[1]["bytes"]
        assert "node-one ansible_host=192.0.2.1" in snapshots[0]["bytes"]
        assert "node-two" not in snapshots[0]["bytes"] and "injected" not in snapshots[0]["bytes"]
        assert [Path(entry["play"]).stem for entry in snapshots] == ["site", "source-drift"]
        assert observed[-1]["program"] == "audit-log.sh"
        assert not Path(snapshots[0]["inventory"]).exists(), "private artifacts survived completion"


@pytest.mark.parametrize("failed_stage", ["site", "source-drift"])
def test_deploy_failure_never_records_success_audit(workspace, failed_stage):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    recorder = binary / "ansible-playbook"
    recorder.write_text(recorder.read_text().replace("sys.exit(0)",
                        f"sys.exit(31 if pathlib.Path(sys.argv[1]).stem == {failed_stage!r} else 0)"))
    result = invoke(workspace, target="deploy", limit="node-one")
    assert result.returncode != 0
    observed = calls(workspace)
    assert not any(entry["program"] == "audit-log.sh" for entry in observed)
    assert len([entry for entry in observed if entry["program"] == "ansible-playbook"]) == (1 if failed_stage == "site" else 2)


def test_prechecks_keep_strict_schema_validation_before_readiness(workspace):
    validator = workspace["root"] / "scripts/validate-secrets.py"
    validator.write_text(validator.read_text().replace("sys.exit(0)", "sys.exit(17)"))
    result = invoke(workspace)
    assert result.returncode != 0
    observed = calls(workspace)
    assert [entry["program"] for entry in observed] == ["validate-secrets.py"]
    assert observed[0]["args"][-1] == "--strict"
    assert not Path(observed[0]["args"][0]).exists(), "private secrets snapshot must be cleaned"


@pytest.mark.parametrize("failure", ["timeout", "sigterm"])
def test_cert_precheck_temporary_keys_are_reclaimed_on_interruption(workspace, failure):
    root = workspace["root"]
    shutil.copy2(ROOT / "scripts/check-certs.sh", root / "scripts/check-certs.sh")
    workspace["secrets"].write_text(yaml.safe_dump({"nginx_xhttp": {
        "server_name": "fixture.example.invalid", "cert_pem": "STUB_CERT_PUBLIC",
        "key_pem": "STUB_CERT_PRIVATE"}}))
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    record = root.parent / "cert-precheck.json"
    write(binary / "openssl", f"""#!{sys.executable}
import json, os, pathlib, sys, time
record = pathlib.Path({str(record)!r})
record.with_suffix('.tmp').write_text(json.dumps({{
    'cert': sys.argv[sys.argv.index('-in') + 1], 'group': os.getpgrp(),
    'private': str(pathlib.Path(os.environ['VPN_SECRETS_FILE']).parent)}}))
record.with_suffix('.tmp').replace(record)
time.sleep(60)
""", 0o700)
    process = subprocess.Popen(["make", "dry-run", "ANSIBLE_LIMIT=node-one",
                                "SECRETS_FILE=" + str(workspace["secrets"])],
                               cwd=root, env=workspace["env"], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    observed = None
    try:
        deadline = time.monotonic() + 15
        while not record.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert record.exists(), "real certificate precheck did not reach the OpenSSL boundary"
        observed = json.loads(record.read_text())
        cert = Path(observed["cert"])
        key = cert.with_name("nginx_xhttp.key.pem")
        assert key.read_text() == "STUB_CERT_PRIVATE\n"
        assert key.stat().st_mode & 0o777 == 0o600
        if failure == "sigterm":
            process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=3 if failure == "sigterm" else 20)
        assert process.returncode != 0
        if failure == "timeout":
            assert "session timeout" in stderr
        assert "STUB_CERT_PRIVATE" not in stdout + stderr
        assert not any(entry["program"] in ("ssh", "ansible-playbook") for entry in calls(workspace))
        assert not Path(observed["private"]).exists(), "controller snapshots survived interruption"
        assert not cert.parent.exists(), "private certificate copies escaped controller cleanup"
    finally:
        for group in {process.pid, *([observed["group"]] if observed else [])}:
            assert group != os.getpgrp()
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                # Production cancellation already reclaimed this owned group.
                pass
        process.communicate()
        if observed:
            # A failing regression may leave its synthetic copies outside the
            # controller directory. Reclaim only this fixture's recorded bundle.
            cert = Path(observed["cert"])
            assert cert.name == "nginx_xhttp.cert.pem" and cert.parent.name.startswith("vpn-check-certs.")
            if cert.parent.exists():
                shutil.rmtree(cert.parent)


def test_standalone_cert_precheck_honors_private_tmpdir_and_cleans_failed_parse(workspace):
    root = workspace["root"]
    temporary = root.parent / "private-cert-temp"
    temporary.mkdir(mode=0o700)
    workspace["secrets"].write_text(yaml.safe_dump({"nginx_xhttp": {
        "server_name": "fixture.example.invalid", "cert_pem": "STUB_CERT_PUBLIC",
        "key_pem": "STUB_CERT_PRIVATE"}}))
    record = root.parent / "standalone-cert.json"
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    write(binary / "openssl", f"""#!{sys.executable}
import json, pathlib, sys
cert = pathlib.Path(sys.argv[sys.argv.index('-in') + 1])
key = cert.with_name('nginx_xhttp.key.pem')
pathlib.Path({str(record)!r}).write_text(json.dumps({{
    'cert': str(cert), 'mode': key.stat().st_mode & 0o777,
    'directory_mode': cert.parent.stat().st_mode & 0o777}}))
raise SystemExit(1)
""", 0o700)
    result = subprocess.run([str(ROOT / "scripts/check-certs.sh")], cwd=root,
                            env={**workspace["env"], "TMPDIR": str(temporary),
                                 "VPN_SECRETS_FILE": str(workspace["secrets"])},
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 1 and "openssl could not parse cert_pem" in result.stdout
    observed = json.loads(record.read_text())
    cert = Path(observed["cert"])
    assert observed["mode"] == 0o600 and observed["directory_mode"] == 0o700
    assert not cert.parent.exists(), "standalone EXIT trap must still reclaim its private copies"
    assert cert.parent.parent == temporary
    assert "STUB_CERT_PRIVATE" not in result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["exit", "unavailable"])
def test_audit_remains_best_effort_and_uses_only_approved_audit_environment(workspace, failure):
    root = workspace["root"]
    audit = root / "scripts/audit-log.sh"
    environment_record = root.parent / "audit-env.json"
    keys = {"AGE_KEY": "synthetic-key-location", "AUDIT_LOG_FILE": "synthetic-log-location",
            "AUDIT_ACTOR": "fixture-operator"}
    workspace["env"].update(keys, AWS_SECRET_ACCESS_KEY="synthetic-provider-credential")
    write(root / ".fleet.mk", "ENV = canary\nPROVIDER = scaleway\n")
    write(audit, f"""#!{sys.executable}
import json, os, pathlib
pathlib.Path({str(environment_record)!r}).write_text(json.dumps(dict(os.environ)))
raise SystemExit(19)
""", 0o700)
    commit_fixture(workspace)
    if failure == "unavailable":
        executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ansible-playbook"
        executable.write_text(executable.read_text().replace("sys.exit(0)",
            f"if pathlib.Path(sys.argv[1]).stem == 'source-drift': pathlib.Path({str(audit)!r}).unlink()\nsys.exit(0)"))
    result = invoke(workspace, target="deploy", limit="node-one")
    assert result.returncode == 0, result.stderr
    assert "deployment audit unavailable" in result.stderr
    assert len([entry for entry in calls(workspace) if entry["program"] == "ansible-playbook"]) == 2
    if failure == "exit":
        environment = json.loads(environment_record.read_text())
        assert {key: environment.get(key) for key in keys} == keys
        assert environment["ENV"] == "canary" and environment["PROVIDER"] == "scaleway"
        assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "synthetic-provider-credential" not in result.stdout + result.stderr


def test_discovery_paths_are_rechecked_after_readiness(workspace):
    root = workspace["root"]
    plugin = root / "ansible/playbooks/vars_plugins"
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ssh"
    executable.write_text(executable.read_text().replace("sys.exit(0)",
        f"pathlib.Path({str(plugin)!r}).mkdir(exist_ok=True)\nsys.exit(0)"))
    result = invoke(workspace, limit="node-one")
    assert result.returncode != 0 and "unsupported Ansible discovery path" in result.stderr
    assert not any(entry["program"] == "ansible-playbook" for entry in calls(workspace))


def test_multigoal_make_keeps_source_identity_outside_controller_targets(workspace):
    root = workspace["root"]
    identity_record = root.parent / "identities.txt"
    with (root / "Makefile").open("a") as stream:
        stream.write("\nfixture-before fixture-after:\n"
                     f"\t@printf '%s %s\\n' \"$@\" \"$${{DEPLOY_SOURCE_REVISION}}\" >> '{identity_record}'\n")
    commit_fixture(workspace)
    result = subprocess.run(["make", "fixture-before", "dry-run", "deploy", "fixture-after",
                             "ANSIBLE_LIMIT=node-one", "SECRETS_FILE=" + str(workspace["secrets"])],
                            cwd=root, env=workspace["env"], text=True, capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr
    identities = [line.split() for line in identity_record.read_text().splitlines()]
    assert [line[0] for line in identities] == ["fixture-before", "fixture-after"]
    assert len(identities[0][1]) == 40 and identities[0][1] == identities[1][1]
    observed = calls(workspace)
    assert len([entry for entry in observed if entry["program"] == "ssh"]) == 2
    assert len([entry for entry in observed if entry["program"] == "ansible-playbook"]) == 3
    assert len([entry for entry in observed if entry["program"] == "audit-log.sh"]) == 1


def test_frozen_transport_is_portable_and_retains_original_host_key_identity(workspace):
    root = workspace["root"]
    overrides = write(root.parent / "overrides.yaml", "ansible_host: 198.51.100.8\nansible_port: 2022\n")
    record = root.parent / "ssh-config.json"
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ansible-playbook"
    write(executable, f"""#!{sys.executable}
import json, pathlib, shlex, subprocess, sys
loader = json.loads(pathlib.Path(sys.argv[1]).read_text())[0]
files = loader['vars']['deployment_input_files']['node-one']
transport = json.loads(pathlib.Path(files[-1]).read_text())
options = shlex.split(transport['ansible_ssh_args'])
assert all(options[index] in ('-F', '-o') for index in range(0, len(options), 2))
result = subprocess.run(['/usr/bin/ssh', '-G', *options, transport['ansible_host']],
                        text=True, capture_output=True, check=True, timeout=5)
config = dict(line.split(' ', 1) for line in result.stdout.splitlines())
pathlib.Path({str(record)!r}).write_text(json.dumps({{'config': config, 'transport': transport}}))
""", 0o700)
    result = invoke(workspace, limit="node-one", ANSIBLE_EXTRA_VARS_FILE=str(overrides))
    assert result.returncode == 0, result.stderr
    observed = json.loads(record.read_text())
    config, transport = observed["config"], observed["transport"]
    assert config["hostname"] == transport["ansible_host"] == "198.51.100.8"
    assert config["port"] == str(transport["ansible_port"]) == "2022"
    assert config["user"] == transport["ansible_user"] == "deploy"
    assert config["hostkeyalias"] == "[192.0.2.1]:2022"
    assert config["stricthostkeychecking"] == "true" and config["batchmode"] == "yes"
    assert config["identityfile"] == transport["ansible_ssh_private_key_file"]
    assert config["controlmaster"] == "false" and config["identityagent"] == "none"
    assert transport["ansible_ssh_common_args"] == transport["ansible_ssh_extra_args"] == ""
    ssh = next(entry["args"] for entry in calls(workspace) if entry["program"] == "ssh")
    assert ssh[-2] == config["hostname"] and ssh[ssh.index("-p") + 1] == config["port"]
    assert "HostKeyAlias=" + config["hostkeyalias"] in ssh
    assert "UserKnownHostsFile=" + config["userknownhostsfile"] in ssh


@pytest.mark.parametrize("interrupt", [signal.SIGTERM, signal.SIGINT])
def test_make_cancellation_reclaims_readiness_children(workspace, interrupt):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    pids = workspace["root"].parent / "pids.json"
    write(binary / "ssh", f"""#!{sys.executable}
import json, os, pathlib, subprocess, time
child = subprocess.Popen(['sleep', '60'])
record = pathlib.Path({str(pids)!r})
record.with_suffix('.tmp').write_text(json.dumps([os.getpid(), child.pid]))
record.with_suffix('.tmp').replace(record)
time.sleep(60)
""", 0o700)
    process = subprocess.Popen(["make", "dry-run", "ANSIBLE_LIMIT=node-one",
                                "SECRETS_FILE=" + str(workspace["secrets"])],
                               cwd=workspace["root"], env=workspace["env"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        deadline = time.monotonic() + 15
        while not pids.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pids.exists(), "readiness SSH did not start"
        if interrupt == signal.SIGINT:
            # Ctrl-C targets the foreground group. SIGINT sent only to Make's
            # PID is not a keyboard interrupt delivered to its recipe process.
            os.killpg(process.pid, interrupt)
        else:
            process.send_signal(interrupt)
        process.communicate(timeout=3)
        assert process.returncode != 0
        for pid in json.loads(pids.read_text()):
            result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
            assert not result.stdout.strip() or result.stdout.strip().startswith("Z"), "readiness descendant escaped"
        assert not any(entry["program"] == "ansible-playbook" for entry in calls(workspace))
    finally:
        for group in {process.pid, *(json.loads(pids.read_text())[:1] if pids.exists() else [])}:
            assert group != os.getpgrp()
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()


def install_local_ansible(workspace):
    """Run installed Ansible; fail before any accidental SSH or sudo execution."""
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ansible-playbook"
    write(executable, f"""#!{sys.executable}
import runpy
from ansible.plugins.connection.ssh import Connection
from ansible.plugins.become.sudo import BecomeModule
def forbidden(*args, **kwargs):
    raise AssertionError('fixture refuses SSH or sudo execution')
Connection._run = forbidden
BecomeModule.build_become_command = forbidden
runpy.run_module('ansible.cli.playbook', run_name='__main__')
""", 0o700)


@pytest.mark.parametrize("cohort", ["vpn-p0", "vpn-p1p2", "vpn-fullstack"])
@pytest.mark.parametrize("override", [False, True])
def test_real_ansible_preserves_profiles_types_secrets_and_local_delegation(workspace, cohort, override):
    root = workspace["root"]
    for name in ("all", "vpn", cohort):
        (root / f"ansible/group_vars/{name}.yml").write_bytes((ROOT / f"ansible/group_vars/{name}.yml").read_bytes())
    (root / "ansible/playbooks/group_vars").symlink_to("../group_vars")
    source = workspace["inventory"].read_text().replace("[vpn-p0]", "[" + cohort + "]")
    source = source.replace("provider=upcloud", "provider=upcloud allowed_ssh_cidrs='[\"198.51.100.1/32\"]'")
    source = source.replace("provider=vultr", "provider=vultr allowed_ssh_cidrs='[\"198.51.100.2/32\"]'")
    workspace["inventory"].write_text(source)
    result_file = root.parent / "actual-{{ inventory_hostname }}.json"
    play = [{"hosts": "vpn", "gather_facts": False, "become": False,
             "vars_files": ["{{ lookup('env', 'VPN_SECRETS_FILE') }}"], "tasks": [{
                 "name": "Write the effective values through actual local delegation",
                 "ansible.builtin.copy": {"dest": str(result_file), "mode": "0600", "content":
                     "{{ {'vpn': vpn, 'allowed': allowed_ssh_cidrs, 'port': ansible_port, "
                     "'address': ansible_host, 'provider': provider, 'cohorts': group_names, "
                     "'origin': public_site_canonical_url, 'secret': fixture_secret} | to_json }}"},
                 "delegate_to": "localhost", "become": False, "check_mode": False, "no_log": True}]}]
    (root / "ansible/playbooks/site.yml").write_text(yaml.safe_dump(play))
    overrides = write(root.parent / "override.yaml",
                      "public_site_canonical_url: https://fixture.example.invalid\n"
                      "ansible_host: 198.51.100.8\nansible_port: 2022\n") if override else None
    install_local_ansible(workspace)
    baseline_env = {**workspace["env"], "ANSIBLE_CONFIG": str(root / "ansible/ansible.cfg"),
                    "VPN_SECRETS_FILE": str(workspace["secrets"]), "ANSIBLE_DEBUG": "false"}
    baseline = subprocess.run(["ansible-playbook", str(root / "ansible/playbooks/site.yml"),
                               "-i", str(workspace["inventory"]),
                               *(["--limit", "node-one"] if override else []),
                               *(["--extra-vars", "@" + str(overrides)] if overrides else [])],
                              cwd=root, env=baseline_env, capture_output=True, text=True, timeout=30)
    assert baseline.returncode == 0, baseline.stderr + baseline.stdout
    expected = {path.name: json.loads(path.read_text()) for path in root.parent.glob("actual-*.json")}
    assert len(expected) == (1 if override else 2)
    for path in root.parent.glob("actual-*.json"):
        path.unlink()
    write(root / "ansible/playbooks/host_vars/node-one.yml",
          "fixture_secret: hostile-sibling-host-vars\nvpn: {enable_hysteria: hostile}\n")
    candidate = invoke(workspace, limit="node-one" if override else "",
                       **({"ANSIBLE_EXTRA_VARS_FILE": str(overrides)} if overrides else {}))
    assert candidate.returncode == 0, candidate.stderr + candidate.stdout
    assert {path.name: json.loads(path.read_text()) for path in root.parent.glob("actual-*.json")} == expected
    assert "synthetic-private-value" not in candidate.stdout + candidate.stderr


@pytest.mark.parametrize("playbook_plugin", [False, True])
def test_real_ansible_excludes_ambient_legacy_vars_plugin_and_host_vars(workspace, playbook_plugin):
    root = workspace["root"]
    marker = root.parent / "legacy-plugin-executed"
    collections = root / ".ansible/collections"
    write(collections / "ansible_collections/fixture/reviewed/plugins/filter/identity.py",
          "class FilterModule:\n    def filters(self):\n"
          "        return {'identity': lambda value: value + '-reviewed-collection'}\n")
    plugin_dir = workspace["home"] / ".ansible/plugins/vars"
    write(plugin_dir / "ambient.py", f"""from pathlib import Path
from ansible.plugins.vars import BaseVarsPlugin
class VarsModule(BaseVarsPlugin):
    REQUIRES_ENABLED = False
    def get_vars(self, loader, path, entities, cache=True):
        Path({str(marker)!r}).write_text('executed')
        return {{'fixture_poison': 'ambient-authority'}}
""")
    write(root / "ansible/playbooks/host_vars/node-one.yml", "fixture_poison: sibling-host-vars\n")
    write(root / "ansible/playbooks/site.yml", "- hosts: vpn\n  gather_facts: false\n  tasks:\n"
          "    - name: Observe actual variable loading\n      ansible.builtin.debug:\n"
          "        msg: \"{{ (fixture_poison | default('clean')) | fixture.reviewed.identity }}\"\n")
    install_local_ansible(workspace)
    baseline_environment = {**workspace["env"], "ANSIBLE_CONFIG": str(root / "ansible/ansible.cfg"),
                            "ANSIBLE_VARS_PLUGINS": str(plugin_dir), "ANSIBLE_COLLECTIONS_PATH": str(collections)}
    baseline = subprocess.run(["ansible-playbook", str(root / "ansible/playbooks/site.yml"),
                               "-i", str(workspace["inventory"])], cwd=root,
                              env=baseline_environment, text=True, capture_output=True, timeout=30)
    assert baseline.returncode == 0, baseline.stderr + baseline.stdout
    assert marker.exists(), "control must demonstrate the actual installed legacy plugin executes"
    marker.unlink()
    if playbook_plugin:
        write(root / "ansible/playbooks/vars_plugins/ambient.py", (plugin_dir / "ambient.py").read_text())
    workspace["env"]["ANSIBLE_VARS_PLUGINS"] = str(plugin_dir)
    workspace["env"]["ANSIBLE_CONFIG"] = str(root.parent / "untrusted.cfg")
    write(root.parent / "untrusted.cfg", "[defaults]\ndebug=True\n")
    workspace["env"]["AWS_SECRET_ACCESS_KEY"] = "synthetic-provider-credential"
    result = invoke(workspace, limit="node-one")
    assert not marker.exists()
    if playbook_plugin:
        assert result.returncode != 0 and "unsupported Ansible discovery path" in result.stderr
        assert not any(entry["program"] == "ssh" for entry in calls(workspace))
        return
    assert result.returncode == 0, result.stderr + result.stdout
    assert '"msg": "clean-reviewed-collection"' in result.stdout
    assert "ambient-authority" not in result.stdout and "sibling-host-vars" not in result.stdout
    assert "synthetic-provider-credential" not in result.stdout + result.stderr


@pytest.mark.parametrize("relative", ["ansible/playbooks/vars_plugins",
                                      "ansible/playbooks/module_utils",
                                      "ansible/playbooks/roles",
                                      "ansible/roles/fixture-role/filter_plugins"])
def test_autoload_paths_and_dangling_links_refuse_before_ssh(workspace, relative):
    target = workspace["root"] / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(workspace["root"].parent / "absent-plugin-directory", target_is_directory=True)
    result = invoke(workspace)
    assert result.returncode != 0 and "unsupported Ansible discovery path" in result.stderr
    assert calls(workspace) == []


def test_generated_wrapper_accepts_all_canonical_roles_in_real_ansible_syntax_check(workspace):
    root = workspace["root"]
    for name in ("roles", "group_vars", "templates"):
        shutil.copytree(ROOT / "ansible" / name, root / "ansible" / name, dirs_exist_ok=True, symlinks=True)
    for name in ("site.yml", "source-drift.yml"):
        shutil.copyfile(ROOT / "ansible/playbooks" / name, root / "ansible/playbooks" / name)
    shutil.copyfile(ROOT / "ansible/role-tiers.yml", root / "ansible/role-tiers.yml")
    workspace["secrets"].write_bytes((ROOT / "tests/fixtures/secrets-sample.yml").read_bytes())
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ansible-playbook"
    actual_ansible = shutil.which("ansible-playbook")
    assert actual_ansible, "the installed pinned Ansible is required"
    write(executable, f"""#!{sys.executable}
import os, sys
os.execv({actual_ansible!r}, [{actual_ansible!r}, *sys.argv[1:], '--syntax-check'])
""", 0o700)
    result = invoke(workspace)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "playbook:" in result.stdout
