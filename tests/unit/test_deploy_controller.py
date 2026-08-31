"""Deploy controller behavior through Make, private files and real Ansible.

SSH/Ansible executables in the orchestration fixture record calls instead of
contacting hosts. Separate parity cases use the installed Ansible locally.
"""

import contextlib
import ast
import hashlib
import json
import os
from pathlib import Path
import re
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
    for name in ("fleet_inspection.py", "deploy-source-identity.sh", "sshd_bundle_source.py", "sshd_contexts.py",
                 "sshd_transaction_limits.py",
                 "validate-ansible-extra-vars.py", "deploy-controller.py", "bootstrap_readiness.py",
                 "network-exposure-gate.py"):
        source = ROOT / "scripts" / name
        if source.exists():
            target = root / "scripts" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
    for name in ("sshd_migrate.py", "sshd_transaction.py", "sshd_ownership.py"):
        source = ROOT / "ansible/roles/baseline/files" / name
        target = root / "ansible/roles/baseline/files" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for name in ("vpn-sshd-boot-recover.service", "vpn-sshd-recover.service",
                 "vpn-sshd-recover.timer"):
        source = ROOT / "ansible/roles/baseline/templates" / name
        target = root / "ansible/roles/baseline/templates" / name
        target.parent.mkdir(parents=True, exist_ok=True)
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
                      "node-one ansible_host=192.0.2.1 ansible_user=deploy ansible_port=2222 provider=upcloud env=prod "
                      "inspection_transport_host=100.64.0.1 inspection_host_key_alias=192.0.2.1\n"
                      "node-two ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22 provider=vultr env=prod "
                      "inspection_transport_host=100.64.0.2 inspection_host_key_alias=192.0.2.2\n"
                      "[vpn-p0]\nnode-one\n[vpn-p1p2]\nnode-two\n"
                      f"[vpn:vars]\nansible_ssh_private_key_file={key}\nansible_python_interpreter=/usr/bin/python3\n")
    secrets = write(tmp_path.resolve() / "secrets.yaml", "fixture_secret: synthetic-private-value\n")
    context_pairs = {}
    for name, public, management, port in (
            ("node-one", "192.0.2.1", "100.64.0.1", 2222),
            ("node-two", "192.0.2.2", "100.64.0.2", 22)):
        context = {"user": "deploy", "host": name, "addr": "198.51.100.44",
                   "laddr": public, "lport": port}
        context_pairs[name] = [context, {**context, "addr": "100.64.0.44", "laddr": management}]
    contexts = write(tmp_path.resolve() / "ssh-contexts.json", "{}\n")
    promotion = write(tmp_path.resolve() / "promotion.json", "{}\n")
    calls = tmp_path.resolve() / "calls.jsonl"
    binary = tmp_path.resolve() / "bin"
    binary.mkdir()
    # These transport boundaries never inspect real keys, connect to hosts or
    # run runtime playbooks. Paths are fixed inside this fixture's scripts.
    program = f"""#!{sys.executable}
import json, os, pathlib, sys
with pathlib.Path({str(calls)!r}).open('a') as stream:
    stream.write(json.dumps({{'program': pathlib.Path(sys.argv[0]).name, 'args': sys.argv[1:],
        'tailnet_auth': 'present' if 'TAILSCALE_AUTH_KEY' in os.environ else 'absent'}}) + '\\n')
if pathlib.Path(sys.argv[0]).name == 'ansible-inventory':
    print(json.dumps({{'vpn': {{'hosts': ['node-one', 'node-two']}}}}))
sys.exit(0)
"""
    for name in ("ssh", "ansible-playbook", "ansible-inventory"):
        write(binary / name, program, 0o700)
    for name in ("validate-secrets.py", "spot-check-secrets.py", "check-certs.sh", "audit-log.sh"):
        write(root / "scripts" / name, program, 0o700)
    write(root / "scripts/sshd-promotion-proof.py", program.replace(
        "sys.exit(0)", """
if pathlib.Path(sys.argv[0]).name == 'sshd-promotion-proof.py':
    config = json.loads(pathlib.Path(sys.argv[sys.argv.index('--config') + 1]).read_text())
    sys.exit(2 if config.get('fixture') == 'reject' else 0)
sys.exit(0)
"""), 0o700)
    write(root / ".gitignore", "ansible/inventory/\n__pycache__/\n")
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("ANSIBLE_", "GIT_", "DEPLOY_", "BACKUP_"))
                   and k not in ("SKIP_PRECHECK", "MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "HOSTS", "COHORTS")}
    environment.update(HOME=str(home), PATH=str(binary) + os.pathsep + os.environ["PATH"],
                       INSPECT_KNOWN_HOSTS=str(known_hosts),
                       DEPLOY_SSH_CONTEXTS_FILE=str(contexts),
                       DEPLOY_PROMOTION_CONFIG_FILE=str(promotion))
    for command in (["git", "init", "-q"], ["git", "config", "user.name", "Deploy fixture"],
                    ["git", "config", "user.email", "fixture@example.invalid"],
                    ["git", "add", "."], ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "test: fixture source"]):
        subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    source_digest = subprocess.run([str(root / "scripts/deploy-source-identity.sh"), "--digest"],
                                   cwd=root, env=environment, text=True,
                                   capture_output=True, check=True).stdout.strip()
    return {"root": root, "home": home, "inventory": inventory, "key": key,
            "context_pairs": context_pairs,
            "contexts": contexts, "known_hosts": known_hosts, "secrets": secrets,
            "calls": calls, "env": environment, "source_digest": source_digest}


def set_contexts(workspace, limit, context_pairs=None):
    selected = ({"node-one"} if limit in {"node-one", "vpn-p0"}
                else {"node-two"} if limit in {"node-two", "vpn-p1p2"}
                else {"node-one", "node-two"})
    pairs = context_pairs or workspace["context_pairs"]
    workspace["contexts"].write_text(json.dumps({name: pairs[name] for name in sorted(selected)}) + "\n")
    digest = workspace["source_digest"]
    addresses = {"node-one": "192.0.2.1", "node-two": "192.0.2.2"}
    Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"]).write_text(json.dumps({
        name: {"schema_version": 1, "fixture": name, "target_identity": {
            "inventory_alias": name,
            "public_service_address_sha256": hashlib.sha256(addresses[name].encode()).hexdigest(),
            "deployable_digest": digest,
        }} for name in sorted(selected)}) + "\n")


def invoke(workspace, target="dry-run", limit="", context_pairs=None, **values):
    set_contexts(workspace, limit, context_pairs)
    arguments = {"ANSIBLE_LIMIT": limit, "SECRETS_FILE": str(workspace["secrets"]), **values}
    return subprocess.run(["make", target, *(f"{key}={value}" for key, value in arguments.items())],
                          cwd=workspace["root"], env=workspace["env"], text=True,
                          capture_output=True, timeout=25)


def calls(workspace):
    path = workspace["calls"]
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def network_exposure_override(workspace, *, mode="canary"):
    artifact = write(workspace["root"].parent / "reviewed-policy.json", "synthetic signed policy\n")
    key = write(workspace["root"].parent / "reviewed-key.pem", "synthetic public key\n")
    promoted = mode in {"canary", "enforce"}
    value = {"network_exposure_gate": {
        "mode": mode, "artifact": str(artifact), "trusted_key": str(key),
        "trusted_key_sha256": "a" * 64, "source_id": "reviewed-source",
        "promotion_approved": promoted, "promotion_digest": "b" * 64 if promoted else "",
        "authorized_hosts": ["node-one"] if promoted else [],
    }}
    override = write(workspace["root"].parent / "network-exposure.yml", yaml.safe_dump(value))
    return override, artifact, key


def assert_recovery_preflight(entry, address):
    """Identify the exact read-only recovery gate without relaxing call ordering."""
    assert entry["program"] == "ssh"
    assert entry["args"][-2] == address
    remote = entry["args"][-1]
    for predicate in (
        'root=/usr/local/lib/vpn-sshd',
        'state=/var/lib/vpn-sshd-transaction',
        '/usr/bin/readlink -f "$root/current/sshd_migrate.py"',
        '[ "$migrate" = "$root/generations/$generation/sshd_migrate.py" ]',
        '[ "${#generation}" -eq 64 ]',
        'case "$generation" in *[!0-9a-f]*) exit 40;; esac',
        '/usr/bin/sudo -n /usr/bin/test -d "$state"',
        '/usr/bin/sudo -n /usr/bin/test ! -L "$state"',
        "stat -c '%u:%g:%a' \"$state\")\" = 0:0:700",
        '/usr/bin/sudo -n /usr/bin/test -f "$state/transaction.lock"',
        '/usr/bin/sudo -n /usr/bin/test ! -L "$state/transaction.lock"',
        "stat -c '%u:%g:%a' \"$state/transaction.lock\")\" = 0:0:600",
        '"$root/sshd_bundle.py" status',
        'check-installation',
        'sys.stdin.buffer.read(4097)',
    ):
        assert predicate in remote
    assert re.search(r'\[ "\$generation" = "[0-9a-f]{64}" \]', remote)


def assert_bootstrap_readiness(entry, address):
    assert entry["program"] == "ssh"
    assert entry["args"][-2] == address
    remote = entry["args"][-1]
    assert "cloud-init status --wait" in remote
    assert "/var/lib/cloud-init-vpn-bootstrap.done" in remote


def test_restore_runtime_secrets_reach_the_first_tagged_deploy(workspace):
    """Real Make/decrypt/controller; only SOPS, checks and transport are fixtures."""
    import hashlib

    root = workspace["root"]
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    plaintext = workspace["secrets"].read_bytes()
    runtime = root.parent / "restore runtime"
    source = runtime / "vpn-prod.secrets.yaml"
    encrypted = write(root.parent / "restore.sops.yaml", "synthetic encrypted fixture\n")
    shutil.copy2(ROOT / "scripts/decrypt-secrets.sh", root / "scripts/decrypt-secrets.sh")
    write(binary / "sops", f"""#!{sys.executable}
import json, pathlib, sys
assert sys.argv[1:] == ['--decrypt', {str(encrypted)!r}]
with pathlib.Path({str(workspace['calls'])!r}).open('a') as stream:
    stream.write(json.dumps({{'program': 'sops'}}) + '\\n')
sys.stdout.buffer.write({plaintext!r})
""", 0o700)
    recorder = f"""#!{sys.executable}
import hashlib, json, os, pathlib, stat, sys
name = pathlib.Path(sys.argv[0]).name
secret = pathlib.Path(os.environ['VPN_SECRETS_FILE'])
record = {{'program': name, 'args': sys.argv[1:], 'secret': str(secret),
          'mode': stat.S_IMODE(secret.stat().st_mode),
          'digest': hashlib.sha256(secret.read_bytes()).hexdigest()}}
if name == 'validate-secrets.py':
    assert sys.argv[1:] == [str(secret), '--strict']
if name == 'ansible-playbook':
    play = json.loads(pathlib.Path(sys.argv[1]).read_text())
    assert all(str(secret) in files for files in play[0]['vars']['deployment_input_files'].values())
    record['play'] = pathlib.Path(play[-1]['import_playbook']).stem
with pathlib.Path({str(workspace['calls'])!r}).open('a') as stream:
    stream.write(json.dumps(record) + '\\n')
"""
    for name in ("validate-secrets.py", "spot-check-secrets.py", "check-certs.sh"):
        write(root / "scripts" / name, recorder, 0o700)
    write(binary / "ansible-playbook", recorder, 0o700)
    commit_fixture(workspace)
    environment = {key: value for key, value in workspace["env"].items()
                   if key not in ("SECRETS_FILE", "SKIP_PRECHECK")}
    common = ["ENV=prod", "RUNTIME_DIR=" + str(runtime)]
    deploy = ["make", "deploy", *common, "ANSIBLE_LIMIT=node-one",
              "ANSIBLE_TAGS=baseline,firewall,backup"]
    set_contexts(workspace, "node-one")

    missing = subprocess.run(deploy, cwd=root, env=environment, capture_output=True, text=True, timeout=25)
    assert missing.returncode != 0
    assert calls(workspace) == [], "plaintext must exist before checks, SSH or site execution"
    decrypted = subprocess.run(["make", "decrypt", *common, "SOPS_FILE=" + str(encrypted)],
                               cwd=root, env=environment, capture_output=True, text=True, timeout=25)
    assert decrypted.returncode == 0, decrypted.stderr
    assert source.read_bytes() == plaintext and source.stat().st_mode & 0o777 == 0o600
    result = subprocess.run(deploy, cwd=root, env=environment, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr
    observed = calls(workspace)
    assert [entry["program"] for entry in observed] == [
        "sops", "sshd-promotion-proof.py", "validate-secrets.py", "spot-check-secrets.py", "check-certs.sh", "ssh",
        "ssh", "ansible-playbook", "ansible-playbook", "audit-log.sh"]
    assert_bootstrap_readiness(observed[5], "100.64.0.1")
    assert_recovery_preflight(observed[6], "100.64.0.1")
    consumers = [entry for entry in observed if "secret" in entry]
    snapshot = Path(consumers[0]["secret"])
    assert snapshot != source
    assert all(entry["secret"] == str(snapshot) and entry["mode"] == 0o600
               and entry["digest"] == hashlib.sha256(plaintext).hexdigest() for entry in consumers)
    plays = [entry for entry in observed if entry["program"] == "ansible-playbook"]
    assert [entry["play"] for entry in plays] == ["site", "source-drift"]
    assert plays[0]["args"][-2:] == ["--tags", "baseline,firewall,backup"]
    assert "--tags" not in plays[1]["args"]
    assert not snapshot.exists(), "private controller snapshot must be removed"
    assert source.read_bytes() == plaintext and source.stat().st_mode & 0o777 == 0o600
    assert "synthetic-private-value" not in (
        missing.stdout + missing.stderr + decrypted.stdout + decrypted.stderr + result.stdout + result.stderr)


@pytest.mark.parametrize("limit,expected", [
    ("", ["100.64.0.1", "100.64.0.2"]),
    ("node-one", ["100.64.0.1"]),
    ("vpn-p1p2", ["100.64.0.2"]),
    ("vpn-p0,node-two", ["100.64.0.1", "100.64.0.2"]),
])
def test_make_waits_for_exact_inventory_subset_before_ansible(workspace, limit, expected):
    result = invoke(workspace, limit=limit)
    assert result.returncode == 0, result.stderr
    observed = calls(workspace)
    ssh = [entry for entry in observed if entry["program"] == "ssh"]
    assert [entry["args"][-2] for entry in ssh] == [address for address in expected for _ in range(2)]
    serial = [entry for entry in observed if entry["program"] in {"ssh", "ansible-playbook"}]
    assert [entry["program"] for entry in serial] == [item for _ in expected
                                                       for item in ("ssh", "ssh", "ansible-playbook")]
    for index, address in enumerate(expected):
        readiness, recovery, _ansible = serial[index * 3:(index + 1) * 3]
        assert_bootstrap_readiness(readiness, address)
        assert_recovery_preflight(recovery, address)
    play = next(index for index, entry in enumerate(observed) if entry["program"] == "ansible-playbook")
    assert not any(entry["program"] == "ansible-inventory" for entry in observed)
    assert "--check" in observed[play]["args"] and "--diff" in observed[play]["args"]


@pytest.mark.parametrize("target", ["deploy", "dry-run"])
def test_deploy_refuses_missing_recovery_foundation_before_ansible(workspace, target):
    """A fresh node must use the explicit installer before ordinary site writes."""
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ssh"
    executable.write_text(executable.read_text().replace(
        "sys.exit(0)",
        "sys.exit(42 if 'sshd_bundle.py' in sys.argv[-1] and ' status ' in sys.argv[-1] else 0)",
    ))
    result = invoke(workspace, target=target, limit="node-one")
    assert result.returncode != 0 and "SSH recovery foundation unavailable" in result.stderr
    assert "nonce" not in result.stdout + result.stderr
    observed = calls(workspace)
    recovery = [entry for entry in observed if entry["program"] == "ssh"
                and "sshd_bundle.py" in entry["args"][-1] and " status " in entry["args"][-1]]
    assert len(recovery) == 1
    assert not any(entry["program"] in {"ansible-playbook", "audit-log.sh"} for entry in observed)


@pytest.mark.parametrize("target", ["deploy", "dry-run"])
def test_recovery_status_documents_drive_fail_closed_controller_order(workspace, target):
    terminal = {"generation": "1d34d0a4-6be7-4b09-b169-47e819ef2a0c", "nonce": "a" * 64,
                "deadline": 123, "snapshot_digest": "b" * 64}
    cases = (
        (b'{"status":"idle"}\n', True),
        (json.dumps({**terminal, "status": "committed"}).encode(), True),
        (json.dumps({**terminal, "status": "rolled_back"}).encode(), True),
        (b'{"status":"prepared"}', False),
        (b'{"status":"applying"}', False),
        (b'{"status":"applied"}', False),
        (b'{"status":"unknown"}', False),
        (b'not-json', False),
        (b'x' * 4097, False),
    )
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ssh"
    original = executable.read_text()
    for payload, accepted in cases:
        if workspace["calls"].exists():
            workspace["calls"].unlink()
        executable.write_text(original.replace("sys.exit(0)", f"""
if 'sshd_bundle.py' in sys.argv[-1] and ' status ' in sys.argv[-1]:
    import shlex, subprocess
    command = shlex.split(sys.argv[-1].split('|', 1)[1])[:5]
    sys.exit(subprocess.run(command, input={payload!r}).returncode)
sys.exit(0)
"""))
        result = invoke(workspace, target=target, limit="node-one")
        observed = calls(workspace)
        if accepted:
            assert result.returncode == 0, result.stderr
            assert any(entry["program"] == "ansible-playbook" for entry in observed)
        else:
            assert result.returncode != 0
            assert "SSH recovery foundation unavailable" in result.stderr
            assert not any(entry["program"] in {"ansible-playbook", "audit-log.sh"} for entry in observed)
        assert "nonce" not in result.stdout + result.stderr


def test_recovery_preflight_parses_bounded_terminal_or_idle_status(workspace):
    result = invoke(workspace, limit="node-one")
    assert result.returncode == 0, result.stderr
    recovery = next(entry for entry in calls(workspace)
                    if entry["program"] == "ssh" and "sshd_bundle.py" in entry["args"][-1])
    remote = recovery["args"][-1]
    assert "sys.stdin.buffer.read(4097)" in remote
    assert "idle" in remote and "committed" in remote and "rolled_back" in remote
    assert '"$root/sshd_bundle.py" status >/dev/null' not in remote


@pytest.mark.parametrize("payload,accepted", [
    (b'{"status":"idle"}\n', True),
    (json.dumps({"generation": "1d34d0a4-6be7-4b09-b169-47e819ef2a0c", "nonce": "a" * 64,
                 "status": "committed", "deadline": 123, "snapshot_digest": "b" * 64}).encode(), True),
    (json.dumps({"generation": "1d34d0a4-6be7-4b09-b169-47e819ef2a0c", "nonce": "a" * 64,
                 "status": "rolled_back", "deadline": 123, "snapshot_digest": "b" * 64}).encode(), True),
    (b'{"status":"prepared"}', False),
    (b'{"status":"applying"}', False),
    (b'{"status":"applied"}', False),
    (b'{"status":"unknown"}', False),
    (b'{"status":"idle","status":"idle"}', False),
    (b'{"generation":7,"nonce":"bad","status":"committed","deadline":true,"snapshot_digest":null}', False),
    (b'not-json', False),
    (b'x' * 4097, False),
])
def test_recovery_status_validator_accepts_only_strict_terminal_or_idle_schema(payload, accepted):
    tree = ast.parse((ROOT / "scripts/deploy-controller.py").read_text())
    validator = next(ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "RECOVERY_STATUS_VALIDATOR"
                             for target in node.targets))
    result = subprocess.run([sys.executable, "-I", "-B", "-c", validator], input=payload,
                            capture_output=True, timeout=5)
    assert (result.returncode == 0) is accepted
    assert result.stdout == b"" and result.stderr == b""


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


@pytest.mark.parametrize("field,target", [
    ("ANSIBLE_LIMIT", "dry-run"), ("SECRETS_FILE", "dry-run"),
    ("ANSIBLE_EXTRA_VARS_FILE", "dry-run"), ("INSPECT_KNOWN_HOSTS", "dry-run"),
    ("DEPLOY_SSH_CONTEXTS_FILE", "dry-run"), ("DEPLOY_PROMOTION_CONFIG_FILE", "deploy"),
])
def test_make_inputs_do_not_expand_make_functions(workspace, field, target):
    marker = workspace["root"].parent / "expanded"
    result = invoke(workspace, target=target, limit="node-one",
                    **{field: "$(shell touch " + str(marker) + ")"})
    assert result.returncode != 0
    assert not marker.exists()
    assert not any(entry["program"] in ("ssh", "ansible-playbook") for entry in calls(workspace))


@pytest.mark.parametrize("target", ["deploy", "dry-run"])
def test_make_refuses_command_line_tailnet_credential_before_expansion(
    workspace, target
):
    marker = workspace["root"].parent / "tailnet-credential-expanded"
    result = invoke(
        workspace,
        target=target,
        limit="node-one",
        TAILSCALE_AUTH_KEY="$(shell touch " + str(marker) + ")",
    )
    assert result.returncode != 0
    assert "must come from the environment" in result.stderr
    assert not marker.exists()
    assert calls(workspace) == []


def test_tailnet_credential_reaches_only_one_node_site_playbook(workspace):
    workspace["env"]["TAILSCALE_AUTH_KEY"] = "tskey-auth-fixture_12345678"
    result = invoke(workspace, target="deploy", limit="node-one")

    assert result.returncode == 0, result.stderr
    observed = calls(workspace)
    site = [
        entry
        for entry in observed
        if entry["program"] == "ansible-playbook"
        and Path(entry["args"][0]).stem.endswith("-site")
    ]
    assert len(site) == 1 and site[0]["tailnet_auth"] == "present"
    assert all(
        entry["tailnet_auth"] == "absent"
        for entry in observed
        if entry not in site
    )


def test_dry_run_never_forwards_ambient_tailnet_credential(workspace):
    workspace["env"]["TAILSCALE_AUTH_KEY"] = "tskey-auth-fixture_12345678"
    result = invoke(workspace, target="dry-run", limit="node-one")

    assert result.returncode == 0, result.stderr
    assert all(entry["tailnet_auth"] == "absent" for entry in calls(workspace))


@pytest.mark.parametrize(
    "credential,limit",
    [
        ("invalid", "node-one"),
        ("tskey-auth-fixture_12345678", ""),
    ],
)
def test_tailnet_credential_refuses_invalid_or_multi_node_use_before_ssh(
    workspace, credential, limit
):
    workspace["env"]["TAILSCALE_AUTH_KEY"] = credential
    result = invoke(workspace, target="deploy", limit=limit)

    assert result.returncode != 0
    assert "Tailnet enrollment credential invalid" in result.stderr
    assert not any(entry["program"] in ("ssh", "ansible-playbook") for entry in calls(workspace))


@pytest.mark.parametrize("field", ["ENV", "PROVIDER"])
@pytest.mark.parametrize("target", ["deploy", "backup-configure", "install-ssh-recovery"])
def test_make_labels_do_not_expand_before_controller_privacy_guard(workspace, field, target):
    marker = workspace["root"].parent / "early-label-expansion"
    workspace["env"]["ANSIBLE_DEBUG"] = "true"
    controller = {"backup-configure": "backup-configure.py",
                  "install-ssh-recovery": "install-sshd-recovery.py"}.get(target)
    if controller:
        shutil.copy2(ROOT / "scripts" / controller, workspace["root"] / "scripts" / controller)
    result = invoke(workspace, target=target, limit="node-one", SSH_RECOVERY_EXCLUSIVE_WINDOW="1",
                    **{field: "$(shell touch " + str(marker) + ")"})
    assert result.returncode != 0
    if target == "install-ssh-recovery":
        assert json.loads(result.stdout)["reason"] == "ssh-recovery-install-failed"
    else:
        message = "ansible-debug-not-supported" if target == "backup-configure" else "debug is not supported"
        assert message in result.stderr
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


@pytest.mark.parametrize("fault", ["artifact-mode", "artifact-symlink", "key-mode", "key-symlink"])
def test_network_exposure_inputs_refuse_before_transport_or_audit(workspace, fault):
    override, artifact, key = network_exposure_override(workspace)
    target = artifact if fault.startswith("artifact-") else key
    if fault.endswith("mode"):
        target.chmod(0o640)
    else:
        replacement = target.with_suffix(target.suffix + ".replacement")
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o600)
        target.unlink()
        target.symlink_to(replacement)
    result = invoke(workspace, target="dry-run", limit="node-one",
                    ANSIBLE_EXTRA_VARS_FILE=str(override))
    assert result.returncode != 0
    assert not any(entry["program"] in {"ssh", "ansible-playbook", "audit-log.sh"}
                   for entry in calls(workspace))


@pytest.mark.parametrize("mode,target", [
    ("log_only", "dry-run"), ("canary", "deploy"), ("enforce", "deploy"),
])
def test_network_exposure_inputs_are_snapshotted_for_exact_selected_host(
        workspace, mode, target):
    override, artifact, key = network_exposure_override(workspace, mode=mode)
    root, call_record = workspace["root"], workspace["calls"]
    write(root / "scripts/network-exposure-gate.py", f"""#!{sys.executable}
import json, pathlib, stat, sys
artifact = pathlib.Path(sys.argv[sys.argv.index('--artifact') + 1])
key = pathlib.Path(sys.argv[sys.argv.index('--trusted-key') + 1])
assert artifact.read_text() == 'synthetic signed policy\\n'
assert key.read_text() == 'synthetic public key\\n'
assert stat.S_IMODE(artifact.stat().st_mode) == stat.S_IMODE(key.stat().st_mode) == 0o600
assert artifact != pathlib.Path({str(artifact)!r}) and key != pathlib.Path({str(key)!r})
with pathlib.Path({str(call_record)!r}).open('a') as stream:
    stream.write(json.dumps({{'program': 'network-exposure-gate.py', 'args': sys.argv[1:],
                             'artifact': str(artifact), 'key': str(key)}}) + '\\n')
print(json.dumps({{'summary': {{'validation': 'valid'}}, 'plan': {{}}}}))
""", 0o700)
    ansible_record = root.parent / "network-exposure-ansible.json"
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    write(binary / "ansible-playbook", f"""#!{sys.executable}
import json, pathlib, stat, sys, yaml
play = json.loads(pathlib.Path(sys.argv[1]).read_text())
files = play[0]['vars']['deployment_input_files']['node-one']
override = next(pathlib.Path(path) for path in files if pathlib.Path(path).name.endswith('-overrides.yml'))
gate = yaml.safe_load(override.read_text())['network_exposure_gate']
artifact = pathlib.Path(gate['artifact'])
key = pathlib.Path(gate['trusted_key'])
pathlib.Path({str(ansible_record)!r}).write_text(json.dumps({{
    'gate': gate, 'override_mode': stat.S_IMODE(override.stat().st_mode),
    'artifact_mode': stat.S_IMODE(artifact.stat().st_mode),
    'key_mode': stat.S_IMODE(key.stat().st_mode),
    'artifact_bytes': artifact.read_text(), 'key_bytes': key.read_text(),
}}))
""", 0o700)
    commit_fixture(workspace)
    result = invoke(workspace, target=target, limit="node-one",
                    ANSIBLE_EXTRA_VARS_FILE=str(override))
    assert result.returncode == 0, result.stderr
    observed = calls(workspace)
    gate_call = next(entry for entry in observed if entry["program"] == "network-exposure-gate.py")
    first_transport = next(index for index, entry in enumerate(observed)
                           if entry["program"] in {"ssh", "ansible-playbook"})
    assert observed.index(gate_call) < first_transport
    assert gate_call["args"][gate_call["args"].index("--inventory-host") + 1] == "node-one"
    loaded = json.loads(ansible_record.read_text())
    assert loaded["override_mode"] == loaded["artifact_mode"] == loaded["key_mode"] == 0o600
    assert loaded["artifact_bytes"] == "synthetic signed policy\n"
    assert loaded["key_bytes"] == "synthetic public key\n"
    assert loaded["gate"]["mode"] == mode
    assert loaded["gate"]["authorized_hosts"] == (["node-one"] if mode in {"canary", "enforce"} else [])
    assert Path(loaded["gate"]["artifact"]) != artifact
    assert Path(loaded["gate"]["trusted_key"]) != key
    assert not Path(loaded["gate"]["artifact"]).exists()
    assert not Path(loaded["gate"]["trusted_key"]).exists()


def test_network_exposure_source_replacement_refuses_after_validation_before_ssh(workspace):
    override, artifact, _key = network_exposure_override(workspace)
    root = workspace["root"]
    replacement = artifact.with_suffix(".replacement")
    replacement.write_text("replaced signed policy\n")
    replacement.chmod(0o600)
    write(root / "scripts/network-exposure-gate.py", f"""#!{sys.executable}
import os
os.replace({str(replacement)!r}, {str(artifact)!r})
print('{{"summary": {{"validation": "valid"}}, "plan": {{}}}}')
""", 0o700)
    result = invoke(workspace, target="dry-run", limit="node-one",
                    ANSIBLE_EXTRA_VARS_FILE=str(override))
    assert result.returncode != 0
    assert not any(entry["program"] in {"ssh", "ansible-playbook", "audit-log.sh"}
                   for entry in calls(workspace))


def test_network_exposure_promotion_must_equal_exact_inventory_selection(workspace):
    override, _artifact, _key = network_exposure_override(workspace)
    document = yaml.safe_load(override.read_text())
    document["network_exposure_gate"]["authorized_hosts"] = ["node-two"]
    override.write_text(yaml.safe_dump(document))
    override.chmod(0o600)
    result = invoke(workspace, target="deploy", limit="node-one",
                    ANSIBLE_EXTRA_VARS_FILE=str(override))
    assert result.returncode != 0
    assert not any(entry["program"] in {"ssh", "ansible-playbook", "audit-log.sh"}
                   for entry in calls(workspace))


@pytest.mark.parametrize("fault", ["contexts-mode", "contexts-selection", "contexts-value",
                                    "contexts-port", "contexts-duplicate",
                                    "promotion-mode", "promotion-selection", "promotion-duplicate"])
def test_transaction_inputs_are_validated_before_first_ssh(workspace, fault):
    target = "deploy" if fault.startswith("promotion-") else "dry-run"
    set_contexts(workspace, "node-one")
    if fault == "contexts-mode":
        workspace["contexts"].chmod(0o640)
    elif fault == "contexts-selection":
        workspace["contexts"].write_text(json.dumps({
            "node-two": workspace["context_pairs"]["node-two"]}) + "\n")
    elif fault == "contexts-value":
        invalid = [dict(item) for item in workspace["context_pairs"]["node-one"]]
        invalid[1]["lport"] = True
        workspace["contexts"].write_text(json.dumps({"node-one": invalid}) + "\n")
    elif fault == "contexts-port":
        invalid = [dict(item, lport=22) for item in workspace["context_pairs"]["node-one"]]
        workspace["contexts"].write_text(json.dumps({"node-one": invalid}) + "\n")
    elif fault == "contexts-duplicate":
        pair = json.dumps(workspace["context_pairs"]["node-one"])
        workspace["contexts"].write_text('{"node-one":' + pair + ',"node-one":' + pair + '}\n')
    elif fault == "promotion-mode":
        Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"]).chmod(0o640)
    elif fault == "promotion-selection":
        Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"]).write_text(json.dumps({
            "node-two": {"schema_version": 1, "fixture": "node-two"}}) + "\n")
    else:
        promotion = Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"])
        promotion.write_text(promotion.read_text().replace(
            '"fixture": "node-one"', '"fixture": "node-one", "fixture": "reject"'))
    result = subprocess.run(["make", target, "ANSIBLE_LIMIT=node-one",
                             "SECRETS_FILE=" + str(workspace["secrets"])],
                            cwd=workspace["root"], env=workspace["env"],
                            text=True, capture_output=True, timeout=25)
    assert result.returncode != 0
    assert not any(entry["program"] in {"ssh", "ansible-playbook"} for entry in calls(workspace))


def test_swapped_valid_promotion_configs_refuse_before_validation_or_ssh(workspace):
    set_contexts(workspace, "")
    promotion = Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"])
    value = json.loads(promotion.read_text())
    value["node-one"]["target_identity"], value["node-two"]["target_identity"] = (
        value["node-two"]["target_identity"], value["node-one"]["target_identity"])
    promotion.write_text(json.dumps(value) + "\n")
    result = subprocess.run(["make", "deploy", "SECRETS_FILE=" + str(workspace["secrets"])],
                            cwd=workspace["root"], env=workspace["env"],
                            text=True, capture_output=True, timeout=25)
    assert result.returncode != 0
    assert calls(workspace) == []


def test_all_promotion_configs_are_validated_before_first_ssh(workspace):
    set_contexts(workspace, "")
    promotion = Path(workspace["env"]["DEPLOY_PROMOTION_CONFIG_FILE"])
    value = json.loads(promotion.read_text())
    value["node-two"]["fixture"] = "reject"
    promotion.write_text(json.dumps(value) + "\n")
    result = subprocess.run(["make", "deploy", "SECRETS_FILE=" + str(workspace["secrets"])],
                            cwd=workspace["root"], env=workspace["env"],
                            text=True, capture_output=True, timeout=25)
    assert result.returncode != 0
    observed = calls(workspace)
    assert [entry["program"] for entry in observed] == [
        "sshd-promotion-proof.py", "sshd-promotion-proof.py"]
    assert not any(entry["program"] in {"ssh", "ansible-playbook"} for entry in observed)


def test_first_failed_node_stops_before_second_node_readiness(workspace):
    binary = Path(workspace["env"]["PATH"].split(os.pathsep)[0])
    recorder = binary / "ansible-playbook"
    recorder.write_text(recorder.read_text().replace("sys.exit(0)", """
document = json.loads(pathlib.Path(sys.argv[1]).read_text())
stage = pathlib.Path(document[-1]['import_playbook']).stem
inventory = pathlib.Path(sys.argv[sys.argv.index('-i') + 1]).read_text()
sys.exit(31 if stage == 'site' and 'node-one ' in inventory else 0)
"""))
    result = invoke(workspace, target="deploy")
    assert result.returncode != 0
    serial = [entry for entry in calls(workspace) if entry["program"] in {"ssh", "ansible-playbook"}]
    assert [entry["program"] for entry in serial] == ["ssh", "ssh", "ansible-playbook"]
    assert_bootstrap_readiness(serial[0], "100.64.0.1")
    assert_recovery_preflight(serial[1], "100.64.0.1")
    assert not any("100.64.0.2" in argument for entry in serial for argument in entry["args"])


def test_per_node_wrapper_contains_exact_transaction_identity(workspace):
    record = workspace["root"].parent / "transaction.json"
    executable = Path(workspace["env"]["PATH"].split(os.pathsep)[0]) / "ansible-playbook"
    write(executable, f"""#!{sys.executable}
import json, pathlib, sys
document = json.loads(pathlib.Path(sys.argv[1]).read_text())
files = document[0]['vars']['deployment_input_files']['node-one']
transaction = json.loads(pathlib.Path(next(path for path in files if path.endswith('-ssh-transaction.json'))).read_text())
pathlib.Path({str(record)!r}).write_text(json.dumps(transaction))
""", 0o700)
    result = invoke(workspace, limit="node-one")
    assert result.returncode == 0, result.stderr
    observed = json.loads(record.read_text())
    assert observed["ssh_transaction_controller_managed"] is True
    assert observed["ssh_transaction_promotion_config_path"] is None
    assert observed["ssh_transaction_target_identity"]["inventory_alias"] == "node-one"
    assert len(observed["ssh_transaction_bundle_generation"]) == 64
    assert Path(observed["ssh_transaction_inventory_path"]).name == "0-inventory.ini"
    assert Path(observed["ssh_transaction_known_hosts_path"]).name == "known_hosts"


def test_private_read_only_ssh_key_remains_usable(workspace):
    workspace["key"].chmod(0o400)
    result = invoke(workspace, limit="node-one")
    assert result.returncode == 0, result.stderr
    assert any(entry["program"] == "ssh" for entry in calls(workspace))


def commit_fixture(workspace):
    subprocess.run(["git", "add", "."], cwd=workspace["root"], env=workspace["env"], check=True, capture_output=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "test: configure fixture"],
                   cwd=workspace["root"], env=workspace["env"], check=True, capture_output=True)
    environment = {key: value for key, value in workspace["env"].items() if not key.startswith("GIT_")}
    workspace["source_digest"] = subprocess.run(
        [str(workspace["root"] / "scripts/deploy-source-identity.sh"), "--digest"],
        cwd=workspace["root"], env=environment, text=True,
        capture_output=True, check=True).stdout.strip()


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
assert inventory.name == '0-inventory.ini'
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
                        f"document = json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
                        f"stage = pathlib.Path(document[-1]['import_playbook']).stem\n"
                        f"sys.exit(31 if stage == {failed_stage!r} else 0)"))
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
    set_contexts(workspace, "node-one")
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
    set_contexts(workspace, "node-one")
    result = subprocess.run(["make", "fixture-before", "dry-run", "deploy", "fixture-after",
                             "ANSIBLE_LIMIT=node-one", "SECRETS_FILE=" + str(workspace["secrets"])],
                            cwd=root, env=workspace["env"], text=True, capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr
    identities = [line.split() for line in identity_record.read_text().splitlines()]
    assert [line[0] for line in identities] == ["fixture-before", "fixture-after"]
    assert len(identities[0][1]) == 40 and identities[0][1] == identities[1][1]
    observed = calls(workspace)
    ssh = [entry for entry in observed if entry["program"] == "ssh"]
    assert len(ssh) == 4
    for offset in (0, 2):
        assert_bootstrap_readiness(ssh[offset], "100.64.0.1")
        assert_recovery_preflight(ssh[offset + 1], "100.64.0.1")
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
transport_path = next(path for path in files if path.endswith('-transport.json'))
transport = json.loads(pathlib.Path(transport_path).read_text())
options = shlex.split(transport['ansible_ssh_args'])
assert all(options[index] in ('-F', '-o') for index in range(0, len(options), 2))
result = subprocess.run(['/usr/bin/ssh', '-G', *options, transport['ansible_host']],
                        text=True, capture_output=True, check=True, timeout=5)
config = dict(line.split(' ', 1) for line in result.stdout.splitlines())
pathlib.Path({str(record)!r}).write_text(json.dumps({{'config': config, 'transport': transport}}))
""", 0o700)
    context = {"user": "deploy", "host": "node-one", "addr": "198.51.100.44",
               "laddr": "192.0.2.1", "lport": 2022}
    result = invoke(workspace, limit="node-one",
                    context_pairs={"node-one": [context, {**context, "laddr": "198.51.100.8"}]},
                    ANSIBLE_EXTRA_VARS_FILE=str(overrides))
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
    set_contexts(workspace, "node-one")
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
            with contextlib.suppress(ProcessLookupError):
                os.killpg(group, signal.SIGKILL)
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
    if not override:
        expected["actual-node-one.json"]["address"] = "100.64.0.1"
        expected["actual-node-two.json"]["address"] = "100.64.0.2"
    for path in root.parent.glob("actual-*.json"):
        path.unlink()
    write(root / "ansible/playbooks/host_vars/node-one.yml",
          "fixture_secret: hostile-sibling-host-vars\nvpn: {enable_hysteria: hostile}\n")
    context_pairs = None
    if override:
        context = {"user": "deploy", "host": "node-one", "addr": "198.51.100.44",
                   "laddr": "192.0.2.1", "lport": 2022}
        context_pairs = {"node-one": [context, {**context, "laddr": "198.51.100.8"}]}
    candidate = invoke(workspace, limit="node-one" if override else "", context_pairs=context_pairs,
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
