#!/usr/bin/env python3
"""Inventory-bound readiness, convergence and source parity for Make deploys."""

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile

import yaml

import fleet_inspection
from bootstrap_readiness import ReadinessError, cancellation, run_command, wait_for_bootstrap
from sshd_bundle_source import BundleSourceError, bundle_manifest
from sshd_contexts import ContextError, bind_contexts
from sshd_transaction_limits import TRANSACTION_TIMEOUT_SECONDS


class DeployError(Exception):
    """Categorical public errors; never include inputs or subprocess output."""


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-key")
        value[key] = item
    return value


# Ansible's add_all_plugin_dirs scans these subdirs independently of configured
# plugin paths. This repository has no custom plugins at playbook/role bases.
AUTOLOAD_DIRS = (
    "action_plugins", "become_plugins", "cache_plugins", "callback_plugins", "cliconf_plugins",
    "connection_plugins", "doc_fragments", "filter_plugins", "httpapi_plugins", "inventory_plugins",
    "library", "lookup_plugins", "module_utils", "netconf_plugins", "shell_plugins",
    "strategy_plugins", "terminal_plugins", "test_plugins", "vars_plugins",
)

RECOVERY_STATUS_VALIDATOR = r"""import json
import re
import sys

def reject():
    raise SystemExit(41)

def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-key")
        value[key] = item
    return value

raw = sys.stdin.buffer.read(4097)
if not raw or len(raw) > 4096:
    reject()
try:
    value = json.loads(raw, object_pairs_hook=unique)
except (ValueError, UnicodeError):
    reject()
if not isinstance(value, dict) or type(value.get("status")) is not str:
    reject()
status = value["status"]
if status == "idle":
    if set(value) != {"status"}:
        reject()
elif status in {"committed", "rolled_back"}:
    if set(value) != {"generation", "nonce", "status", "deadline", "snapshot_digest"}:
        reject()
    if (type(value["generation"]) is not str
            or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value["generation"]) is None
            or type(value["nonce"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value["nonce"]) is None
            or type(value["deadline"]) is not int or value["deadline"] <= 0
            or type(value["snapshot_digest"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value["snapshot_digest"]) is None):
        reject()
else:
    reject()
"""

RECOVERY_PREFLIGHT = r"""set -eu
root=/usr/local/lib/vpn-sshd
state=/var/lib/vpn-sshd-transaction
migrate=$(/usr/bin/readlink -f "$root/current/sshd_migrate.py")
directory=${migrate%/sshd_migrate.py}
generation=${directory##*/}
[ "$migrate" = "$root/generations/$generation/sshd_migrate.py" ]
[ "${#generation}" -eq 64 ]
case "$generation" in *[!0-9a-f]*) exit 40;; esac
[ "$generation" = "__EXPECTED_GENERATION__" ]
/usr/bin/sudo -n /usr/bin/test -d "$state"
/usr/bin/sudo -n /usr/bin/test ! -L "$state"
[ "$(/usr/bin/sudo -n /usr/bin/stat -c '%u:%g:%a' "$state")" = 0:0:700 ]
/usr/bin/sudo -n /usr/bin/test -f "$state/transaction.lock"
/usr/bin/sudo -n /usr/bin/test ! -L "$state/transaction.lock"
[ "$(/usr/bin/sudo -n /usr/bin/stat -c '%u:%g:%a' "$state/transaction.lock")" = 0:0:600 ]
/usr/bin/sudo -n /usr/bin/python3 -I -B "$root/sshd_bundle.py" status 2>/dev/null | /usr/bin/python3 -I -B -c __STATUS_VALIDATOR__ 2>/dev/null
/usr/bin/sudo -n /usr/bin/python3 -I -B "$migrate" check-installation >/dev/null 2>&1
"""


def validate_discovery_paths(root):
    playbooks = root / "ansible/playbooks"
    # Playbook-relative roles take precedence over ANSIBLE_ROLES_PATH.
    if os.path.lexists(playbooks / "roles"):
        raise DeployError("unsupported Ansible discovery path")
    bases = [playbooks]
    roles = root / "ansible/roles"
    if roles.exists():
        for role in roles.iterdir():
            if role.is_symlink():
                raise DeployError("unsupported Ansible discovery path")
            if role.is_dir():
                bases.append(role)
    if any(os.path.lexists(base / name) for base in bases for name in AUTOLOAD_DIRS):
        raise DeployError("unsupported Ansible discovery path")


def private_file(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    return path


def validate_yaml(data, *, empty=False):
    try:
        value = yaml.safe_load(data)
    except (yaml.YAMLError, UnicodeError):
        raise DeployError("invalid YAML input") from None
    if empty and value is None:
        return
    if not isinstance(value, dict) or (not empty and not value) or any(not isinstance(key, str) for key in value):
        raise DeployError("YAML input must be a mapping")


def read_input(path, *, private=False, exact_mode=None, limit=fleet_inspection.LIMIT):
    """Allow trusted macOS directory aliases, but never follow the final file."""
    original = Path(path).expanduser().absolute()
    try:
        for parent in reversed(original.parents):
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (info.st_uid not in (0, os.geteuid()) or
                    (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 and not sticky_root)):
                raise DeployError("unsafe input directory")
        fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022
                    or (private and info.st_mode & 0o077)
                    or (exact_mode is not None and stat.S_IMODE(info.st_mode) != exact_mode)):
                raise DeployError("unsafe input file")
            canonical = fleet_inspection._open_local_file(original.resolve(strict=True), private=private)
            try:
                other = os.fstat(canonical)
                if (info.st_dev, info.st_ino) != (other.st_dev, other.st_ino):
                    raise DeployError("input changed during validation")
            finally:
                os.close(canonical)
            data = stream.read(limit + 1)
            if not data or len(data) > limit:
                raise DeployError("empty or oversized input")
            return data
    except (OSError, fleet_inspection.InspectionError):
        raise DeployError("unreadable or unsafe input") from None


def read_fenced_input(path, *, private=False, exact_mode=None, limit=fleet_inspection.LIMIT):
    original = Path(path).expanduser().absolute()
    data = read_input(original, private=private, exact_mode=exact_mode, limit=limit)
    try:
        info = original.lstat()
    except OSError:
        raise DeployError("unreadable or unsafe input") from None
    fingerprint = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
                   info.st_size, hashlib.sha256(data).digest())
    return data, (original, private, exact_mode, limit, fingerprint)


def verify_input_fence(fence):
    path, private, exact_mode, limit, expected = fence
    data = read_input(path, private=private, exact_mode=exact_mode, limit=limit)
    try:
        info = path.lstat()
    except OSError:
        raise DeployError("input changed during validation") from None
    actual = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
              info.st_size, hashlib.sha256(data).digest())
    if actual != expected:
        raise DeployError("input changed during validation")


def execution_environment(root, directory):
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE")
                   if key in os.environ}
    environment.update(ANSIBLE_CONFIG=str(root / "ansible/ansible.cfg"), ANSIBLE_DEBUG="false",
                       ANSIBLE_HOME=str(directory / "ansible-home"), ANSIBLE_HOST_KEY_CHECKING="true",
                       ANSIBLE_INVENTORY_ENABLED="ini", ANSIBLE_VARS_ENABLED="",
                       ANSIBLE_LOG_PATH=os.devnull, ANSIBLE_STDOUT_CALLBACK="default",
                       ANSIBLE_LOAD_CALLBACK_PLUGINS="false", ANSIBLE_DISPLAY_ARGS_TO_STDOUT="false",
                       ANSIBLE_COLLECTIONS_PATH=str(root / ".ansible/collections"),
                       ANSIBLE_COLLECTIONS_SCAN_SYS_PATH="false", ANSIBLE_ROLES_PATH=str(root / "ansible/roles"))
    for kind in ("VARS", "CALLBACK", "ACTION", "CONNECTION", "LOOKUP", "FILTER", "TEST",
                 "BECOME", "CACHE", "CLICONF", "DOC_FRAGMENT", "HTTPAPI", "INVENTORY",
                 "NETCONF", "STRATEGY", "TERMINAL"):
        environment[f"ANSIBLE_{kind}_PLUGINS"] = os.devnull
    return environment


def tailnet_site_environment(environment, host_count, mode, *, enabled):
    """Forward a validated one-node enrollment capability only to site.yml."""
    credential = os.environ.get("TAILSCALE_AUTH_KEY")
    if enabled and host_count != 1:
        raise DeployError("Tailnet management requires one exact inventory node")
    if credential is None or mode != "deploy":
        return environment
    if (not enabled or re.fullmatch(r"tskey-auth-[A-Za-z0-9_-]{8,480}", credential)
            is None):
        raise DeployError("Tailnet enrollment credential invalid")
    return {**environment, "TAILSCALE_AUTH_KEY": credential}


def tailnet_enabled_for_selection(root, hosts, memberships, metadata, override_values):
    """Resolve the effective replace-semantics Tailnet toggle for selected hosts."""
    enabled = []
    for host in hosts:
        vpn = {}
        for group in ("all", "vpn", *memberships[host["name"]]):
            if not re.fullmatch(r"all|vpn|vpn-[a-z0-9][a-z0-9-]*", group):
                raise DeployError("unsupported canonical cohort")
            document = yaml.safe_load(read_input(root / "ansible/group_vars" / (group + ".yml")))
            if document is None:
                document = {}
            if not isinstance(document, dict):
                raise DeployError("canonical variables invalid")
            if "vpn" in document:
                vpn = document["vpn"]
                if not isinstance(vpn, dict):
                    raise DeployError("canonical vpn variables invalid")
        host_metadata = metadata.get(host["name"])
        if not isinstance(host_metadata, dict):
            raise DeployError("canonical host metadata invalid")
        if "vpn" in host_metadata:
            vpn = host_metadata["vpn"]
            if not isinstance(vpn, dict):
                raise DeployError("canonical host vpn variables invalid")
        if "vpn" in override_values:
            vpn = override_values["vpn"]
            if not isinstance(vpn, dict):
                raise DeployError("operator vpn variables invalid")
        value = vpn.get("enable_tailnet_management", False)
        if not isinstance(value, bool):
            raise DeployError("Tailnet management toggle invalid")
        if value:
            enabled.append(host["name"])
    return enabled


def checked(command, *, environment, cwd, timeout=15, capture=False, stream=False):
    status, output = run_command(command, environment=environment, cwd=cwd, timeout=timeout,
                                 capture=capture, stream=stream)
    if status:
        raise DeployError("local command failed")
    return output


def require_recovery_foundation(command, generation, environment):
    """Require the exact read-only recovery capability before site convergence."""
    if re.fullmatch("[0-9a-f]{64}", generation) is None:
        raise DeployError("SSH recovery foundation unavailable")
    remote = RECOVERY_PREFLIGHT.replace("__EXPECTED_GENERATION__", generation).replace(
        "__STATUS_VALIDATOR__", shlex.quote(RECOVERY_STATUS_VALIDATOR))
    try:
        status, _output = run_command([*command[:-1], remote], environment=environment, timeout=45)
    except ReadinessError:
        raise DeployError("SSH recovery foundation unavailable") from None
    if status:
        raise DeployError("SSH recovery foundation unavailable")


def source_identity(root, environment, *, require_clean):
    if require_clean and checked(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
                                 environment=environment, cwd=root, capture=True).strip():
        raise DeployError("clean source required")
    result = {}
    for name, flag, size in (("DEPLOY_SOURCE_REVISION", "--revision", 40),
                             ("DEPLOYABLE_SOURCE_DIGEST", "--digest", 64)):
        value = checked([str(root / "scripts/deploy-source-identity.sh"), flag],
                        environment=environment, cwd=root, capture=True).decode().strip()
        if not re.fullmatch("[0-9a-f]{" + str(size) + "}", value):
            raise DeployError("source identity unavailable")
        result[name] = value
    return result


def inventory_selection(inventory, limit, directory):
    raw = read_input(inventory)
    snapshot = private_file(directory / "source.ini", raw)
    # This pass resolves only canonical membership and retains original lines.
    # The existing strict selector validates the entire snapshot exactly once.
    section, rows, groups, global_lines = "", {}, {}, []
    try:
        for line in raw.decode().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1]
                groups.setdefault(section, [])
                continue
            words = shlex.split(stripped, comments=True)
            if section == "vpn" and words:
                rows[words[0]] = line
                groups[section].append(words[0])
            elif section == "vpn:vars":
                global_lines.append(line)
            elif section.startswith("vpn-") and len(words) == 1:
                groups[section].append(words[0])
        selected = set()
        tokens = limit.split(",") if limit else ["vpn"]
        for token in tokens:
            if not fleet_inspection.SAFE_NAME.fullmatch(token) or token in ("all", "ungrouped"):
                raise DeployError("unsupported inventory selection")
            if token in rows and token in groups:
                raise DeployError("ambiguous inventory selection")
            if token in rows:
                selected.add(token)
            elif token in groups and (token == "vpn" or token.startswith("vpn-")):
                selected.update(groups[token])
            else:
                raise DeployError("unknown inventory selection")
        names = sorted(selected)
        hosts = fleet_inspection.select_hosts(snapshot, names)
    except (UnicodeError, ValueError, fleet_inspection.InspectionError):
        raise DeployError("invalid canonical inventory") from None
    memberships = {name: sorted(group for group, members in groups.items()
                                if group.startswith("vpn-") and name in members) for name in names}
    data = "[vpn]\n" + "\n".join(rows[name] for name in names) + "\n"
    for group in sorted(groups):
        members = [name for name in names if group in memberships[name]]
        if members:
            data += "[" + group + "]\n" + "\n".join(members) + "\n"
    data += "[vpn:vars]\n" + "\n".join(global_lines) + "\n"
    selected_file = private_file(directory / "selected.ini", data.encode())
    metadata = {}
    for name in names:
        values = dict(line.strip().split("=", 1) for line in global_lines)
        for entry in shlex.split(rows[name], comments=True)[1:]:
            key, value = entry.split("=", 1)
            try:
                values[key] = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                values[key] = value
        metadata[name] = values
    return hosts, memberships, metadata, selected_file, rows, global_lines


def single_inventory(directory, index, host, memberships):
    name = host["name"]
    fields = [name, "ansible_host=" + shlex.quote(host["address"]),
              "ansible_user=" + shlex.quote(host["user"]), "ansible_port=" + str(host["port"])]
    if host["transport"] != host["address"] or host["alias"] != host["address"]:
        fields += ["inspection_transport_host=" + shlex.quote(host["transport"]),
                   "inspection_host_key_alias=" + shlex.quote(host["alias"])]
    data = "[vpn]\n" + " ".join(fields) + "\n"
    for group in memberships[name]:
        data += "[" + group + "]\n" + name + "\n"
    data += "[vpn:vars]\nansible_ssh_private_key_file=" + shlex.quote(host["key"]) + "\n"
    data += "ansible_python_interpreter=/usr/bin/python3\n"
    return private_file(directory / f"{index}-inventory.ini", data.encode())


def portable_ssh_arguments(command):
    # ssh, scp and sftp share -o forms, but disagree about -p/-l/-i.
    options, result = iter(command[1:-2]), []
    for flag in options:
        value = next(options)
        if flag in ("-i", "-l", "-p"):
            value = {"-i": "IdentityFile", "-l": "User", "-p": "Port"}[flag] + "=" + value
            flag = "-o"
        if flag not in ("-F", "-o"):
            raise DeployError("unsupported SSH option")
        if flag == "-o" and value.startswith(("IdentityFile=", "UserKnownHostsFile=")):
            key, value = value.split("=", 1)
            if any(char in value for char in "\r\n\x00"):
                raise DeployError("unsafe SSH path")
            value = key + '="' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        result.extend((flag, value))
    return shlex.join(result)


def transport_variables(host, command):
    return {"ansible_host": host["transport"], "ansible_port": host["port"],
            "ansible_user": host["user"], "ansible_ssh_private_key_file": host["key"],
            "ansible_ssh_args": portable_ssh_arguments(command), "ansible_ssh_common_args": "",
            "ansible_ssh_extra_args": "", "ansible_ssh_executable": "/usr/bin/ssh",
            "ansible_scp_executable": "/usr/bin/scp", "ansible_sftp_executable": "/usr/bin/sftp",
            "ansible_connection": "ssh", "ansible_python_interpreter": "/usr/bin/python3",
            "ansible_become": True, "ansible_become_user": "root", "ansible_become_method": "sudo",
            "ansible_become_flags": "-n"}


def prepare_host_playbooks(root, directory, index, host, memberships, metadata, secrets, overrides,
                           command, inventory, known_hosts, transaction):
    paths = []
    for group in ("all", "vpn", *memberships[host["name"]]):
        if not re.fullmatch(r"all|vpn|vpn-[a-z0-9][a-z0-9-]*", group):
            raise DeployError("unsupported canonical cohort")
        data = read_input(root / "ansible/group_vars" / (group + ".yml"))
        validate_yaml(data, empty=True)
        paths.append(str(private_file(directory / f"{index}-{group}.yml", data)))
    paths.append(str(private_file(directory / f"{index}-metadata.json",
                                  json.dumps(metadata[host["name"]]).encode())))
    paths.append(str(secrets))
    if overrides:
        paths.append(str(overrides))
    paths.append(str(private_file(directory / f"{index}-transport.json",
                                  json.dumps(transport_variables(host, command)).encode())))
    transaction_vars = dict(transaction, ssh_transaction_inventory_path=str(inventory),
                            ssh_transaction_known_hosts_path=str(known_hosts))
    paths.append(str(private_file(directory / f"{index}-ssh-transaction.json",
                                  json.dumps(transaction_vars, sort_keys=True).encode())))
    files = {host["name"]: paths}
    loader = {"name": "Load canonical deployment inputs for the selected host", "hosts": "vpn",
              "gather_facts": False, "become": False, "tags": ["always"],
              "vars": {"deployment_input_files": files}, "tasks": [{
                  "name": "Load ordered canonical variables without ambient host vars",
                  "ansible.builtin.include_vars": {"file": "{{ deployment_input_file }}", "hash_behaviour": "replace"},
                  "loop": "{{ deployment_input_files[inventory_hostname] }}",
                  "loop_control": {"loop_var": "deployment_input_file"}, "no_log": True}]}
    return {name: private_file(directory / f"{index}-{name}.json", json.dumps([
        loader, {"import_playbook": str(root / "ansible/playbooks" / (name + ".yml"))}]).encode())
            for name in ("site", "source-drift")}


def transaction_inputs(mode, hosts, identity, directory, root, environment):
    try:
        raw = read_input(os.environ["DEPLOY_SSH_CONTEXTS_FILE"], private=True, exact_mode=0o600)
        contexts = json.loads(raw, object_pairs_hook=unique_object)
    except (KeyError, ValueError, UnicodeError):
        raise DeployError("SSH contexts unavailable") from None
    names = {host["name"] for host in hosts}
    if not isinstance(contexts, dict) or set(contexts) != names:
        raise DeployError("SSH contexts do not match selection")
    try:
        for name in sorted(names):
            host = next(item for item in hosts if item["name"] == name)
            bind_contexts(contexts[name], host["address"], host["transport"], host["port"])
    except ContextError:
        raise DeployError("SSH contexts invalid") from None
    generation, _manifest = bundle_manifest()
    promotions = None
    if mode == "deploy":
        try:
            promotion_raw = read_input(
                os.environ["DEPLOY_PROMOTION_CONFIG_FILE"], private=True, exact_mode=0o600)
            promotions = json.loads(promotion_raw, object_pairs_hook=unique_object)
        except (KeyError, ValueError, UnicodeError):
            raise DeployError("promotion proof config unavailable") from None
        if (not isinstance(promotions, dict) or set(promotions) != names
                or any(not isinstance(config, dict) or not config for config in promotions.values())):
            raise DeployError("promotion proof configs do not match selection")
    result = {}
    promotion_paths = []
    for host in hosts:
        alias = host["name"]
        expected_target = {
            "inventory_alias": alias,
            "public_service_address_sha256": hashlib.sha256(host["address"].encode()).hexdigest(),
            "deployable_digest": identity["DEPLOYABLE_SOURCE_DIGEST"],
        }
        promotion = None
        if promotions is not None:
            target = promotions[alias].get("target_identity")
            if (not isinstance(target, dict)
                    or any(target.get(key) != value for key, value in expected_target.items())):
                raise DeployError("promotion proof configs do not bind selected targets")
            promotion = private_file(directory / (alias + "-promotion-config.json"),
                                     json.dumps(promotions[alias], sort_keys=True).encode())
            promotion_paths.append(promotion)
        result[alias] = {
            "ssh_transaction_controller_managed": True,
            "ssh_transaction_contexts": contexts[alias],
            "ssh_transaction_bundle_generation": generation,
            "ssh_transaction_timeout_seconds": TRANSACTION_TIMEOUT_SECONDS,
            "ssh_transaction_promotion_config_path": str(promotion) if promotion else None,
            "ssh_transaction_target_identity": expected_target,
        }
    for promotion in promotion_paths:
        checked([sys.executable, str(root / "scripts/sshd-promotion-proof.py"),
                 "--validate-config", "--config", str(promotion)],
                environment=environment, cwd=directory, timeout=30)
    return result


def prepare_network_exposure_inputs(root, directory, values, hosts, environment):
    config = values.get("network_exposure_gate")
    if config is None or config["mode"] == "disabled":
        return values, []
    selected = sorted(host["name"] for host in hosts)
    if config["mode"] in {"canary", "enforce"} and sorted(config["authorized_hosts"]) != selected:
        raise DeployError("network exposure promotion does not match selection")
    artifact_data, artifact_fence = read_fenced_input(
        config["artifact"], private=True, exact_mode=0o600, limit=4 * 1024 * 1024)
    key_data, key_fence = read_fenced_input(
        config["trusted_key"], private=True, exact_mode=0o600)
    artifact = private_file(directory / "network-exposure-artifact.json", artifact_data)
    trusted_key = private_file(directory / "network-exposure-trusted-key.pem", key_data)
    normalized = dict(config, artifact=str(artifact), trusted_key=str(trusted_key))
    result = dict(values, network_exposure_gate=normalized)
    for host in selected:
        command = [sys.executable, str(root / "scripts/network-exposure-gate.py"),
                   "--mode", normalized["mode"], "--artifact", normalized["artifact"],
                   "--trusted-key", normalized["trusted_key"], "--trusted-key-sha256",
                   normalized["trusted_key_sha256"], "--source-id", normalized["source_id"],
                   "--promotion-approved", str(normalized["promotion_approved"]).lower(),
                   "--promotion-digest", normalized["promotion_digest"], "--inventory-host", host,
                   "--authorized-hosts-json", json.dumps(
                       normalized["authorized_hosts"], separators=(",", ":")), "--internal-plan"]
        output = checked(command, environment=environment, cwd=directory, timeout=20, capture=True)
        try:
            document = json.loads(output, object_pairs_hook=unique_object)
        except (UnicodeError, ValueError):
            raise DeployError("network exposure validation failed") from None
        if (not isinstance(document, dict) or set(document) != {"summary", "plan"}
                or not isinstance(document["summary"], dict) or not isinstance(document["plan"], dict)):
            raise DeployError("network exposure validation failed")
    return result, [artifact_fence, key_fence]


def controller(mode):
    if os.environ.get("ANSIBLE_DEBUG", "false").lower() not in ("false", "0", "no", "off"):
        raise DeployError("Ansible debug is not supported")
    if mode not in ("deploy", "dry-run"):
        raise DeployError("unsupported deployment mode")
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="vpn-deploy-") as temporary:
        directory = Path(temporary).resolve()
        environment = execution_environment(root, directory)
        identity = source_identity(root, environment, require_clean=mode == "deploy")
        environment.update(identity)
        validate_discovery_paths(root)
        hosts, memberships, metadata, _inventory, _rows, _global_lines = inventory_selection(
            root / "ansible/inventory/generated.ini", os.environ.get("DEPLOY_LIMIT", ""), directory)
        secret_data = read_input(os.environ["DEPLOY_SECRETS_FILE"], private=True, exact_mode=0o600)
        validate_yaml(secret_data)
        secrets = private_file(directory / "secrets.yaml", secret_data)
        environment["VPN_SECRETS_FILE"] = str(secrets)
        overrides, override_values, input_fences = None, {}, []
        if os.environ.get("DEPLOY_EXTRA_VARS_FILE"):
            if not os.environ.get("DEPLOY_LIMIT"):
                raise DeployError("extra vars require an explicit inventory selection")
            override_data, override_fence = read_fenced_input(
                os.environ["DEPLOY_EXTRA_VARS_FILE"], private=True, exact_mode=0o600)
            source_overrides = private_file(directory / "source-overrides.yml", override_data)
            checked([sys.executable, str(root / "scripts/validate-ansible-extra-vars.py"), str(source_overrides)],
                    environment=environment, cwd=directory)
            override_values = yaml.safe_load(source_overrides.read_text())
            override_values, exposure_fences = prepare_network_exposure_inputs(
                root, directory, override_values, hosts, environment)
            input_fences = [override_fence, *exposure_fences]
            normalized = (yaml.safe_dump(override_values, sort_keys=True).encode()
                          if "network_exposure_gate" in override_values else override_data)
            overrides = private_file(directory / "operator-overrides.yml", normalized)
        known_hosts = private_file(directory / "known_hosts", read_input(os.environ.get(
            "DEPLOY_KNOWN_HOSTS", str(Path.home() / ".ssh/known_hosts"))))
        commands, identities = [], set()
        for index, host in enumerate(hosts):
            host["key"] = str(private_file(directory / f"identity-{index}", read_input(host["key"], private=True)))
            host["transport"] = override_values.get("ansible_host", host["transport"])
            host["port"] = override_values.get("ansible_port", host["port"])
            pair = (host["transport"].lower(), host["port"])
            if pair in identities:
                raise DeployError("duplicate effective transport")
            identities.add(pair)
            commands.append(fleet_inspection.ssh_command(host, known_hosts))
        transactions = transaction_inputs("deploy" if mode == "deploy" else "check",
                                          hosts, identity, directory, root, environment)
        tailnet_hosts = tailnet_enabled_for_selection(
            root, hosts, memberships, metadata, override_values)
        site_environment = tailnet_site_environment(
            environment, len(hosts), mode, enabled=bool(tailnet_hosts))
        prepared = []
        for index, (host, command) in enumerate(zip(hosts, commands)):
            inventory = single_inventory(directory, index, host, memberships)
            playbooks = prepare_host_playbooks(
                root, directory, index, host, memberships, metadata, secrets, overrides,
                command, inventory, known_hosts, transactions[host["name"]])
            arguments = ["-i", str(inventory)]
            if overrides:
                arguments += ["--extra-vars", "@" + str(overrides)]
            prepared.append((host, command, playbooks, arguments))
        if os.environ.get("DEPLOY_SKIP_PRECHECK", "") != "1":
            # Reclaim precheck secret copies even if their EXIT traps are killed.
            # Keep Ansible's default temp root: nested paths exceed macOS's RPC socket limit.
            precheck_environment = {**environment, "TMPDIR": str(directory)}
            checked([sys.executable, str(root / "scripts/validate-secrets.py"), str(secrets), "--strict"],
                    environment=precheck_environment, cwd=directory)
            checked([sys.executable, str(root / "scripts/spot-check-secrets.py")],
                    environment=precheck_environment, cwd=directory)
            checked([str(root / "scripts/check-certs.sh")], environment=precheck_environment, cwd=directory)
        for fence in input_fences:
            verify_input_fence(fence)
        for host, command, playbooks, arguments in prepared:
            wait_for_bootstrap(command[:-1], environment=environment)
            require_recovery_foundation(
                command, transactions[host["name"]]["ssh_transaction_bundle_generation"], environment)
            current = source_identity(root, environment, require_clean=mode == "deploy")
            if current != identity:
                raise DeployError("source changed during readiness")
            validate_discovery_paths(root)
            site = ["ansible-playbook", str(playbooks["site"]), *arguments]
            if mode == "dry-run":
                site += ["--check", "--diff"]
            elif os.environ.get("DEPLOY_TAGS"):
                site += ["--tags", os.environ["DEPLOY_TAGS"]]
            checked(site, environment=site_environment, cwd=directory, timeout=3600, stream=True)
            if mode == "deploy":
                checked(["ansible-playbook", str(playbooks["source-drift"]), *arguments],
                        environment=environment, cwd=directory, timeout=300, stream=True)
                audit_environment = {**environment, "ENV": os.environ.get("DEPLOY_ENV", "prod"),
                                     "PROVIDER": os.environ.get("DEPLOY_PROVIDER", "upcloud")}
                audit_environment.update({key: os.environ[key]
                                          for key in ("AGE_KEY", "AUDIT_LOG_FILE", "AUDIT_ACTOR")
                                          if key in os.environ})
                try:
                    status, _output = run_command(
                        [str(root / "scripts/audit-log.sh"), "append-best-effort",
                         "--action", "site-deploy", "--note",
                         "playbook=site.yml node=" + host["name"] + " warp_outbound_role=conditional"],
                        environment=audit_environment, cwd=root, timeout=30)
                except ReadinessError:
                    status = 1
                if status:
                    print("warning: deployment audit unavailable", file=sys.stderr)


def main():
    try:
        with cancellation():
            controller(sys.argv[1])
    except (DeployError, BundleSourceError, ReadinessError, fleet_inspection.InspectionError) as error:
        print("deploy: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
