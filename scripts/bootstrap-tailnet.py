#!/usr/bin/env python3
"""Establish one restricted Tailnet path through pinned public OpenSSH."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import NamedTuple

import fleet_inspection as inspection
import tailnet_management as tailnet

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "ansible/inventory/generated.ini"
CONFIG_FIELDS = {
    "schema_version", "environment", "provider", "inventory_alias",
    "public_address", "ssh_port", "host_key_sha256", "public_sources",
    "approved_sources", "source_revision", "deployable_digest", "known_hosts",
    "cleanup_manifest", "output",
}


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


deploy = module("deploy-controller")


class BootstrapError(ValueError):
    """Categorical refusal; private input and child output never escape."""


class Inputs(NamedTuple):
    config: dict
    host: dict
    ssh: list
    known_hosts: Path
    environment: dict
    directory: Path
    fences: list
    output_parent_identity: tuple


def _addresses(values, *, tailnet_only=False):
    if tailnet_only:
        return tailnet.validate_sources(values)
    if not isinstance(values, list) or not 1 <= len(values) <= 8:
        raise BootstrapError("public-sources-invalid")
    result = []
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except (ValueError, TypeError):
            raise BootstrapError("public-sources-invalid") from None
        if (not isinstance(value, str) or value != str(address) or address.is_unspecified
                or address.is_multicast or address.is_loopback or address.is_link_local
                or address in (tailnet.TAILNET_V4 if address.version == 4 else tailnet.TAILNET_V6)
                or value in result):
            raise BootstrapError("public-sources-invalid")
        result.append(value)
    return result


def _output_path(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise BootstrapError("output-path-invalid")
    path = Path(value)
    if any(part in (".", "..") for part in path.parts) or os.path.lexists(path):
        raise BootstrapError("output-path-unavailable")
    # Freeze the physical parent; the publisher reopens and compares its inode.
    parent = path.parent.resolve(strict=True)
    for directory in (parent, *parent.parents):
        info = directory.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or (info.st_mode & 0o022 and not sticky_root)):
            raise BootstrapError("output-parent-unsafe")
    info = parent.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise BootstrapError("output-parent-unsafe")
    return parent / path.name


def _pin(config, host, directory, environment):
    original = Path(config["known_hosts"])
    raw, fence = deploy.read_fenced_input(original)
    source = deploy.private_file(directory / "known-hosts-source", raw)
    lookup = host["alias"] if host["port"] == 22 else f"[{host['alias']}]:{host['port']}"
    found = inspection.bounded_command(
        ["ssh-keygen", "-F", lookup, "-f", str(source)], environment=environment,
    ).decode().splitlines()
    keys = set()
    for line in found:
        if line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 3 and fields[1] == "ssh-ed25519":
            keys.add(fields[2])
    if len(keys) != 1:
        raise BootstrapError("single-host-key-required")
    key = next(iter(keys))
    try:
        digest = hashlib.sha256(base64.b64decode(key, validate=True)).hexdigest()
    except ValueError:
        raise BootstrapError("host-key-invalid") from None
    if digest != config["host_key_sha256"]:
        raise BootstrapError("host-key-mismatch")
    return deploy.private_file(directory / "known-hosts", f"{lookup} ssh-ed25519 {key}\n".encode()), fence


def _cleanup_fences(config, host):
    path = config["cleanup_manifest"]
    if config["environment"] == "prod":
        if path is not None:
            raise BootstrapError("unexpected-cleanup-manifest")
        return []
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise BootstrapError("cleanup-manifest-required")
    guard = module("staging-cleanup-guard" if config["provider"] == "upcloud" else "vultr-staging-cleanup-guard")
    try:
        manifest = guard.load_manifest(
            Path(path), expected_provider=config["provider"],
            expected_environment=config["environment"],
        ) if config["provider"] == "upcloud" else guard.load_manifest(
            Path(path), expected_environment=config["environment"],
        )
        raw_manifest, manifest_fence = deploy.read_fenced_input(path, private=True, exact_mode=0o600)
        if json.loads(raw_manifest) != manifest:
            raise BootstrapError("cleanup-manifest-changed")
        state_path = manifest["state"]["path"]
        raw, state_fence = deploy.read_fenced_input(
            state_path, private=True, exact_mode=0o600, limit=guard.MAX_STATE_BYTES,
        )
        state = inspection.decode_json(raw)
        if (hashlib.sha256(raw).hexdigest() != manifest["state"]["sha256"]
                or manifest["hostname"] != host["name"]
                or state["outputs"]["server_ipv4"]["value"] != host["address"]):
            raise BootstrapError("cleanup-target-mismatch")
        if config["provider"] == "upcloud":
            identity = guard._extract_state_identity(state, host["name"])
            if identity != (manifest["server_uuid"], manifest["root_storage_uuid"]):
                raise BootstrapError("cleanup-target-mismatch")
        else:
            if guard._extract_identity(state, host["name"]) != manifest["resources"]:
                raise BootstrapError("cleanup-target-mismatch")
        return [manifest_fence, state_fence]
    except (guard.GuardError, KeyError, TypeError, ValueError):
        raise BootstrapError("cleanup-ownership-refused") from None


def load_inputs(environment, directory):
    """Validate and freeze every local capability before the first remote call."""
    try:
        target = environment.get("BOOTSTRAP_TARGET", "")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", target)
                or target in {"all", "vpn", "ungrouped"}):
            raise BootstrapError("exact-node-required")
        if environment.get("ANSIBLE_DEBUG", "false").lower() not in {"false", "0", "no", "off"}:
            raise BootstrapError("debug-forbidden")
        raw, config_fence = deploy.read_fenced_input(
            environment["TAILNET_BOOTSTRAP_CONFIG"], private=True, exact_mode=0o600,
        )
        config = inspection.decode_json(raw)
        if set(config) != CONFIG_FIELDS or type(config["schema_version"]) is not int or config["schema_version"] != 1:
            raise BootstrapError("config-invalid")
        if (config["inventory_alias"] != target or config["provider"] not in {"upcloud", "vultr"}
                or not isinstance(config["environment"], str)
                or not re.fullmatch(r"prod|ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}", config["environment"])):
            raise BootstrapError("target-invalid")
        for name, length in (("source_revision", 40), ("deployable_digest", 64), ("host_key_sha256", 64)):
            if not isinstance(config[name], str) or not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", config[name]):
                raise BootstrapError("binding-invalid")
        _addresses(config["public_sources"])
        _addresses(config["approved_sources"], tailnet_only=True)
        _addresses([config["public_address"]])
        if not isinstance(config["known_hosts"], str) or not Path(config["known_hosts"]).is_absolute():
            raise BootstrapError("known-hosts-invalid")
        config["output"] = str(_output_path(config["output"]))
        child = deploy.execution_environment(ROOT, directory)
        # Read only the declared base variables from the caller, not ambient
        # provider capabilities, Git routing, Ansible plugins, tags, or auth keys.
        for name in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE"):
            if name in environment:
                child[name] = environment[name]
        identity = deploy.source_identity(ROOT, child, require_clean=True)
        if (identity["DEPLOY_SOURCE_REVISION"] != config["source_revision"]
                or identity["DEPLOYABLE_SOURCE_DIGEST"] != config["deployable_digest"]):
            raise BootstrapError("source-mismatch")
        deploy.validate_discovery_paths(ROOT)
        inventory, inventory_fence = deploy.read_fenced_input(INVENTORY)
        frozen = deploy.private_file(directory / "inventory-source", inventory)
        host = inspection.select_hosts(frozen, [target])[0]
        if (type(config["ssh_port"]) is not int or host["port"] != config["ssh_port"]
                or host["address"] != config["public_address"]):
            raise BootstrapError("inventory-target-mismatch")
        host["transport"] = host["address"]
        key, key_fence = deploy.read_fenced_input(host["key"], private=True, exact_mode=0o600)
        host["key"] = str(deploy.private_file(directory / "identity", key))
        known_hosts, pin_fence = _pin(config, host, directory, child)
        ssh = inspection.ssh_command(host, known_hosts)
        ssh[1:1] = ["-o", "HostKeyAlgorithms=ssh-ed25519"]
        fences = [config_fence, inventory_fence, key_fence, pin_fence, *_cleanup_fences(config, host)]
        parent = Path(config["output"]).parent.stat()
        return Inputs(config, host, ssh, known_hosts, child, directory, fences, (parent.st_dev, parent.st_ino))
    except (KeyError, TypeError, ValueError, OSError, inspection.InspectionError,
            deploy.DeployError, tailnet.Refusal):
        raise BootstrapError("bootstrap-inputs-refused") from None


def _binding(inputs):
    fields = {"inventory_alias", "public_address", "ssh_port", "public_sources", "approved_sources",
              "host_key_sha256", "source_revision", "deployable_digest"}
    return tailnet.validate_binding({key: inputs.config[key] for key in fields})


def _remote(inputs, host, command, payload=b"", *, timeout=45):
    from bootstrap_readiness import run_command
    argv = inspection.ssh_command(host, inputs.known_hosts)
    argv[1:1] = ["-o", "HostKeyAlgorithms=ssh-ed25519"]
    argv[-1] = command
    status, raw = run_command(argv, timeout=timeout, environment=inputs.environment,
                              capture=True, input_data=payload)
    if status or len(raw) > 32768:
        raise BootstrapError("bootstrap-remote-refused")
    result = json.loads(raw, object_pairs_hook=deploy.unique_object)
    if not isinstance(result, dict) or result.get("status") == "error":
        raise BootstrapError("bootstrap-remote-refused")
    return result


def _probe(inputs, host, *, preinstall=False):
    source = (ROOT / "scripts/tailnet_bootstrap_probe.py").read_bytes()
    parser = b"fragment_parser = None\n"
    if preinstall:
        # Reuse the canonical fragment grammar without installing guest code
        # or duplicating its validator in the read-only preflight.
        helper = (ROOT / "scripts/tailnet-network-guest.py").read_bytes()
        parser = (b"shared = {'__name__': 'tailnet_preflight_fragment'}\nexec(" + repr(helper).encode()
                  + b", shared)\nfragment_parser = shared['canonical_fragment']\n")
    request = json.dumps([_binding(inputs), host["user"], host["transport"]]).encode()
    invocation = (b"\n" + parser + b"print(json.dumps(probe(*json.loads(" + repr(request).encode()
                  + b"),fragment_parser=fragment_parser,preinstall=" + str(preinstall).encode() + b")))\n")
    context = _remote(inputs, host, "sudo -n /usr/bin/python3 -I -B -S -", source + invocation)
    expected = {"user", "host", "addr", "laddr", "lport"}
    sources = inputs.config["public_sources"] if host["transport"] == host["address"] else inputs.config["approved_sources"]
    if (set(context) != expected or context["user"] != host["user"] or context["host"] != context["addr"]
            or context["addr"] not in sources or context["laddr"] != host["transport"]
            or context["lport"] != host["port"]):
        raise BootstrapError("bootstrap-socket-proof-invalid")
    return context


def _installed(inputs):
    names = ["tailnet_management.py", "tailnet_firewall.py", "tailnet_bootstrap_probe.py", "tailnet-network-guest.py", "sshd_contexts.py",
             "tailnet-configure.py", "tailnet-check.py", "tailnet-recover.py", "tailnet-firewall-recover.py"]
    manifest = {"/usr/local/lib/vpn-tailnet/" + name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest() for name in names}
    for name in ("vpn-tailnet-firewall-recover.service", "vpn-tailnet-recover.service", "vpn-tailnet-recover.timer"):
        manifest["/etc/systemd/system/" + name] = hashlib.sha256((ROOT / "ansible/roles/tailnet-management/templates" / (name + ".j2")).read_bytes()).hexdigest()
    source = '''import os,pathlib,stat,hashlib,json
expected=json.loads(__MANIFEST__)
for path in ['/usr/local/lib/vpn-tailnet','/var/lib/vpn-tailnet-management']:
 p=pathlib.Path(path)
 for parent in [p,*p.parents]:
  if os.path.lexists(parent):
   i=parent.lstat()
   assert stat.S_ISDIR(i.st_mode) and i.st_uid==0 and not i.st_mode&0o022
seen=0
for path,digest in expected.items():
 if not os.path.lexists(path): continue
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  i=os.fstat(f.fileno())
  assert stat.S_ISREG(i.st_mode) and i.st_uid==0 and not i.st_mode&0o022 and i.st_nlink==1
  data=f.read(1048577)
 assert len(data)<=1048576 and hashlib.sha256(data).hexdigest()==digest
 seen+=1
root=pathlib.Path('/usr/local/lib/vpn-tailnet')
if root.exists():
 assert {p.name for p in root.iterdir()} <= {pathlib.Path(p).name for p in expected if p.startswith(str(root)+'/')}|{'__pycache__'}
assert seen in (0,len(expected))
print(json.dumps({'status':'ready' if seen else 'absent'}))
'''.replace("__MANIFEST__", repr(json.dumps(manifest)))
    return _remote(inputs, inputs.host, "sudo -n /usr/bin/python3 -I -B -S -", source.encode())["status"]


def _require_source(inputs):
    identity = deploy.source_identity(ROOT, inputs.environment, require_clean=True)
    if (identity["DEPLOY_SOURCE_REVISION"] != inputs.config["source_revision"]
            or identity["DEPLOYABLE_SOURCE_DIGEST"] != inputs.config["deployable_digest"]):
        raise BootstrapError("bootstrap-source-changed")


def _install(inputs):
    from bootstrap_readiness import run_command
    _require_source(inputs)
    # Extra vars also override localhost during delegation. Scope connection
    # settings to this one-node group so local validation stays local.
    transport = deploy.transport_variables(inputs.host, inputs.ssh)
    if any(any(char in str(value) for char in "\r\n\x00") for value in transport.values()):
        raise BootstrapError("bootstrap-transport-invalid")
    inventory = "[vpn]\n" + inputs.host["name"] + "\n\n[vpn:vars]\n"
    inventory += "".join(f"{name}={value}\n" for name, value in transport.items())
    path = deploy.private_file(inputs.directory / "bootstrap-inventory.ini", inventory.encode())
    variables = {"bootstrap_inventory_alias": inputs.host["name"], "bootstrap_public_preflight": True,
                 "tailnet_management": {"approved_sources": inputs.config["approved_sources"]}}
    extra = deploy.private_file(inputs.directory / "bootstrap-variables.json", json.dumps(variables).encode())
    command = ["ansible-playbook", "-i", str(path), str(ROOT / "ansible/playbooks/bootstrap-tailnet.yml"),
               "--limit", inputs.host["name"], "--extra-vars", "@" + str(extra)]
    status, _ = run_command(command, timeout=900, environment=inputs.environment, cwd=inputs.directory)
    if status or _installed(inputs) != "ready":
        raise BootstrapError("bootstrap-installation-failed")


def _rpc(inputs, action, **values):
    import shlex
    loader = "import sys,runpy;sys.path.insert(0,'/usr/local/lib/vpn-tailnet');runpy.run_path('/usr/local/lib/vpn-tailnet/tailnet-configure.py',run_name='__main__')"
    command = "sudo -n /usr/bin/python3 -I -B -c " + shlex.quote(loader)
    payload = json.dumps({"action": action, **values}, sort_keys=True).encode()
    return _remote(inputs, inputs.host, command, payload, timeout=120 if action == "enroll" else 60)


def _capability(inputs, result):
    from uuid import UUID
    if (set(result) != {"status", "changed", "nonce", "generation", "binding_sha256", "lease", "node"}
            or result["status"] not in {"pending", "configured"}
            or result["changed"] is not (result["status"] == "pending")
            or result["generation"] != tailnet.RECOVERY_GENERATION
            or not re.fullmatch(r"[0-9a-f]{32}", result["nonce"])
            or result["binding_sha256"] != hashlib.sha256(tailnet._canonical_bytes(_binding(inputs))).hexdigest()):
        raise BootstrapError("bootstrap-capability-invalid")
    node, lease = result["node"], result["lease"]
    if (set(node) != {"id", "hostname", "ipv4", "ipv6"}
            or not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", node["id"])
            or node["hostname"] != "vpn-enroll-" + result["nonce"]
            or set(lease) != {"boot_id", "started_ms", "deadline_ms"}
            or str(UUID(lease["boot_id"])) != lease["boot_id"]
            or type(lease["started_ms"]) is not int or lease["started_ms"] < 0
            or type(lease["deadline_ms"]) is not int
            or lease["deadline_ms"] - lease["started_ms"] != tailnet.LEASE_SECONDS * 1000):
        raise BootstrapError("bootstrap-capability-invalid")
    tailnet.validate_sources([node["ipv4"], node["ipv6"]])
    if ipaddress.ip_address(node["ipv4"]).version != 4 or ipaddress.ip_address(node["ipv6"]).version != 6:
        raise BootstrapError("bootstrap-capability-invalid")
    return result


def _proofs(inputs, capability):
    from bootstrap_readiness import run_command, ReadinessError
    public = _probe(inputs, inputs.host)
    def sftp(host):
        command = inspection.sftp_command(host, inputs.known_hosts)
        command[1:1] = ["-o", "HostKeyAlgorithms=ssh-ed25519"]
        status, _ = run_command(command, timeout=20, environment=inputs.environment, input_data=b"pwd\nquit\n")
        if status:
            raise BootstrapError("bootstrap-sftp-failed")
    sftp(inputs.host)
    for family in ("ipv4", "ipv6"):
        host = {**inputs.host, "transport": capability["node"][family]}
        try:
            context = _probe(inputs, host)
            sftp(host)
        except (BootstrapError, ReadinessError):
            continue
        contexts = [public, context]
        tailnet._validate_external_contexts(_binding(inputs), capability["node"], contexts)
        return contexts
    raise BootstrapError("bootstrap-management-proof-failed")


def _publish(inputs, capability, contexts, parent_identity):
    import secrets
    path = Path(inputs.config["output"])
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".bootstrap-" + secrets.token_hex(16)
    created = False
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != parent_identity or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise BootstrapError("bootstrap-output-parent-changed")
        output = {"schema_version": 1, "status": "configured", "binding": _binding(inputs),
                  "confirmation": capability, "contexts": contexts}
        payload = tailnet._canonical_bytes(output)
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            os.fchmod(handle, 0o600)
            tailnet._write_all(handle, payload)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, path.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=fd)
        created = False
        os.fsync(fd)
    finally:
        if created:
            os.unlink(temporary, dir_fd=fd)
            os.fsync(fd)
        os.close(fd)


def run(inputs, auth_key):
    from bootstrap_readiness import wait_for_bootstrap
    from sshd_bundle_source import bundle_manifest
    if auth_key is not None:
        tailnet._validate_auth_key(auth_key)
    parent_identity = inputs.output_parent_identity
    binding = _binding(inputs)
    for fence in inputs.fences:
        deploy.verify_input_fence(fence)
    wait_for_bootstrap(inputs.ssh[:-1], environment=inputs.environment)
    generation, _manifest = bundle_manifest()
    deploy.require_recovery_foundation(inputs.ssh, generation, inputs.environment)
    installed = _installed(inputs)
    existing = _rpc(inputs, "status", binding=binding) if installed == "ready" else {"status": "idle"}
    if existing["status"] == "configured":
        configured = _capability(inputs, existing)
        contexts = _proofs(inputs, configured)
        for fence in inputs.fences:
            deploy.verify_input_fence(fence)
        _require_source(inputs)
        _publish(inputs, configured, contexts, parent_identity)
        return {"status": "configured", "changed": False, "vpn_acceptance": "not-performed"}
    if existing["status"] != "idle":
        raise BootstrapError("bootstrap-transaction-pending")
    if auth_key is None:
        raise BootstrapError("bootstrap-enrollment-key-required")
    _probe(inputs, inputs.host, preinstall=True)
    for fence in inputs.fences:
        deploy.verify_input_fence(fence)
    if installed != "ready":
        _install(inputs)
    for fence in inputs.fences:
        deploy.verify_input_fence(fence)
    _require_source(inputs)
    deploy.require_recovery_foundation(inputs.ssh, generation, inputs.environment)
    # The guest arms before all access writes. If an enroll reply is lost,
    # status may reconcile it; otherwise autonomous recovery retains authority.
    pending = None
    try:
        try:
            pending = _capability(inputs, _rpc(inputs, "enroll", binding=binding, auth_key=auth_key))
        except BootstrapError:
            pending = _capability(inputs, _rpc(inputs, "status", binding=binding))
        contexts = _proofs(inputs, pending)
        for fence in inputs.fences:
            deploy.verify_input_fence(fence)
        _require_source(inputs)
        try:
            configured = _capability(inputs, _rpc(inputs, "confirm", capability=pending, contexts=contexts))
        except BootstrapError:
            configured = _capability(inputs, _rpc(inputs, "status", binding=binding))
        if configured["status"] != "configured" or configured["nonce"] != pending["nonce"]:
            raise BootstrapError("bootstrap-confirmation-uncertain")
    except BaseException:
        if pending is not None:
            try:
                state = _rpc(inputs, "status", binding=binding)
                if state.get("status") == "pending":
                    _rpc(inputs, "rollback", capability=pending)
            except Exception:
                pass  # The durable timer remains authoritative; never claim rollback.
        raise
    # Publication failure cannot turn a confirmed transaction into a logout.
    _publish(inputs, configured, contexts, parent_identity)
    return {"status": "configured", "changed": True, "vpn_acceptance": "not-performed"}


def main():
    import sys
    from bootstrap_readiness import cancellation, ReadinessError
    try:
        with cancellation(), tempfile.TemporaryDirectory(prefix="vpn-tailnet-bootstrap-") as temporary:
            inputs = load_inputs(dict(os.environ), Path(temporary).resolve())
            result = run(inputs, os.environ.get("TAILSCALE_AUTH_KEY"))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BootstrapError, tailnet.Refusal, ReadinessError, inspection.InspectionError,
            deploy.DeployError, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "error", "reason": "bootstrap-failed", "action": "inspect-transaction-before-retrying"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
