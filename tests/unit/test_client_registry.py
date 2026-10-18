"""Registry-resolved refresh semantics for scripts/issue-sub-token.sh.

Covers REQ-REFRESH-OPTIONS and the registry-write side of
REQ-REGISTRY-LIFECYCLE:
  * a bare --refresh-token reuses format/hosts recorded in client_registry;
  * an unregistered token fails closed before any remote write;
  * a successful issuance records status/options in the encrypted document.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
import re
import select
import signal
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER = REPO_ROOT / "scripts" / "issue-sub-token.sh"
BOOTSTRAP_ISSUER = REPO_ROOT / "scripts" / "issue-bootstrap.sh"
PORT_RESOLVER = REPO_ROOT / "scripts" / "resolve-subscription-port.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "secrets-sample.yml"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
REGISTERED_TOKEN = "fixture-token-for-contract-test"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def _sops_stub() -> str:
    body = """#!/bin/sh
set -eu
if [ "${ARG1:-}" = "set" ]; then
  value=$(cat)
  file="$3"
  path="$4"
  VALUE="$value" python3 - "$file" "$path" <<'PY'
import json, os, re, sys

file, path = sys.argv[1], sys.argv[2]
doc = json.load(open(file))
keys = re.findall(r'\["([^"]+)"\]', path)
node = doc
for key in keys[:-1]:
    node = node.setdefault(key, {})
node[keys[-1]] = json.loads(os.environ["VALUE"])
open(file, "w").write(json.dumps(doc))
PY
  exit 0
fi
for source_file do :; done
if [ "${3:-}" = '["client_registry"]' ]; then
  python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("client_registry", {})))' < "$source_file"
else
  python3 -c 'import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data)' < "$source_file"
fi
"""
    return body.replace("${ARG1:-}", "${1:-}")


def _harness(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    if not shutil_which("jq"):
        pytest.skip("jq is required")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps(yaml.safe_load(FIXTURE.read_text())))
    secrets_file.chmod(0o600)
    payload_file = tmp_path / "payload.json"
    meta_file = tmp_path / "meta.json"
    ssh_marker = tmp_path / "ssh-called"
    _write_executable(bin_dir / "sops", _sops_stub())
    _write_executable(
        bin_dir / "wg",
        "#!/bin/sh\ncat >/dev/null\nprintf 'fixture-server-public-key'\n",
    )
    _write_executable(
        bin_dir / "ssh",
        f"""#!{sys.executable}
import base64, json, os, pathlib, sys
cmd = sys.argv[-1]
if '--publication-ready' in cmd:
    if os.environ.get('PUBLISHER_PROTOCOL') == 'legacy':
        raise SystemExit(0)
    if os.environ.get('MIRROR_MODE') == '1':
        raise SystemExit(1)
    print('subscription-publisher-v1')
    raise SystemExit(0)
if '.vpn-sub-mirror-current' in cmd:
    raise SystemExit(1 if os.environ.get('MIRROR_MODE') == '1' else 0)
pathlib.Path({str(ssh_marker)!r}).touch()
data = sys.stdin.buffer.read()
if '--publish-sub' in cmd:
    doc = json.loads(data)
    pathlib.Path({str(payload_file)!r}).write_bytes(base64.b64decode(doc['payload_b64']))
    meta = dict(client=doc['client'])
    if doc['expires']:
        meta['expires'] = doc['expires']
    pathlib.Path({str(meta_file)!r}).write_text(json.dumps(meta))
    print('subscription-published-v1')
else:
    pathlib.Path({str(meta_file)!r} if '.meta' in cmd else {str(payload_file)!r}).write_bytes(data)
""",
    )
    env = os.environ.copy()
    tool_path = os.pathsep.join(
        entry
        for entry in env["PATH"].split(os.pathsep)
        if not entry.endswith("/mise/shims")
    )
    env.update(
        {
            "PATH": f"{bin_dir}:{STUBS_BIN}:{tool_path}",
            "HOME": str(tmp_path),
            "AGE_KEY": str(tmp_path / "age.key"),
            "AUDIT_LOG_FILE": str(tmp_path / "audit.log.age"),
            "AUDIT_ACTOR": "fixture",
            "AWG_HOST": "",
            "SOPS_FILE": str(secrets_file),
            "STUB_LOG": str(tmp_path / "stub.log"),
        }
    )
    return env, payload_file, ssh_marker, secrets_file


def shutil_which(name: str):
    from shutil import which

    return which(name)


@contextmanager
def _owned_command(arguments, **kwargs):
    child = subprocess.Popen(
        arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, **kwargs,
    )
    try:
        yield child
    finally:
        # Do not poll/reap the session leader before group cleanup: its PID
        # must remain reserved while this invocation can still own descendants.
        if child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.communicate(timeout=2)


def _run_issuer(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    arguments = ["bash", str(ISSUER), "phone", *args]
    with _owned_command(arguments, text=True, env=env, cwd=REPO_ROOT) as child:
        stdout, stderr = child.communicate(timeout=30)
        return subprocess.CompletedProcess(arguments, child.returncode, stdout, stderr)


def test_sops_fixture_reads_complete_document_before_output(tmp_path):
    fake = tmp_path / "sops"
    _write_executable(fake, _sops_stub().replace(
        "set -eu\n", "set -eu\nprintf 'fixture-ready\\n' >&2\n", 1,
    ))
    prefix = b'{"synthetic":'
    suffix = json.dumps("payload" * 2048).encode() + b"}"
    arguments = [str(fake), "--decrypt", "--input-type", "json",
                 "--output-type", "json", "/dev/stdin"]
    with _owned_command(arguments, stdin=subprocess.PIPE) as child:
        assert select.select([child.stderr], [], [], 3)[0], "fixture did not start"
        assert child.stderr.readline() == b"fixture-ready\n"
        child.stdin.write(prefix)
        child.stdin.flush()
        assert not select.select([child.stdout], [], [], 0.2)[0], (
            "the SOPS fixture must consume the complete input before publication"
        )
        stdout, stderr = child.communicate(input=suffix, timeout=5)
        assert child.returncode == 0, stderr
        assert stdout == prefix + suffix


def test_issuer_harness_timeout_reaps_its_owned_session():
    descendant = (
        "import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print(os.getpid(), flush=True); time.sleep(60)"
    )
    launcher = (
        "import subprocess,sys; "
        "child=subprocess.Popen([sys.executable, '-c', sys.argv[1]]); child.wait()"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        with _owned_command([sys.executable, "-c", launcher, descendant], text=True) as child:
            assert select.select([child.stdout], [], [], 3)[0], "descendant did not start"
            descendant_pid = int(child.stdout.readline())
            child.communicate(timeout=0.2)
    assert child.returncode is not None
    assert child.stdout.closed and child.stderr.closed
    status = subprocess.run(
        ["ps", "-p", str(descendant_pid), "-o", "stat="],
        capture_output=True, text=True, timeout=2,
    )
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z"), (
        "the TERM-resistant descendant escaped its owned session cleanup"
    )


def test_bare_refresh_reuses_registry_format_and_hosts(tmp_path: Path) -> None:
    env, payload_file, _, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "reused: format,expires" in result.stdout
    # Registry records formats [singbox, ripdpi]; last issued wins.
    payload = json.loads(payload_file.read_text())
    assert "ripdpi" in payload


def test_refresh_unregistered_token_fails_closed(tmp_path: Path) -> None:
    env, payload_file, ssh_marker, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", "totally-unregistered-token")
    assert result.returncode != 0
    assert "client_registry entry" in result.stderr
    assert not payload_file.exists()
    assert not ssh_marker.exists()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_refresh_refuses_foreign_or_ambiguous_client_before_publication(tmp_path, ambiguous):
    env, payload_file, ssh_marker, secrets_file = _harness(tmp_path)
    document = json.loads(secrets_file.read_text())
    registry = document["client_registry"]
    registry["other-device"] = dict(registry["phone"])
    if not ambiguous:
        del registry["phone"]
    secrets_file.write_text(json.dumps(document))
    before = secrets_file.read_bytes()

    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)

    assert result.returncode != 0
    assert ("ambiguous" if ambiguous else "requested client") in result.stderr
    assert "refresh payload format" not in result.stdout
    assert not payload_file.exists()
    assert not ssh_marker.exists()
    assert secrets_file.read_bytes() == before


@pytest.mark.parametrize("issuer", [ISSUER, BOOTSTRAP_ISSUER])
def test_issuers_refuse_direct_write_when_mirror_generation_is_active(
    tmp_path: Path, issuer: Path
) -> None:
    """A legacy write must not claim delivery once the mirror pointer is live."""
    env, payload_file, ssh_marker, _ = _harness(tmp_path)
    env["MIRROR_MODE"] = "1"
    result = subprocess.run(
        ["bash", str(issuer), "phone"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "mirror mode is active" in result.stderr
    assert not payload_file.exists()
    assert not ssh_marker.exists()


def _load_port_resolver():
    spec = importlib.util.spec_from_file_location(
        "resolve_subscription_port", PORT_RESOLVER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_grant_is_versioned_intrinsically_bounded_and_override_aware(
    tmp_path, monkeypatch
):
    module = _load_port_resolver()
    group_vars = tmp_path / "vars"
    group_vars.mkdir()
    (group_vars / "all.yml").write_text(
        "subscription:\n  bootstrap_max_lifetime_seconds: 120\n"
    )
    monkeypatch.setattr(module, "GROUP_VARS", group_vars)
    monkeypatch.setattr(module, "INVENTORY", tmp_path / "absent.ini")
    monkeypatch.setattr(module.time, "time", lambda: 1800000000)
    grant = module.bootstrap_grant("node.example.test", {})
    assert re.fullmatch(r"b1_1800000000_[A-Za-z0-9_-]{43}", grant["token"])
    assert grant["expires"] == 1800000120
    (group_vars / "vpn.yml").write_text(
        "subscription:\n  server_name: node.example.test\n"
    )
    # Higher-precedence dictionaries replace earlier policy rather than merging.
    assert module.bootstrap_grant("node.example.test", {})["lifetime"] == 604800
    assert (
        module.bootstrap_grant("node.example.test", {"_replace_policy": True})[
            "lifetime"
        ]
        == 604800
    )
    from datetime import datetime, timedelta, timezone

    tomorrow = (
        datetime.fromtimestamp(1800000000, timezone.utc) + timedelta(days=1)
    ).date()
    shortened = module.bootstrap_grant("node.example.test", {}, tomorrow.isoformat())
    assert 1800000000 < shortened["expires"] < 1800000000 + 604800
    assert (
        module.bootstrap_grant(
            "node.example.test", {"bootstrap_max_lifetime_seconds": 60}
        )["expires"]
        == 1800000060
    )
    for lifetime in (True, "60", 59, 2592001):
        with pytest.raises(ValueError):
            module.bootstrap_grant(
                "node.example.test", {"bootstrap_max_lifetime_seconds": lifetime}
            )
    for expiry in ("invalid", "2026-01-01", "2099-01-01", "2027-1-1"):
        with pytest.raises(ValueError):
            module.bootstrap_grant("node.example.test", {}, expiry)


def test_bootstrap_issuer_publishes_versioned_token_hash_and_bounded_metadata(tmp_path):
    env, payload, _, _ = _harness(tmp_path)
    result = subprocess.run(
        ["bash", str(BOOTSTRAP_ISSUER), "phone"],
        env=env,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    match = re.search(r"/bootstrap/(b1_([0-9]{10})_[A-Za-z0-9_-]{43})", result.stdout)
    assert match
    assert (
        json.loads((tmp_path / "meta.json").read_text())["expires"]
        == int(match[2]) + 604800
    )
    assert payload.exists()


def test_subscription_port_resolver_matches_effective_cohort_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issued URLs follow the same all/vpn/cohort precedence as the role."""
    module = _load_port_resolver()
    group_vars = tmp_path / "group_vars"
    group_vars.mkdir()
    (group_vars / "all.yml").write_text("subscription_port: 18444\n")
    (group_vars / "vpn.yml").write_text("subscription_port: 19444\n")
    (group_vars / "vpn-edge.yml").write_text("subscription_port: 20444\n")
    inventory = tmp_path / "generated.ini"
    inventory.write_text("[vpn-edge]\nnode.example.test\n")
    monkeypatch.setattr(module, "GROUP_VARS", group_vars)
    monkeypatch.setattr(module, "INVENTORY", inventory)
    assert module.resolve("node.example.test", 8444) == 20444


def test_refresh_explicit_override_wins_and_is_logged(tmp_path: Path) -> None:
    env, payload_file, _, _ = _harness(tmp_path)
    result = _run_issuer(
        env,
        "--format",
        "singbox",
        "--refresh-token",
        REGISTERED_TOKEN,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "overridden: format" in result.stdout
    payload = json.loads(payload_file.read_text())
    assert "ripdpi" not in payload


def test_fresh_issuance_records_registry_entry(tmp_path: Path) -> None:
    env, _, _, secrets_file = _harness(tmp_path)
    result = _run_issuer(env, "--format", "singbox", "--print-token-only")
    assert result.returncode == 0, result.stderr + result.stdout
    token = result.stdout.strip().splitlines()[-1]
    prefix = hashlib.sha256(token.encode()).hexdigest()[:8]
    doc = json.loads(secrets_file.read_text())
    entry = doc["client_registry"]["phone"]
    assert entry["status"] == "delivered"
    assert entry["token_hash_prefix"] == prefix
    assert entry["hosts"] == ["upcloud:prod"]
    assert "singbox" in entry["formats"]


def test_fresh_issuance_records_multi_host_env(tmp_path: Path) -> None:
    """HOSTS from the emitter environment must land in the registry.

    Regression: first issuance recorded only PROVIDER:ENV while the emitter
    consumed HOSTS, so a bare refresh downgraded a multi-host subscription
    to a single-host payload.
    """
    env, payload_file, _, secrets_file = _harness(tmp_path)
    multi_hosts = "upcloud:p0-upcloud,scaleway:p1-scaleway,vultr:p2-vultr"
    env["HOSTS"] = multi_hosts
    result = _run_issuer(env, "--format", "singbox", "--print-token-only")
    assert result.returncode == 0, result.stderr + result.stdout
    doc = json.loads(secrets_file.read_text())
    assert doc["client_registry"]["phone"]["hosts"] == multi_hosts.split(",")


def test_refresh_reports_ignored_emitter_environment(tmp_path: Path) -> None:
    """A refresh must say that env HOSTS/COHORTS lost to the registry.

    The registry is authoritative on refresh by design, but silently
    discarding an operator-supplied HOSTS= produced a payload that did not
    match the invocation with nothing in the output to explain it.
    """
    env, _, _, _ = _harness(tmp_path)
    env["HOSTS"] = "vultr:some-other-host"
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ignored: emitter HOSTS/COHORTS" in result.stdout


def test_refresh_without_emitter_environment_is_quiet(tmp_path: Path) -> None:
    env, _, _, _ = _harness(tmp_path)
    result = _run_issuer(env, "--refresh-token", REGISTERED_TOKEN)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ignored:" not in result.stdout


def test_issuer_revoke_hint_names_the_key_the_role_consumes() -> None:
    """The printed revoke instruction must name the consumed secrets key.

    The role renders the revocation file from `subscription.revoked_tokens`;
    the issuer used to tell operators to append the hash to
    `subscription.revoked_token_hashes`, which nothing reads — so a leaked
    token stayed valid after a by-the-book revocation.
    """
    role_tasks = (
        REPO_ROOT / "ansible/roles/subscription-host/tasks/enable.yml"
    ).read_text()
    iterated = set(re.findall(r"for \w+ in subscription\.(\w+)", role_tasks))
    assert iterated == {"revoked_tokens"}
    assert (
        set(re.findall(r"subscription\.(revoked_\w+)", (REPO_ROOT / "scripts/issue_sub_token.py").read_text())) == iterated
    )


@pytest.mark.parametrize(
    "script_name,arguments,artifact",
    [
        ("issue-sub-token.sh", ["--qr"], "phone.sub.qr.png"),
        ("issue-bootstrap.sh", ["--qr"], "phone.bootstrap.qr.png"),
        ("emit-qr.sh", [], "phone.qr.png"),
    ],
)
@pytest.mark.parametrize("legacy_output", [False, True])
def test_qr_output_is_private_at_creation(
    tmp_path, script_name, arguments, artifact, legacy_output
):
    env, _, _, _ = _harness(tmp_path)
    env["QR_MODE_LOG"] = str(tmp_path / "qr-mode")
    if legacy_output:
        (tmp_path / artifact).write_text("old credential")
        (tmp_path / artifact).chmod(0o644)
    _write_executable(
        tmp_path / "bin/qrencode",
        """#!/usr/bin/env python3
import os, pathlib, stat, sys
output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
with output.open('wb') as stream:
    stream.write(sys.stdin.buffer.read())
    pathlib.Path(os.environ['QR_MODE_LOG']).write_text(str(stat.S_IMODE(os.fstat(stream.fileno()).st_mode)))
""",
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / script_name), "phone", *arguments],
        env=env,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        umask=0o022,
    )
    assert result.returncode == 0, result.stderr
    assert int((tmp_path / "qr-mode").read_text()) == 0o600
    assert (tmp_path / artifact).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("script_name", ["issue-sub-token.sh", "issue-bootstrap.sh"])
@pytest.mark.parametrize(
    "directory",
    ["/opt/o'brien", "relative/path", "/opt/../evil", "/opt/$(id)", "/opt/space dir"],
)
def test_subscription_directory_rejected_before_external_commands(
    tmp_path, script_name, directory
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / script_name
    script.write_text((REPO_ROOT / "scripts" / script_name).read_text())
    if script_name == "issue-sub-token.sh":
        for module in ("issue_sub_token.py", "client_payload.py", "fleet_inspection.py", "client_delivery_identity.py", "awg_client.py", "awg_device_binding.py", "encrypted_client_document.py", "transport_semantics.py", "ripdpi_cohort_fingerprint.py"):
            (scripts / module).write_text((REPO_ROOT / "scripts" / module).read_text())
    marker = tmp_path / "external-call"
    _write_executable(
        scripts / "terraform-env.sh", f"#!/bin/sh\ntouch {marker}\nexit 73\n"
    )
    result = subprocess.run(
        ["bash", str(script), "phone"],
        env={**os.environ, "SUBSCRIPTION_DIR": directory, "HOME": str(tmp_path), "SOPS_FILE": str(tmp_path / "absent.sops.yaml")},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2, result.stderr
    assert ("private transaction refused" if script_name == "issue-sub-token.sh" else "SUBSCRIPTION_DIR must be") in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("script_name", ["issue-sub-token.sh", "issue-bootstrap.sh"])
def test_safe_subscription_directory_reaches_next_stage(tmp_path, script_name):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / script_name
    script.write_text((REPO_ROOT / "scripts" / script_name).read_text())
    if script_name == "issue-sub-token.sh":
        for module in ("issue_sub_token.py", "client_payload.py", "fleet_inspection.py", "client_delivery_identity.py", "awg_client.py", "awg_device_binding.py", "encrypted_client_document.py", "transport_semantics.py", "ripdpi_cohort_fingerprint.py"):
            (scripts / module).write_text((REPO_ROOT / "scripts" / module).read_text())
    marker = tmp_path / "external-call"
    _write_executable(
        scripts / "terraform-env.sh", f"#!/bin/sh\ntouch {marker}\nexit 73\n"
    )
    result = subprocess.run(
        ["bash", str(script), "phone"],
        env={**os.environ, "SUBSCRIPTION_DIR": "/var/lib/vpn-subscription", "HOME": str(tmp_path), "SOPS_FILE": str(tmp_path / "absent.sops.yaml")},
        capture_output=True,
        text=True,
        timeout=5,
    )
    if script_name == "issue-sub-token.sh":
        # Encrypted authority is now admitted before endpoint lookup.
        assert result.returncode == 2 and "private transaction unavailable" in result.stderr
        assert not marker.exists()
    else:
        assert result.returncode == 73, result.stderr
        assert marker.exists()


def test_first_token_initializes_schema_valid_no_awg_state(tmp_path):
    import jsonschema
    env, _, _, secrets_file = _harness(tmp_path)
    document = json.loads(secrets_file.read_text())
    document.pop('client_registry', None)
    for instance in document['amneziawg_secrets']['instances']:
        instance['peers'] = [peer for peer in instance['peers'] if peer['name'] != 'phone']
    secrets_file.write_text(json.dumps(document))
    result = _run_issuer(env, '--format', 'singbox', '--print-token-only')
    assert result.returncode == 0, result.stderr
    document = json.loads(secrets_file.read_text())
    entry = document['client_registry']['phone']
    assert entry['awg_binding'] is None
    assert entry['awg_private_key'] == entry['awg_public_key_fingerprint'] == ''
    schema = json.loads((REPO_ROOT / 'secrets/schema.json').read_text())
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(document))


def test_token_delivery_preserves_existing_awg_authority(tmp_path):
    env, _, _, secrets_file = _harness(tmp_path)
    document = json.loads(secrets_file.read_text())
    expected = {key: value for key, value in document['client_registry']['phone'].items() if key.startswith('awg_')}
    assert expected['awg_binding'] is not None
    result = _run_issuer(env, '--format', 'singbox', '--print-token-only')
    assert result.returncode == 0, result.stderr
    actual = json.loads(secrets_file.read_text())['client_registry']['phone']
    assert {key: value for key, value in actual.items() if key.startswith('awg_')} == expected


@pytest.mark.parametrize('selected_host', ['upcloud:prod', 'vultr:prod'])
@pytest.mark.parametrize('ambient', [None, 'conflicting'])
def test_refresh_restores_persisted_awg_host_across_multiple_enabled_hosts(tmp_path, selected_host, ambient):
    env, payload_file, _, secrets_file = _harness(tmp_path)
    document = json.loads(secrets_file.read_text())
    document['hysteria']['masquerade_url'] = 'https://vpn.example.com'
    secrets_file.write_text(json.dumps(document))
    from copy import deepcopy
    from awg_device_binding import public_key
    import base64
    other = deepcopy(document)
    private = base64.b64encode(bytes([9]) * 32).decode()
    public = public_key(private)
    other['amneziawg_secrets']['instances'][0].update(
        listen_port=51821, server_private_key=base64.b64encode(bytes([55]) * 32).decode())
    other['amneziawg_secrets']['instances'][0]['peers'][0]['public_key'] = public
    other['client_registry']['phone'].update(
        hosts=['vultr:prod'], awg_private_key=private,
        awg_public_key_fingerprint='sha256:' + hashlib.sha256(public.encode()).hexdigest()[:16],
        awg_binding={'provider': 'vultr', 'environment': 'prod', 'instance': 'awg0'})
    other_file = tmp_path / 'other.json'
    other_file.write_text(json.dumps(other))
    other_file.chmod(0o600)
    env.update(HOSTS='upcloud:prod,vultr:prod', COHORTS='p2-udp,p2-udp', AWG_HOST=selected_host,
               SOPS_FILES=str(secrets_file) + ',' + str(other_file))
    initial = _run_issuer(env, '--format', 'ripdpi', '--print-token-only')
    assert initial.returncode == 0, initial.stderr
    original = json.loads(payload_file.read_text())['ripdpi']['amneziawg']
    assert len(original) == 1
    assert original[0]['peer']['endpoint'].endswith(':51821' if selected_host == 'vultr:prod' else ':51820')
    token = initial.stdout.strip().splitlines()[-1]
    for name in ('HOSTS', 'COHORTS', 'AWG_HOST'):
        env.pop(name, None)
    if ambient:
        env['AWG_HOST'] = 'vultr:prod' if selected_host == 'upcloud:prod' else 'upcloud:prod'
    refreshed = _run_issuer(env, '--refresh-token', token)
    assert refreshed.returncode == 0, refreshed.stderr
    assert json.loads(payload_file.read_text())['ripdpi']['amneziawg'] == original
    assert json.loads(secrets_file.read_text())['client_registry']['phone']['awg_delivery_host'] == selected_host


def test_refresh_requires_recorded_delivery_selection(tmp_path):
    env, _, ssh_marker, secrets_file = _harness(tmp_path)
    document = json.loads(secrets_file.read_text())
    del document['client_registry']['phone']['awg_delivery_host']
    secrets_file.write_text(json.dumps(document))
    result = _run_issuer(env, '--refresh-token', REGISTERED_TOKEN)
    assert result.returncode != 0 and 'delivery selection' in result.stderr
    assert not ssh_marker.exists()


@pytest.mark.parametrize("selector", ["invalid", "upcloud:Prod", "vultr:prod"])
def test_invalid_delivery_selector_refuses_before_publication(tmp_path, selector):
    env, _, ssh_marker, secrets_file = _harness(tmp_path)
    before = secrets_file.read_bytes()
    env.update(AWG_HOST=selector, HOSTS="upcloud:prod")
    result = _run_issuer(env, "--print-token-only")
    assert result.returncode != 0 and "private transaction refused" in result.stderr
    assert not ssh_marker.exists()
    assert secrets_file.read_bytes() == before


def test_old_delivery_runtime_refuses_before_any_remote_publication(tmp_path):
    env, payload_file, ssh_marker, secrets_file = _harness(tmp_path)
    env["PUBLISHER_PROTOCOL"] = "legacy"
    before = secrets_file.read_bytes()
    result = subprocess.run(["bash", str(ISSUER), "phone"], capture_output=True,
                            text=True, env=env, cwd=REPO_ROOT, check=False)
    assert result.returncode == 2
    assert "publisher unavailable" in result.stderr
    assert not payload_file.exists() and not ssh_marker.exists()
    assert secrets_file.read_bytes() == before
