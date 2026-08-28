#!/usr/bin/env python3
"""Inventory-bound readiness, convergence and source parity for Make deploys."""

import ast
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


class DeployError(Exception):
    """Categorical public errors; never include inputs or subprocess output."""


# Ansible's add_all_plugin_dirs scans these subdirs independently of configured
# plugin paths. This repository has no custom plugins at playbook/role bases.
AUTOLOAD_DIRS = (
    "action_plugins", "become_plugins", "cache_plugins", "callback_plugins", "cliconf_plugins",
    "connection_plugins", "doc_fragments", "filter_plugins", "httpapi_plugins", "inventory_plugins",
    "library", "lookup_plugins", "module_utils", "netconf_plugins", "shell_plugins",
    "strategy_plugins", "terminal_plugins", "test_plugins", "vars_plugins",
)


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


def read_input(path, *, private=False, exact_mode=None):
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
            data = stream.read(fleet_inspection.LIMIT + 1)
            if not data or len(data) > fleet_inspection.LIMIT:
                raise DeployError("empty or oversized input")
            return data
    except (OSError, fleet_inspection.InspectionError):
        raise DeployError("unreadable or unsafe input") from None


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


def checked(command, *, environment, cwd, timeout=15, capture=False, stream=False):
    status, output = run_command(command, environment=environment, cwd=cwd, timeout=timeout,
                                 capture=capture, stream=stream)
    if status:
        raise DeployError("local command failed")
    return output


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
    return hosts, memberships, metadata, selected_file


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


def prepare_playbooks(root, directory, hosts, memberships, metadata, secrets, overrides, commands):
    files = {}
    for index, host in enumerate(hosts):
        paths = []
        for group in ("all", "vpn", *memberships[host["name"]]):
            if not re.fullmatch(r"all|vpn|vpn-[a-z0-9][a-z0-9-]*", group):
                raise DeployError("unsupported canonical cohort")
            data = read_input(root / "ansible/group_vars" / (group + ".yml"))
            validate_yaml(data, empty=True)
            paths.append(str(private_file(directory / f"{index}-{group}.yml", data)))
        paths.append(str(private_file(directory / f"{index}-metadata.json", json.dumps(metadata[host["name"]]).encode())))
        paths.append(str(secrets))
        if overrides:
            paths.append(str(overrides))
        paths.append(str(private_file(directory / f"{index}-transport.json",
                                     json.dumps(transport_variables(host, commands[index])).encode())))
        files[host["name"]] = paths
    loader = {"name": "Load canonical deployment inputs for each selected host", "hosts": "vpn",
              "gather_facts": False, "become": False, "tags": ["always"],
              "vars": {"deployment_input_files": files}, "tasks": [{
                  "name": "Load ordered canonical variables without ambient host vars",
                  "ansible.builtin.include_vars": {"file": "{{ deployment_input_file }}", "hash_behaviour": "replace"},
                  "loop": "{{ deployment_input_files[inventory_hostname] }}",
                  "loop_control": {"loop_var": "deployment_input_file"}, "no_log": True}]}
    return {name: private_file(directory / (name + ".json"), json.dumps([
        loader, {"import_playbook": str(root / "ansible/playbooks" / (name + ".yml"))}]).encode())
            for name in ("site", "source-drift")}


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
        hosts, memberships, metadata, inventory = inventory_selection(
            root / "ansible/inventory/generated.ini", os.environ.get("DEPLOY_LIMIT", ""), directory)
        secret_data = read_input(os.environ["DEPLOY_SECRETS_FILE"], private=True, exact_mode=0o600)
        validate_yaml(secret_data)
        secrets = private_file(directory / "secrets.yaml", secret_data)
        environment["VPN_SECRETS_FILE"] = str(secrets)
        overrides, override_values = None, {}
        if os.environ.get("DEPLOY_EXTRA_VARS_FILE"):
            if not os.environ.get("DEPLOY_LIMIT"):
                raise DeployError("extra vars require an explicit inventory selection")
            overrides = private_file(directory / "overrides.yaml", read_input(
                os.environ["DEPLOY_EXTRA_VARS_FILE"], private=True, exact_mode=0o600))
            checked([sys.executable, str(root / "scripts/validate-ansible-extra-vars.py"), str(overrides)],
                    environment=environment, cwd=directory)
            override_values = yaml.safe_load(overrides.read_text())
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
        playbooks = prepare_playbooks(root, directory, hosts, memberships, metadata, secrets, overrides, commands)
        if os.environ.get("DEPLOY_SKIP_PRECHECK", "") != "1":
            checked([sys.executable, str(root / "scripts/validate-secrets.py"), str(secrets), "--strict"],
                    environment=environment, cwd=directory)
            checked([sys.executable, str(root / "scripts/spot-check-secrets.py")], environment=environment, cwd=directory)
            checked([str(root / "scripts/check-certs.sh")], environment=environment, cwd=directory)
        for command in commands:
            wait_for_bootstrap(command[:-1], environment=environment)
        current = source_identity(root, environment, require_clean=mode == "deploy")
        if current != identity:
            raise DeployError("source changed during readiness")
        validate_discovery_paths(root)
        arguments = ["-i", str(inventory)]
        if overrides:
            arguments += ["--extra-vars", "@" + str(overrides)]
        site = ["ansible-playbook", str(playbooks["site"]), *arguments]
        if mode == "dry-run":
            site += ["--check", "--diff"]
        elif os.environ.get("DEPLOY_TAGS"):
            site += ["--tags", os.environ["DEPLOY_TAGS"]]
        checked(site, environment=environment, cwd=directory, timeout=3600, stream=True)
        if mode == "deploy":
            checked(["ansible-playbook", str(playbooks["source-drift"]), *arguments],
                    environment=environment, cwd=directory, timeout=300, stream=True)
            audit_environment = {**environment, "ENV": os.environ.get("DEPLOY_ENV", "prod"),
                                 "PROVIDER": os.environ.get("DEPLOY_PROVIDER", "upcloud")}
            audit_environment.update({key: os.environ[key] for key in ("AGE_KEY", "AUDIT_LOG_FILE", "AUDIT_ACTOR")
                                      if key in os.environ})
            try:
                status, _output = run_command([str(root / "scripts/audit-log.sh"), "append-best-effort",
                                              "--action", "site-deploy", "--note",
                                              "playbook=site.yml warp_outbound_role=conditional"],
                                             environment=audit_environment, cwd=root, timeout=30)
            except ReadinessError:
                status = 1
            if status:
                print("warning: deployment audit unavailable", file=sys.stderr)


def main():
    try:
        with cancellation():
            controller(sys.argv[1])
    except (DeployError, ReadinessError, fleet_inspection.InspectionError) as error:
        print("deploy: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
