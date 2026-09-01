#!/usr/bin/env python3
"""Onboard one sentinel through private preparation and a committed receipt.

Active onboarding intentionally uses the operator's SSH alias configuration;
passive inspection's separate ``-F /dev/null`` contract does not apply here.
Only fixed remote commands and bounded stdin bundles cross that connection.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys
import tempfile
import termios
import time
from uuid import UUID, uuid4

import yaml

from fleet_inspection import LIMIT as COMMAND_LIMIT, InspectionError, _open_local_file, bounded_command
from liveness_generation import JOB_TIMEOUT_SECONDS, RECEIPT_TIMEOUT
from liveness_profiles import ProfileError, build_profiles
from disposable_liveness_executor import ExecutorError, bind_executor, executor_command, load_live_executor

REPO = Path(__file__).resolve().parents[1]
LIMIT = 1024 * 1024
BUNDLE_LIMIT = COMMAND_LIMIT * 2
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SEMVER = re.compile(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?\Z")
PROVENANCE = {"controller_revision", "runner_sha256", "client_generation_id", "public_profile_digest", "vantage"}
TARGET_IDENTITY = {"inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at",
                   "required_profiles", "source_revision", "runner_sha256", "public_profile_digest"}


class InstallError(ValueError):
    """Categorical diagnostics only; subprocess/config contents stay private."""


def _read_awg_private_key(stream):
    try:
        if not stream.isatty():
            return stream.readline(128).rstrip("\r\n")
        descriptor = stream.fileno()
        original = termios.tcgetattr(descriptor)
        hidden = list(original)
        hidden[3] &= ~(termios.ECHO | termios.ECHONL)
        try:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, hidden)
            print("AWG private key (hidden): ", end="", file=sys.stderr, flush=True)
            return stream.readline(128).rstrip("\r\n")
        finally:
            # Discard unread terminal input before the shell regains echo.
            termios.tcsetattr(descriptor, termios.TCSAFLUSH, original)
    except (OSError, ValueError, termios.error):
        raise InstallError("private-key-terminal-unavailable") from None


def _run(command, *, environment=None, input_bytes=b"", timeout=30):
    try:
        return bounded_command(command, environment=environment, input_bytes=input_bytes, timeout=timeout, limit=LIMIT)
    except InspectionError:
        raise InstallError("command-failed") from None


def _read(path, private=False):
    try:
        with os.fdopen(_open_local_file(path, private), "rb") as stream:
            info = os.fstat(stream.fileno())
            if info.st_nlink != 1 or info.st_size > LIMIT:
                raise InstallError("unsafe-input")
            content = stream.read(LIMIT + 1)
        if len(content) > LIMIT:
            raise InstallError("oversized-input")
        return content
    except (OSError, InspectionError):
        raise InstallError("unsafe-input") from None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InstallError("duplicate-field")
        result[key] = value
    return result


def _json(content):
    try:
        return json.loads(content, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        raise InstallError("malformed-json") from None


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return _pairs((self.construct_object(key, deep=deep), self.construct_object(value, deep=deep)) for key, value in node.value)


def _yaml(path, private=False, *, allow_empty=False):
    try:
        document = yaml.load(_read(path, private), Loader=UniqueLoader)
    except yaml.YAMLError:
        raise InstallError("malformed-yaml") from None
    if document is None and allow_empty:
        return {}
    if not isinstance(document, dict):
        raise InstallError("invalid-document")
    return document


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_parent(path):
    missing = []
    cursor = path
    while not os.path.lexists(cursor):
        missing.append(cursor)
        cursor = cursor.parent
    for ancestor in (cursor, *cursor.parents):
        info = ancestor.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_root):
            raise InstallError("unsafe-state-parent")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        _sync(directory.parent)
    info = path.lstat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise InstallError("unsafe-state-parent")


def _write(path, content):
    _private_parent(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".liveness-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _save(path, value):
    _write(path, (json.dumps(value, sort_keys=True) + "\n").encode())


@contextmanager
def registry_lock(path):
    path = Path(path).expanduser().absolute()
    _private_parent(path.parent)
    fd = os.open(path.with_name(path.name + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise InstallError("unsafe-registry-lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("registry-busy") from None
        yield
    finally:
        os.close(fd)


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise InstallError("invalid-generation") from None
    return value


def _provenance(value):
    if not isinstance(value, dict) or set(value) != PROVENANCE:
        raise InstallError("invalid-provenance")
    for field, length in (("controller_revision", 40), ("runner_sha256", 64), ("public_profile_digest", 64)):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value[field]):
            raise InstallError("invalid-provenance")
    _uuid(value["client_generation_id"])
    if value["vantage"] not in ("external", "filtered"):
        raise InstallError("invalid-provenance")


def _target_identity(value, provenance, required):
    if (
        not isinstance(value, dict)
        or set(value) != TARGET_IDENTITY
        or value.get("required_profiles") != sorted(required)
        or value.get("source_revision") != provenance["controller_revision"]
        or value.get("runner_sha256") != provenance["runner_sha256"]
        or value.get("public_profile_digest") != provenance["public_profile_digest"]
        or type(value.get("applied_at")) is not int
        or value["applied_at"] < 1
        or not isinstance(value.get("inventory_alias"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value["inventory_alias"]) is None
        or any(not isinstance(value.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
               for key in ("public_service_address_sha256", "deployable_digest", "runner_sha256", "public_profile_digest"))
        or not isinstance(value.get("source_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["source_revision"]) is None
    ):
        raise InstallError("invalid-target-identity")


def _state(path, kind):
    if not os.path.lexists(path):
        return {"schema_version": 2, kind: {}}
    doc = _json(_read(path, private=True))
    if not isinstance(doc, dict) or set(doc) != {"schema_version", kind} or type(doc["schema_version"]) is not int or doc["schema_version"] != 2 or not isinstance(doc[kind], dict):
        raise InstallError("invalid-registry")
    allowed = {"client", "ssh_target", "ssh_transport_host", "ssh_host_key_alias", "generation_id", "provenance", "required_profiles", "policy", "vantage", "target_identity", "executor_binding_sha256"}
    clients = []
    for sid, entry in doc[kind].items():
        if not isinstance(sid, str) or not NAME.fullmatch(sid) or not isinstance(entry, dict) or set(entry) - allowed:
            raise InstallError("invalid-registry")
        if not isinstance(entry.get("client"), str) or not NAME.fullmatch(entry["client"]) or not isinstance(entry.get("ssh_target"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", entry["ssh_target"]):
            raise InstallError("invalid-registry")
        clients.append(entry["client"])
        for field in ("ssh_transport_host", "ssh_host_key_alias", "policy"):
            if field in entry and (not isinstance(entry[field], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", entry[field])):
                raise InstallError("invalid-registry")
        if ("ssh_transport_host" in entry) != ("ssh_host_key_alias" in entry):
            raise InstallError("invalid-registry")
        if "vantage" in entry and entry["vantage"] not in ("external", "filtered"):
            raise InstallError("invalid-registry")
        if "required_profiles" in entry:
            profiles = entry["required_profiles"]
            if not isinstance(profiles, list) or not profiles or any(p not in ("p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg") for p in profiles) or len(profiles) != len(set(profiles)):
                raise InstallError("invalid-registry")
        if not {"target_identity", "provenance", "required_profiles"} <= entry.keys():
            raise InstallError("invalid-registry")
        if kind == "pending" or "generation_id" in entry or "provenance" in entry:
            _uuid(entry.get("generation_id"))
            _provenance(entry.get("provenance"))
            _target_identity(entry.get("target_identity"), entry["provenance"], entry["required_profiles"])
        if "executor_binding_sha256" in entry and (not isinstance(entry["executor_binding_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["executor_binding_sha256"]) is None):
            raise InstallError("invalid-registry")
    if len(clients) != len(set(clients)):
        raise InstallError("duplicate-client-assignment")
    return doc


def _source_identity(repo):
    command = ["git", "-C", str(repo)]
    if _run(command + ["status", "--porcelain", "--untracked-files=normal"]):
        raise InstallError("source-must-be-clean-and-committed")
    revision = _run(command + ["rev-parse", "HEAD"]).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise InstallError("source-identity-invalid")
    runner = _run(command + ["show", revision + ":scripts/vpn-protocol-liveness.py"])
    engine = _run(command + ["show", revision + ":scripts/liveness_generation.py"])
    return revision, runner, engine


def _evaluator():
    spec = importlib.util.spec_from_file_location("liveness_evaluator", REPO / "scripts/protocol-liveness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selection(path, sid, client, environment):
    if not NAME.fullmatch(sid) or not NAME.fullmatch(client):
        raise InstallError("invalid-name")
    config = _yaml(path)
    evaluator = _evaluator()
    try:
        evaluator.validate_config(config)
    except evaluator.ConfigError:
        raise InstallError("configuration-migration-required") from None
    sentinels = [s for s in config["sentinels"] if s["id"] == sid]
    if len(sentinels) != 1:
        raise InstallError("sentinel-not-declared")
    sentinel = sentinels[0]
    policies = [p for p in config["policies"] if p["id"] == sentinel["policy"]]
    if len(policies) != 1:
        raise InstallError("policy-not-declared")
    required = policies[0]["required_profiles"]
    hosts, cohorts = environment.get("HOSTS", "").split(","), environment.get("COHORTS", "").split(",")
    if len(hosts) != len(cohorts) or len(hosts) != len(set(hosts)) or not hosts:
        raise InstallError("explicit-host-cohort-mapping-required")
    mapping = {}
    for pair, cohort in zip(hosts, cohorts):
        if not re.fullmatch(r"(?:upcloud|vultr|scaleway|hetzner):[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", pair) or not NAME.fullmatch(cohort):
            raise InstallError("explicit-host-cohort-mapping-required")
        mapping[pair] = cohort
    if environment.get("SOPS_FILES"):
        raise InstallError("shared-secrets-required")
    if "p2-amneziawg" in required:
        binding = sentinel.get("awg_target", {})
        if set(binding) != {"provider", "environment", "instance"} or f'{binding["provider"]}:{binding["environment"]}' not in mapping:
            raise InstallError("explicit-awg-binding-required")
    runtime = config["expected_runtime"]
    names = evaluator.required_runtime(policies[0])
    expected = {name: runtime.get(name) for name in names}
    for name, value in expected.items():
        if not isinstance(value, str) or not (re.fullmatch(r"[0-9a-f]{64}", value) if name == "awg_toolchain" else SEMVER.fullmatch(value)):
            raise InstallError("runtime-pin-migration-required")
    return config, sentinel, required, mapping, expected


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _awg_context(secrets, sentinel, mapping, environment):
    binding = sentinel["awg_target"]
    pair = f'{binding["provider"]}:{binding["environment"]}'
    role = REPO / "ansible/roles/amneziawg"
    merged = _yaml(role / "defaults/main.yml")
    for group in ("all", "vpn", "vpn-" + mapping[pair]):
        path = REPO / "ansible/group_vars" / (group + ".yml")
        if group == "vpn" and not path.exists():
            continue
        _merge(merged, _yaml(path, allow_empty=True))
    if merged.get("vpn", {}).get("enable_amneziawg") is not True:
        raise InstallError("awg-disabled-for-bound-host")
    cohort = merged.get("amneziawg_cohort", {})
    slug = merged.get("vpn", {}).get("awg_cohort", "")
    if not secrets.get("amneziawg_secrets", {}).get("instances") and slug:
        if not isinstance(slug, str) or not NAME.fullmatch(slug):
            raise InstallError("invalid-awg-cohort")
        cohort = _yaml(role / "vars/cohorts" / (slug + ".yml")).get("amneziawg_cohort", {})
    output = _run([str(REPO / "scripts/terraform-env.sh"), "output", "-raw", "server_ipv4"],
                  environment={**environment, "PROVIDER": binding["provider"], "ENV": binding["environment"]})
    try:
        endpoint = str(ipaddress.IPv4Address(output.decode().strip()))
    except (ValueError, UnicodeError):
        raise InstallError("invalid-awg-endpoint") from None
    return merged["amneziawg"], cohort, endpoint


def _derive(private, environment):
    tool = shutil.which("awg", path=environment.get("PATH")) or shutil.which("wg", path=environment.get("PATH"))
    if not tool:
        raise InstallError("awg-key-tool-unavailable")
    return _run([tool, "pubkey"], environment=environment, input_bytes=(private + "\n").encode()).decode().strip()


def _parsers(directory, profiles, expected, environment):
    for engine, filename, version_pattern, arguments in (
        ("sing-box", "sing-box.json", r"^sing-box version ([^\s]+)", ["check", "-c"]),
        ("xray", "xray.json", r"^Xray ([^\s]+)", ["run", "-test", "-config"]),
    ):
        if filename not in profiles:
            continue
        version = _run([engine, "version"], environment=environment).decode()
        match = re.match(version_pattern, version)
        if not match or match[1] != expected["sing_box" if engine == "sing-box" else engine]:
            raise InstallError("local-runtime-pin-mismatch")
        _run([engine, *arguments, str(directory / filename)], environment=environment, timeout=30)


def _ssh(sentinel, command, environment, input_bytes=b"", timeout=30, executor=None):
    allowed = ("PATH", "HOME") if executor is not None else ("PATH", "HOME", "SSH_AUTH_SOCK")
    ssh_environment = {key: environment[key] for key in allowed if key in environment}
    ssh_environment.update(LANG="C", LC_ALL="C")
    if executor is not None:
        return _run(list(executor_command(executor["profile"], command)), environment=ssh_environment,
                    input_bytes=input_bytes, timeout=timeout)
    args = ["ssh", *_evaluator().ssh_options(sentinel, 10), "--"]
    return _run([*args, sentinel["ssh_target"], command], environment=ssh_environment, input_bytes=input_bytes, timeout=timeout)


# All paths are fixed beneath a root-only tree. No archive extraction, user path,
# user-controlled executable or root shell is accepted by this receiver.
REMOTE_COMMON = r'''
import base64, fcntl, json, os, pathlib, stat, subprocess, sys, tempfile, uuid
ROOT = pathlib.Path('/etc/vpn-liveness')
OWNER = 0
generation = sys.argv[1]
if os.geteuid() != OWNER or str(uuid.UUID(generation)) != generation:
    raise SystemExit(1)
def check_dir(path):
    for parent in (path, *path.parents):
        st = parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, OWNER) or st.st_mode & 0o022:
            raise ValueError('unsafe-directory')
def make_dir(path):
    if not path.exists():
        check_dir(path.parent)
        path.mkdir(mode=0o700)
    check_dir(path)
    if path.stat().st_uid != OWNER or path.stat().st_mode & 0o077:
        raise ValueError('nonprivate-directory')
def read_file(path, private=True):
    check_dir(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != OWNER or st.st_nlink != 1 or st.st_mode & (0o077 if private else 0o022) or st.st_size > 1048576:
            raise ValueError('unsafe-file')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            data = handle.read(1048577)
        if len(data) > 1048576:
            raise ValueError('oversized-file')
        return data
    finally:
        os.close(fd)
def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
def write_new(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    sync(path.parent)
def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate-key')
        result[key] = value
    return result
'''

REMOTE_STAGE = REMOTE_COMMON + f"\nJOB_TIMEOUT_SECONDS = {JOB_TIMEOUT_SECONDS}\n" + r'''
import shutil
raw = sys.stdin.buffer.read(1048577)
if len(raw) > 1048576: raise ValueError('oversized-bundle')
bundle = json.loads(raw, object_pairs_hook=unique)
if set(bundle) != {'generation_id', 'engine', 'files'} or bundle['generation_id'] != generation:
    raise ValueError('invalid-bundle')
files = bundle['files']
allowed = {'runner.py', 'config.json', 'metadata.json', 'profiles/sing-box.json', 'profiles/xray.json', 'profiles/awg.conf'}
if not isinstance(files, dict) or not {'runner.py', 'config.json', 'metadata.json'} <= files.keys() or not files.keys() <= allowed:
    raise ValueError('invalid-files')
decoded = {name: base64.b64decode(data, validate=True) for name, data in files.items()}
engine = base64.b64decode(bundle['engine'], validate=True)
make_dir(ROOT)
lock = os.open(ROOT / 'generation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
st = os.fstat(lock)
if not stat.S_ISREG(st.st_mode) or st.st_uid != OWNER or st.st_nlink != 1 or st.st_mode & 0o077:
    raise ValueError('unsafe-lock')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
for directory in (ROOT / 'staging', ROOT / 'jobs'):
    make_dir(directory)
    sync(ROOT)
stage = ROOT / 'staging' / generation
if os.path.lexists(stage):
    make_dir(stage); make_dir(stage / 'profiles')
    actual = {p.name for p in stage.iterdir()}
    if actual != {'runner.py', 'config.json', 'metadata.json', 'profiles'} or {p.name for p in (stage / 'profiles').iterdir()} != {path.split('/')[1] for path in files if path.startswith('profiles/')}:
        raise ValueError('stage-conflict')
    if any(read_file(stage / name) != content for name, content in decoded.items()):
        raise ValueError('stage-conflict')
else:
    temporary = pathlib.Path(tempfile.mkdtemp(prefix='.candidate-', dir=stage.parent))
    try:
        (temporary / 'profiles').mkdir(mode=0o700)
        for name, content in decoded.items(): write_new(temporary / name, content)
        sync(temporary)
        temporary.rename(stage); sync(stage.parent)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
job = ROOT / 'jobs' / generation
engine_path = job / 'engine.py'
if os.path.lexists(job):
    make_dir(job)
    if {path.name for path in job.iterdir()} != {'engine.py'} or read_file(engine_path) != engine:
        raise ValueError('engine-conflict')
else:
    temporary = pathlib.Path(tempfile.mkdtemp(prefix='.job-', dir=job.parent))
    try:
        write_new(temporary / 'engine.py', engine)
        temporary.rename(job); sync(job.parent)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
os.close(lock)
unit = 'vpn-liveness-install-' + generation
state = subprocess.run(['/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', unit], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
if state.stdout.strip() not in (b'active', b'activating'):
    subprocess.run(['/usr/bin/systemd-run', '--quiet', '--no-block', '--collect', '--unit=' + unit,
        '--property=Type=oneshot', '--property=RuntimeMaxSec=' + str(JOB_TIMEOUT_SECONDS), '--property=TimeoutStartSec=' + str(JOB_TIMEOUT_SECONDS),
        '--property=KillMode=control-group', '--property=UMask=0077', '--property=StandardOutput=null', '--property=StandardError=null',
        '--', '/usr/bin/python3', '-I', '-B', '-S', str(engine_path), 'install', generation],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=True)
print('{"status":"queued"}')
'''

REMOTE_RECEIPT = REMOTE_COMMON + r'''
engine = ROOT / 'jobs' / generation / 'engine.py'
for directory in (ROOT, ROOT / 'jobs', ROOT / 'jobs' / generation):
    if os.path.lexists(directory):
        check_dir(directory)
        if directory.stat().st_uid != OWNER or directory.stat().st_mode & 0o077:
            raise ValueError('unsafe-directory')
private = True
if not os.path.lexists(engine):
    engine = pathlib.Path('/usr/local/lib/vpn-liveness/liveness_generation.py')
    private = False
if not os.path.lexists(engine):
    if os.path.lexists(ROOT):
        if any(os.path.lexists(ROOT / name) for name in ('pending.json', 'current')):
            raise ValueError('unresolved-state-without-engine')
        receipts = ROOT / 'receipts'
        if os.path.lexists(receipts):
            check_dir(receipts)
            if receipts.stat().st_mode & 0o077 or any(receipts.iterdir()):
                raise ValueError('unresolved-state-without-engine')
    print('{"state":"uncommitted"}')
else:
    read_file(engine, private=private)
    result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-S', str(engine), 'receipt', generation],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
    if result.returncode == 3:
        print('{"state":"uncommitted"}')
    elif result.returncode == 75:
        print('{"state":"running"}')
    elif result.returncode != 0:
        print('{"state":"refused"}')
    else:
        receipt = json.loads(result.stdout, object_pairs_hook=unique)
        print(json.dumps({'state': 'committed', 'receipt': receipt}))
'''


def _remote_command(code, generation):
    return "sudo -n /usr/bin/python3 -I -B -S -c " + shlex.quote(code) + " " + _uuid(generation)


def _receipt(sentinel, pending, environment, executor=None):
    response = _json(_ssh(sentinel, _remote_command(REMOTE_RECEIPT, pending["generation_id"]),
                          environment, executor=executor))
    if response == {"state": "uncommitted"}:
        return None
    if response == {"state": "running"}:
        return "running"
    if response == {"state": "refused"}:
        raise InstallError("remote-state-refused")
    if not isinstance(response, dict) or set(response) != {"state", "receipt"} or response["state"] != "committed":
        raise InstallError("invalid-remote-receipt")
    value = response["receipt"]
    expected = {"generation_id": pending["generation_id"], "status": "committed",
                "runner_sha256": pending["provenance"]["runner_sha256"], "provenance": pending["provenance"],
                "target_identity": pending["target_identity"]}
    if value != expected:
        raise InstallError("remote-receipt-identity-mismatch")
    return value


def _wait_receipt(sentinel, pending, environment, executor=None):
    deadline = time.monotonic() + RECEIPT_TIMEOUT
    while True:
        try:
            receipt = _receipt(sentinel, pending, environment, executor)
            if isinstance(receipt, dict):
                return receipt
        except InstallError as exc:
            if str(exc) != "command-failed":
                raise
        if time.monotonic() >= deadline:
            raise InstallError("installation-unknown-pending-preserved")
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def _publish(registry_path, registry, pending_path, pending, sid, entry):
    registry["sentinels"][sid] = entry
    _save(registry_path, registry)
    del pending["pending"][sid]
    _save(pending_path, pending)


def _audit(mapping, client, sid, environment):
    env = {key: environment[key] for key in ("HOME", "PATH", "AGE_KEY", "AUDIT_LOG_FILE") if key in environment}
    for pair in mapping:
        provider, deployment = pair.split(":")
        try:
            _run([str(REPO / "scripts/audit-log.sh"), "append-best-effort", "--action", "install-liveness-sentinel",
                  "--client", client, "--provider", provider, "--env", deployment, "--note", "sentinel=" + sid], environment=env)
        except InstallError:
            print("install-liveness-sentinel: audit-unavailable", file=sys.stderr)


def install(config_path, sid, client, registry_path, *, read_awg_stdin=False, stdin=None, environment=None,
            executor_manifest=None, executor_binding=None, cleanup_manifest=None):
    environment = dict(os.environ if environment is None else environment)
    config, sentinel, required, mapping, expected = _selection(config_path, sid, client, environment)
    registry_path = Path(registry_path).expanduser().absolute()
    pending_path = registry_path.with_name(registry_path.name + ".pending.json")
    transport = {key: sentinel[key] for key in ("ssh_target", "ssh_transport_host", "ssh_host_key_alias", "policy", "vantage") if key in sentinel}
    executor = None
    executor_environment = {key: environment[key] for key in ("PATH", "HOME") if key in environment}
    executor_runner = lambda command, **kwargs: _run(list(command), environment=executor_environment, **kwargs)
    if any(value is not None for value in (executor_manifest, executor_binding, cleanup_manifest)):
        if not all(value is not None for value in (executor_manifest, executor_binding, cleanup_manifest)):
            raise InstallError("executor-artifacts-required")
        declared = config.get("sentinels")
        if (not isinstance(declared, list) or len(declared) != 1
                or not isinstance(declared[0], dict) or declared[0].get("id") != sid):
            raise InstallError("executor-config")
        try:
            executor = load_live_executor(Path(executor_manifest), home=Path(environment.get("HOME", str(Path.home()))),
                                          now=int(time.time()), runner=executor_runner)
        except ExecutorError as exc:
            raise InstallError(str(exc)) from None
    with registry_lock(registry_path):
        registry, pending = _state(registry_path, "sentinels"), _state(pending_path, "pending")
        for entries in (registry["sentinels"], pending["pending"]):
            if any(value["client"] == client and key != sid for key, value in entries.items()):
                raise InstallError("client-already-assigned")
        previous = pending["pending"].get(sid)
        if previous is not None:
            if previous["client"] != client or any(previous.get(k) != transport.get(k) for k in ("ssh_target", "ssh_transport_host", "ssh_host_key_alias", "policy", "vantage")) or previous.get("required_profiles") != required or any(previous["target_identity"].get(k) != sentinel["target"].get(k) for k in sentinel["target"]):
                raise InstallError("pending-assignment-conflict")
            try:
                receipt = _receipt(sentinel, previous, environment, executor)
            except InstallError as exc:
                if str(exc) == "command-failed":
                    raise InstallError("installation-unknown-pending-preserved") from None
                raise
            if receipt == "running":
                receipt = _wait_receipt(sentinel, previous, environment, executor)
            if receipt is not None:
                _publish(registry_path, registry, pending_path, pending, sid, previous)
                _audit(mapping, client, sid, environment)
                return receipt
        revision, runner, engine = _source_identity(REPO)
        generation = previous["generation_id"] if previous else str(uuid4())
        private = None
        if "p2-amneziawg" in required:
            if not read_awg_stdin:
                raise InstallError("--awg-private-key-stdin-required")
            private = _read_awg_private_key(stdin if stdin is not None else sys.stdin)
            if not re.fullmatch(r"[A-Za-z0-9+/]{43}=", private):
                raise InstallError("invalid-private-key-stdin")
        with tempfile.TemporaryDirectory(prefix="vpn-liveness-install-") as directory:
            # macOS's system temporary directory starts beneath /var, a root
            # symlink. Canonicalize only our newly created owned directory.
            work = Path(directory).resolve()
            work.chmod(0o700)
            secrets_path = work / "secrets.yaml"
            env = {key: value for key, value in environment.items() if key not in ("VPN_SECRETS_FILE", "SECRETS_FILE", "SOPS_FILES")}
            _run([str(REPO / "scripts/decrypt-secrets.sh")], environment={**env, "SECRETS_FILE": str(secrets_path)}, timeout=60)
            secrets = _yaml(secrets_path, private=True)
            emit_env = {**env, "VPN_SECRETS_FILE": str(secrets_path)}
            emitted = [_json(_run([str(REPO / "scripts/emit-singbox.sh"), client, "--profile-format", fmt], environment=emit_env, timeout=120)) for fmt in ("sing-box", "ripdpi")]
            defaults, cohort, endpoint = {}, {}, None
            if "p2-amneziawg" in required:
                defaults, cohort, endpoint = _awg_context(secrets, sentinel, mapping, env)
            profiles = build_profiles(*emitted, secrets, client, required, sentinel.get("awg_target"), endpoint, private,
                                      lambda key: _derive(key, env), f"/etc/vpn-liveness/generations/{generation}/profiles",
                                      awg_defaults=defaults, awg_cohort=cohort)
            profile_servers = {item.get("server") for item in profiles["public_profiles"]
                               if isinstance(item, dict)}
            if (len(profile_servers) != 1 or None in profile_servers
                    or hashlib.sha256(next(iter(profile_servers)).encode()).hexdigest()
                    != sentinel["target"]["public_service_address_sha256"]):
                raise InstallError("target-profile-address-mismatch")
            provenance = {"controller_revision": revision, "runner_sha256": hashlib.sha256(runner).hexdigest(),
                          "client_generation_id": generation, "public_profile_digest": profiles["public_profile_digest"], "vantage": sentinel["vantage"]}
            _provenance(provenance)
            target_identity = {**sentinel["target"], "required_profiles": sorted(required), "source_revision": revision,
                               "runner_sha256": provenance["runner_sha256"], "public_profile_digest": profiles["public_profile_digest"]}
            _target_identity(target_identity, provenance, required)
            entry = {"client": client, **transport, "required_profiles": required, "generation_id": generation,
                     "provenance": provenance, "target_identity": target_identity}
            rendered = {name: (data if isinstance(data, str) else json.dumps(data, separators=(",", ":"))).encode() for name, data in profiles["files"].items()}
            for name, data in rendered.items():
                _write(work / name, data)
            _parsers(work, rendered, expected, env)
            if _source_identity(REPO) != (revision, runner, engine):
                raise InstallError("source-changed-during-preparation")
            if executor is not None:
                try:
                    bind_executor(Path(executor_manifest), Path(executor_binding), Path(config_path), Path(cleanup_manifest),
                                  sentinel=sid, client=client, generation_id=generation, provenance=provenance,
                                  target_identity=target_identity, home=Path(environment.get("HOME", str(Path.home()))),
                                  now=int(time.time()), runner=executor_runner)
                except ExecutorError as exc:
                    raise InstallError(str(exc)) from None
                entry["executor_binding_sha256"] = hashlib.sha256(Path(executor_binding).read_bytes()).hexdigest()
            if previous is not None and previous != entry:
                raise InstallError("pending-source-or-profile-conflict")
            user = _ssh(sentinel, "id -un", environment, executor=executor).decode().strip()
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
                raise InstallError("unsafe-remote-user")
            _ssh(sentinel, "sudo -n true", environment, executor=executor)
            runner_config = {"schema_version": 2, "sentinel": sid, "probe_url": config["probe_url"], "expected_status": config["expected_status"],
                             "timeout_seconds": config.get("probe_timeout_seconds", 15), "degraded_after_ms": config.get("degraded_after_ms", 3000),
                             "expected_runtime": expected, "provenance": provenance, "target_identity": target_identity, **profiles["runtime"]}
            metadata = {"generation_id": generation, "required_profiles": required, "ssh_user": user,
                        "provenance": provenance, "target_identity": target_identity}
            files = {"runner.py": runner, "config.json": json.dumps(runner_config, sort_keys=True).encode(), "metadata.json": json.dumps(metadata, sort_keys=True).encode(),
                     **{"profiles/" + name: data for name, data in rendered.items()}}
            bundle = json.dumps({"generation_id": generation, "engine": base64.b64encode(engine).decode(),
                                 "files": {name: base64.b64encode(data).decode() for name, data in files.items()}}, sort_keys=True).encode()
            if len(bundle) > BUNDLE_LIMIT:
                raise InstallError("candidate-too-large")
            pending["pending"][sid] = entry
            _save(pending_path, pending)
            try:
                _ssh(sentinel, _remote_command(REMOTE_STAGE, generation), environment, bundle,
                     timeout=60, executor=executor)
            except InstallError:
                # SSH loss does not establish whether the independent root job ran.
                pass
            receipt = _wait_receipt(sentinel, entry, environment, executor)
            _publish(registry_path, registry, pending_path, pending, sid, entry)
            _audit(mapping, client, sid, environment)
            return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sentinel", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--awg-private-key-stdin", action="store_true")
    parser.add_argument("--executor-manifest", type=Path)
    parser.add_argument("--executor-binding", type=Path)
    parser.add_argument("--cleanup-manifest", type=Path)
    args = parser.parse_args()
    registry = os.environ.get("LIVENESS_SENTINEL_REGISTRY", str(Path.home() / ".config/vpn-provision/liveness-sentinels.json"))
    try:
        receipt = install(args.config, args.sentinel, args.client, registry,
                          read_awg_stdin=args.awg_private_key_stdin,
                          executor_manifest=args.executor_manifest,
                          executor_binding=args.executor_binding,
                          cleanup_manifest=args.cleanup_manifest)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (InstallError, ProfileError, ExecutorError) as exc:
        print("install-liveness-sentinel: " + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        print("install-liveness-sentinel: operation-failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
