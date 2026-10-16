"""Typed public/private ECH boundaries; native acceptance is a separate lane."""

from __future__ import annotations
import base64
import copy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
import pytest
import yaml

from transport_semantics import ech_config, ech_keys_config, hysteria_errors
from template_render import merge_render_vars, render_fragment, render_template
from test_emit_singbox_roundtrip import (
    _secrets_as_json,
    _build_env,
    SCRIPT,
    BUNDLE_SCRIPT,
)
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def authority(public_name="outer.example", inner_name="vpn.example.com"):
    private = X25519PrivateKey.generate()

    def vector(raw):
        return len(raw).to_bytes(2, "big") + raw

    body = b"\x01\x00\x20" + vector(private.public_key().public_bytes_raw())
    body += (
        vector(b"\x00\x01\x00\x01")
        + b"\x00"
        + bytes([len(public_name)])
        + public_name.encode()
        + b"\x00\x00"
    )
    config = b"\xfe\x0d" + vector(body)
    config_list = vector(config)
    pem = (
        "-----BEGIN ECH KEYS-----\n"
        + base64.b64encode(
            vector(private.private_bytes_raw()) + vector(config)
        ).decode()
        + "\n-----END ECH KEYS-----\n"
    )
    return {
        "profile": "ech-required",
        "generation": hashlib.sha256(config_list).hexdigest(),
        "inner_name": inner_name,
        "public_name": public_name,
        "config_list": base64.b64encode(config_list).decode(),
        "keys_pem": pem,
    }


def hysteria(ech):
    return {
        "version": "v2.13.0",
        "masquerade_url": "https://vpn.example.com",
        "ech": ech,
    }


def test_real_key_agreement_and_public_generation():
    ech = authority()
    assert ech_keys_config(ech["keys_pem"], verify_private=True) == ech["config_list"]
    assert ech_config(ech["config_list"]) == ["outer.example"]
    assert not hysteria_errors(hysteria(ech))


@pytest.mark.parametrize('name', ['192.0.2.1', '2001:db8::1'])
@pytest.mark.parametrize('field', ['public', 'inner'])
def test_ech_generation_refuses_literal_ip_identities_before_binary_acquisition(tmp_path, name, field):
    from hysteria_ech import generate
    public, inner = (name, 'vpn.example.com') if field == 'public' else ('outer.example', name)
    with pytest.raises(ValueError, match='invalid-ech-identities'):
        generate(tmp_path / 'not-acquired', public, inner)


@pytest.mark.parametrize('invocation', ['import', 'inline'])
def test_ech_probe_resolves_installed_authority_without_repository_python_path(tmp_path, invocation):
    library = tmp_path / "libexec" / "ripdpi-transport-egress"
    library.mkdir(parents=True)
    shutil.copyfile(ROOT / "ansible/roles/runtime-release/files/transport_runtime_probe.py",
                    library / "transport_runtime_probe.py")
    shutil.copyfile(ROOT / "scripts/transport_semantics.py",
                    library / "transport_semantics.py")
    (library.parent / "transport_semantics.py").write_text(
        "raise RuntimeError('previous frontend semantic helper must not be loaded')\n")
    preparation = yaml.safe_load((ROOT / "ansible/roles/transport-egress/tasks/runtime-prepare.yml").read_text())
    companion = next(task for task in preparation if task["name"] ==
                     "Install the exact semantic companion before consumer admission")
    assert companion["ansible.builtin.copy"] == {
        "src": "{{ role_path }}/../../../scripts/transport_semantics.py",
        "dest": "{{ transport_egress_libexec_dir }}/transport_semantics.py",
        "owner": "root", "group": "root", "mode": "0644"}
    assert preparation.index(companion) < next(i for i, task in enumerate(preparation)
                                              if "ansible.builtin.command" in task)
    ech = authority()
    key = tmp_path / "ech.key"
    key.write_text(ech["keys_pem"])
    key.chmod(0o600)
    document = {"auth": {"type": "userpass", "userpass": {"probe": "synthetic-password"}},
                "listen": ":443", "masquerade": {"proxy": {"url": "https://vpn.example.com"}},
                "ech": {"keyPath": str(key)}}
    loading = ("sys.path.insert(0,sys.argv[1]);from transport_runtime_probe import hysteria_client;"
               if invocation == 'import' else
               "import types;from pathlib import Path;module=types.ModuleType('transport_runtime_probe');"
               "module.__file__=str(Path(sys.argv[1])/'transport_runtime_probe.py');"
               "exec(Path(module.__file__).read_text(),module.__dict__);hysteria_client=module.hysteria_client;")
    source = ("import json,sys;" + loading +
              "print(json.dumps(hysteria_client(json.load(sys.stdin),1080,'owned-ca.pem','probe')))")
    result = subprocess.run([sys.executable, "-I", "-c", source, str(library)],
                            input=json.dumps(document), cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    client = json.loads(result.stdout)
    assert client["tls"] == {"sni": "vpn.example.com", "ca": "owned-ca.pem",
                             "insecure": False, "ech": ech["config_list"]}


@pytest.mark.parametrize(
    "mutation",
    [
        "key",
        "config",
        "generation",
        "inner",
        "outer",
        "same-name",
        "version",
        "obfs",
        "profile",
        "unknown",
    ],
)
def test_mismatched_or_unsafe_ech_authority_refuses(mutation):
    ech = authority()
    doc = hysteria(ech)
    if mutation == "key":
        ech["keys_pem"] = authority()["keys_pem"]
    elif mutation == "config":
        ech["config_list"] += "AAAA"
    elif mutation == "generation":
        ech["generation"] = "0" * 64
    elif mutation == "inner":
        ech["inner_name"] = "wrong.example"
    elif mutation == "outer":
        ech["public_name"] = "wrong.example"
    elif mutation == "same-name":
        ech["inner_name"] = ech["public_name"]
    elif mutation == "version":
        doc["version"] = "v2.9.0"
    elif mutation == "obfs":
        doc["salamander_enabled"] = True
    elif mutation == "profile":
        ech["profile"] = "opportunistic"
    elif mutation == "unknown":
        ech["private_path"] = "/etc/foreign"
    assert hysteria_errors(doc)


@pytest.mark.parametrize("raw", ["", "AAAA", "../private", "====", "A" * 16385])
def test_invalid_public_config_never_becomes_a_path(raw):
    with pytest.raises(ValueError, match="invalid-ech-config"):
        ech_config(raw)


def test_render_private_key_uses_root_systemd_credential():
    variables = merge_render_vars()
    ech = authority()
    variables["hysteria"]["ech"] = ech
    rendered = render_template(
        ROOT / "ansible/roles/hysteria/templates/config.yaml.j2", variables
    )
    unit = render_template(
        ROOT / "ansible/roles/hysteria/templates/hysteria-server.service.j2", variables
    )
    assert yaml.safe_load(rendered)["ech"] == {
        "keyPath": "/run/credentials/hysteria-server.service/hysteria-ech"
    }
    assert "LoadCredential=hysteria-ech:/etc/hysteria/ech.key" in unit
    assert ech["keys_pem"] not in rendered + unit


@pytest.mark.parametrize("identity", ["ech", "explicit", "frontend"])
def test_smoke_client_retains_exact_verified_tls_identity(identity):
    def tasks(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from tasks(child)
        elif isinstance(value, list):
            for child in value:
                yield from tasks(child)
    source = yaml.safe_load((ROOT / "ansible/playbooks/smoke-test.yml").read_text())
    task = next(task for task in tasks(source) if task.get("name") == "Render Hysteria client config")
    variables = merge_render_vars()
    expected = variables["nginx_xhttp"]["server_name"]
    if identity == "ech":
        expected = "separate.example"
        variables["hysteria"]["ech"] = authority(inner_name=expected)
    elif identity == "explicit":
        expected = "explicit.example"
        variables["hysteria"]["server_name"] = expected
    rendered = render_fragment("hysteria-smoke-client.yaml", task["ansible.builtin.copy"]["content"], variables)
    client = yaml.safe_load(rendered)
    assert client["tls"]["sni"] == expected
    assert client["tls"]["insecure"] is False
    assert ("ech" in client["tls"]) is (identity == "ech")
    assert client["tls"]["ca"] == variables["hysteria_config_dir"] + "/server.fullchain.pem"


@pytest.mark.parametrize(
    "profile", ["bandwidth-capped", "bbr-conservative", "bbr-standard"]
)
def test_resource_profiles_render_exact_native_api(profile):
    variables = merge_render_vars()
    variables["hysteria"]["resource_profile"] = profile
    doc = yaml.safe_load(
        render_template(
            ROOT / "ansible/roles/hysteria/templates/config.yaml.j2", variables
        )
    )
    if profile.startswith("bbr-"):
        assert doc["congestion"] == {"type": "bbr", "bbrProfile": profile[4:]}
        assert doc["ignoreClientBandwidth"] is True
    else:
        assert "congestion" not in doc
    assert doc["quic"]["maxConnReceiveWindow"] == 20971520


@pytest.mark.parametrize("identity", ["frontend", "separate-ech"])
def test_emitter_keeps_ech_and_refuses_unqualified_bundle(tmp_path, identity):
    source = _secrets_as_json(tmp_path)
    document = json.loads(source.read_text())
    inner = document["nginx_xhttp"]["server_name"] if identity == "frontend" else "separate.example"
    ech = authority(inner_name=inner)
    document["hysteria"].update(
        version="v2.13.0", ech=ech, masquerade_url="https://" + inner
    )
    document["client_registry"] = {"laptop": {"status": "active"}}
    source.write_text(json.dumps(document))
    env = _build_env(tmp_path, source)
    result = subprocess.run(
        ["bash", str(SCRIPT), "laptop"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    outbound = next(
        x for x in json.loads(result.stdout)["outbounds"] if x["type"] == "hysteria2"
    )
    assert outbound["tls"]["ech"]["config"][1] == ech["config_list"]
    assert outbound["tls"]["server_name"] == inner
    assert "ECH KEYS" not in result.stdout + result.stderr
    bundle = subprocess.run(
        ["bash", str(BUNDLE_SCRIPT), "laptop"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert bundle.returncode != 0 and not bundle.stdout
    assert "RIPDPI export is unsupported" in bundle.stderr
    xhttp = subprocess.run(
        ["bash", str(SCRIPT), "laptop", "--xhttp-only", "--profile-format", "ripdpi"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert xhttp.returncode == 0, xhttp.stderr
    intermediate = json.loads(xhttp.stdout)
    assert not any(x["type"] == "hysteria2" for x in intermediate["outbounds"])
    from liveness_profiles import build_profiles, ProfileError

    arguments = (
        json.loads(result.stdout),
        intermediate,
        document,
        "laptop",
        ["p1-xhttp", "p2-hysteria2"],
        None,
        None,
        None,
        lambda _key: None,
        "/private/profiles",
    )
    profiles = build_profiles(*arguments, awg_defaults={}, awg_cohort={})
    retained = next(
        x
        for x in profiles["files"]["sing-box.json"]["outbounds"]
        if x["type"] == "hysteria2"
    )
    assert retained["tls"]["ech"] == outbound["tls"]["ech"]
    del next(x for x in arguments[0]["outbounds"] if x["type"] == "hysteria2")["tls"][
        "ech"
    ]
    with pytest.raises(ProfileError, match="wrong-hysteria-ech-generation"):
        build_profiles(*arguments, awg_defaults={}, awg_cohort={})


def test_wrong_private_scalar_with_same_public_metadata_refuses():
    ech = authority()
    raw = bytearray(base64.b64decode(ech["keys_pem"].splitlines()[1]))
    raw[2] ^= 1
    # Change a non-clamped scalar bit to alter its public key.
    raw[3] ^= 1
    ech["keys_pem"] = (
        "-----BEGIN ECH KEYS-----\n"
        + base64.b64encode(raw).decode()
        + "\n-----END ECH KEYS-----\n"
    )
    assert hysteria_errors(hysteria(ech))


@pytest.mark.parametrize('profile', ['ech', 'bbr-conservative', 'bbr-standard'])
def test_bundle_refuses_internal_monitoring_flag_before_emission(tmp_path, profile):
    source = _secrets_as_json(tmp_path)
    document = json.loads(source.read_text())
    document['hysteria']['version'] = 'v2.13.0'
    if profile == 'ech':
        document['hysteria']['ech'] = authority(inner_name=document['nginx_xhttp']['server_name'])
    else:
        document['hysteria']['resource_profile'] = profile
    source.write_text(json.dumps(document))
    environment = _build_env(tmp_path, source)
    result = subprocess.run(['bash', str(BUNDLE_SCRIPT), 'laptop', '--xhttp-only'],
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and not result.stdout
    assert '--xhttp-only is reserved for monitoring' in result.stderr
    assert not Path(environment['STUB_LOG']).exists()


@pytest.mark.parametrize('profile', ['bbr-conservative', 'bbr-standard'])
def test_bbr_recipient_requires_qualified_engine_and_retains_paired_xhttp(tmp_path, profile):
    source = _secrets_as_json(tmp_path)
    document = json.loads(source.read_text())
    document['hysteria'].update(version='v2.13.0', resource_profile=profile)
    source.write_text(json.dumps(document))
    environment = _build_env(tmp_path, source)
    def emit(*arguments):
        return subprocess.run(['bash', str(SCRIPT), 'laptop', *arguments],
                              env=environment, capture_output=True, text=True, timeout=30)
    supported = emit()
    assert supported.returncode == 0, supported.stderr
    outbound = next(value for value in json.loads(supported.stdout)['outbounds'] if value['type'] == 'hysteria2')
    assert outbound['bbr_profile'] == profile.removeprefix('bbr-')
    refused = emit('--profile-format', 'ripdpi')
    assert refused.returncode != 0 and not refused.stdout
    assert 'BBR resource profiles require' in refused.stderr
    paired = emit('--profile-format', 'ripdpi', '--xhttp-only')
    assert paired.returncode == 0, paired.stderr
    assert not any(value['type'] == 'hysteria2' for value in json.loads(paired.stdout)['outbounds'])
    spec = importlib.util.spec_from_file_location('bbr_liveness_check', ROOT / 'scripts/check-liveness-profile-compatibility.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    directory = tmp_path / 'liveness'
    directory.mkdir(mode=0o700)
    paths = checker.render_profiles(directory, document=document)
    sentinel = json.loads(paths['sing-box.json'].read_text())
    assert next(value for value in sentinel['outbounds'] if value['type'] == 'hysteria2')['bbr_profile'] == profile.removeprefix('bbr-')
    assert paths['xray.json'].is_file()


def test_publication_age_channel_hash_and_unknown_advisories():
    from datetime import datetime, timezone, timedelta
    from hysteria_release import publication_eligible

    now = datetime.now(timezone.utc)
    release = {
        "tag_name": "v1.14.3",
        "draft": False,
        "prerelease": False,
        "published_at": (now - timedelta(hours=48)).isoformat(),
        "assets": [{"name": "asset", "digest": "sha256:" + "a" * 64}],
    }
    assert publication_eligible(release, "v1.14.3", {"asset": "a" * 64}, [], now)
    assert not publication_eligible(release, "v1.14.3", {"asset": "a" * 64}, None, now)
    assert not publication_eligible(
        release, "v1.14.3", {"asset": "a" * 64}, [{"severity": "high"}], now
    )
    for field, value in [
        ("prerelease", True),
        ("draft", True),
        ("published_at", (now - timedelta(hours=47)).isoformat()),
        ("tag_name", "v1.14.4"),
    ]:
        bad = copy.deepcopy(release)
        bad[field] = value
        assert not publication_eligible(bad, "v1.14.3", {"asset": "a" * 64}, [], now)
    assert not publication_eligible(release, "v1.14.3", {"asset": "b" * 64}, [], now)


def test_make_issuance_captures_literal_inputs_without_operator_configuration(tmp_path):
    marker = tmp_path / "must-not-execute"
    hostile = "$(shell touch " + str(marker) + ")"
    environment = dict(
        os.environ,
        SOPS_FILE=hostile,
        HYSTERIA_ECH_PUBLIC_NAME=hostile,
        HYSTERIA_ECH_INNER_NAME=hostile,
        HYSTERIA_BINARY=hostile,
    )
    result = subprocess.run(
        ["make", "-n", "issue-hysteria-ech"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0 and not marker.exists()
    assert "$(shell touch" not in result.stdout
    refused = subprocess.run(
        ["make", "-n", "issue-hysteria-ech", "deploy"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert refused.returncode != 0 and not marker.exists()


def test_exact_runtime_contract_matches_current_pins_and_all_architectures():
    pins = json.loads((ROOT / "scripts/hysteria-runtimes.json").read_text())
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    assert pins["hysteria"]["version"] == example["hysteria"]["version"] == "v2.13.0"
    for name in ("hysteria", "sing_box"):
        assert set(pins[name]["sha256"]) == {
            "linux-amd64",
            "linux-arm64",
            "darwin-arm64",
        }
        assert all(len(digest) == 64 for digest in pins[name]["sha256"].values())
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    unit = next(
        job
        for job in workflow["jobs"].values()
        if "SING_BOX_CLIENT_VERSION" in job.get("env", {})
    )
    assert unit["env"]["SING_BOX_CLIENT_VERSION"] == pins["sing_box"]["version"]
    assert (
        unit["env"]["SING_BOX_CLIENT_LINUX_AMD64_SHA256"]
        == pins["sing_box"]["sha256"]["linux-amd64"]
    )


@pytest.mark.parametrize("field", ["ech", "resource_profile"])
def test_explicit_null_profile_cannot_silently_select_classical_tls(field):
    assert hysteria_errors(
        {"version": "v2.13.0", "masquerade_url": "https://vpn.example.com", field: None}
    )


@pytest.mark.parametrize("kind", ["fifo", "directory", "tampered"])
def test_generator_refuses_nonregular_or_unverified_executables(tmp_path, kind):
    from hysteria_ech import verified_binary

    path = tmp_path / "candidate"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"unverified-executable")
    with pytest.raises(ValueError, match="unverified-hysteria-runtime"):
        verified_binary(path)


@pytest.mark.parametrize("origin", [None, 42, {}, "http://inner.example"])
def test_ech_origin_type_refuses_without_loading_or_printing_authority(origin):
    document = hysteria(authority())
    document["masquerade_url"] = origin
    assert hysteria_errors(document)


@pytest.mark.parametrize("field", ["bandwidth_up", "bandwidth_down"])
@pytest.mark.parametrize("value,valid", [
    ("1 bps", True), ("1 gbps", True), ("1000000001 bps", False),
    ("0 bps", False), ("9" * 5000 + " bps", False), (True, False),
])
def test_bandwidth_bounds_refuse_without_integer_conversion_failure(field, value, valid):
    document = {"version": "v2.13.0", "masquerade_url": "https://vpn.example.com", field: value}
    assert bool(hysteria_errors(document)) is not valid


@pytest.mark.parametrize("expression,allowed", [
    ("<1.5.0-rc.5", True), ("<1.5.0 || >=1.14.0, <1.14.3", True),
    ("<=1.14.3", False), (">=1.14.0, <1.15.0", False),
    ("unknown", False), ("", False), ("<1.5.0 ||", False),
])
def test_release_advisories_apply_to_the_exact_candidate(expression, allowed):
    from datetime import datetime, timezone, timedelta
    from hysteria_release import publication_eligible
    now = datetime.now(timezone.utc)
    release = {"tag_name": "v1.14.3", "draft": False, "prerelease": False,
               "published_at": (now-timedelta(hours=49)).isoformat(),
               "assets": [{"name": "asset", "digest": "sha256:"+"a"*64}]}
    advisory = {"severity": "critical", "vulnerabilities": [{
        "package": {"ecosystem": "go", "name": "github.com/sagernet/sing-box"},
        "vulnerable_version_range": expression}]}
    assert publication_eligible(release, "v1.14.3", {"asset":"a"*64}, [advisory], now) is allowed
    advisory["vulnerabilities"][0]["package"]["name"] = "unreviewed-dependency"
    assert not publication_eligible(release, "v1.14.3", {"asset":"a"*64}, [advisory], now)


def test_release_advisory_without_a_named_package_retains_repository_version_scope():
    from datetime import datetime, timezone, timedelta
    from hysteria_release import publication_eligible
    now = datetime.now(timezone.utc)
    release = {"tag_name": "app/v2.13.0", "draft": False, "prerelease": False,
               "published_at": (now-timedelta(hours=49)).isoformat(),
               "assets": [{"name": "asset", "digest": "sha256:"+"a"*64}]}
    advisory = {"severity": "high", "vulnerabilities": [{
        "package": {"ecosystem": "", "name": ""}, "vulnerable_version_range": "<2.9.2"}]}
    assert publication_eligible(release, "app/v2.13.0", {"asset":"a"*64}, [advisory], now)
    advisory["vulnerabilities"][0]["vulnerable_version_range"] = ">=2.9.2"
    assert not publication_eligible(release, "app/v2.13.0", {"asset":"a"*64}, [advisory], now)


def test_release_pair_never_reports_partial_eligibility(monkeypatch, capsys):
    from datetime import datetime, timezone, timedelta
    import hysteria_release as release
    def fetch(url):
        if "/SagerNet/" in url and "/security-advisories" in url:
            raise OSError("unavailable")
        if "/security-advisories" in url:
            return []
        name = "hysteria" if "/HyNetworks/" in url else "sing_box"
        pin = release.PINS[name]
        prefix = "hysteria-" if name == "hysteria" else "sing-box-" + pin["version"] + "-"
        return {"tag_name": ("app/" if name == "hysteria" else "v") + pin["version"],
                "draft": False, "prerelease": False,
                "published_at": (datetime.now(timezone.utc)-timedelta(hours=72)).isoformat(),
                "assets": [{"name": prefix+arch+("" if name == "hysteria" else ".tar.gz"),
                            "digest": "sha256:"+digest} for arch,digest in pin["sha256"].items()]}
    monkeypatch.setattr(release, "fetch", fetch)
    assert release.main() == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "sing_box advisory metadata" in captured.err
