"""CI orchestration contracts; local boundaries do not claim a live provider run."""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import urllib.error

import pytest
import yaml
from template_render import render_template

from ci_tailnet_api import Enrollment, EnrollmentError, NoRedirect
from disposable_promotion import validate_intent

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ci_real_deploy", ROOT / "scripts/ci-real-deploy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def config():
    return {"tailnet": "example.test", "tag": "tag:ci", "templates": {
        "debian13": "00112233-4455-4677-8899-aabbccddeeff",
        "ubuntu2404": "00112233-4455-4677-8899-aabbccddee00",
    }, "reality_target": "example.test:443", "reality_server_name": "example.test",
        "probe_url": "https://example.test/204", "recovery_age_recipient": "age1" + "a" * 58,
        "research": {"dns_morph_bridge": {"binary_url": "https://example.test/bridge", "binary_sha256": "a" * 64},
                     "hysteria_realm": {"linux_amd64_sha256": "b" * 64, "linux_arm64_sha256": "c" * 64}}}


@pytest.mark.parametrize("profile", MODULE.PROFILES)
def test_each_ci_profile_has_an_actual_canonical_promotion_intent(tmp_path, profile):
    value = MODULE.promotion_intent(tmp_path, config(), profile, "ci-staging-test", "vpn-test",
                                    "192.0.2.10", "b" * 64)
    assert validate_intent(value) == value
    assert "applied_at" not in value["target_identity"]
    assert value["liveness"]["sentinels"][0]["ssh_target"] == "ci-liveness"


@pytest.mark.parametrize("profile", MODULE.PROFILES)
def test_ci_provider_contract_matches_actual_role_listener_template(profile):
    variables = yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text())
    variables.update(yaml.safe_load((ROOT / f"ansible/group_vars/vpn-ci-{profile}.yml").read_text()))
    actual = json.loads(render_template(ROOT / "ansible/templates/listener-manifest.json.j2", variables))
    spec = importlib.util.spec_from_file_location("contract", ROOT / "scripts/check-listener-contract.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    assert checker.check({"expected": MODULE.listeners(profile), "actual": actual}) == []


@pytest.mark.parametrize("distro", ["debian13", "ubuntu2404"])
def test_selected_template_is_mandatory_before_provisioning(distro):
    selected = config()
    assert MODULE.validate_config(selected, distro, "p0") == selected
    selected["templates"].pop(distro)
    with pytest.raises(MODULE.DeploymentError):
        MODULE.validate_config(selected, distro, "p0")


@pytest.mark.parametrize("profile,field", [("p0p4", "dns_morph_bridge"), ("p0p5", "hysteria_realm")])
def test_research_profiles_require_real_artifact_pins(profile, field):
    selected = config()
    selected["research"].pop(field)
    with pytest.raises(MODULE.DeploymentError):
        MODULE.validate_config(selected, "debian13", profile)


class API:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout):
        assert timeout == 30
        self.calls.append(request)
        if request.full_url.endswith("oauth/token"):
            return io.BytesIO(b'{"access_token":"synthetic-token"}')
        if request.method == "DELETE":
            return io.BytesIO(b'{}')
        return io.BytesIO(b'{"id":"key-one","key":"tskey-auth-synthetic"}')


def test_enrollment_is_single_use_ephemeral_preauthorized_and_revokes_only_owned_key():
    api = API()
    client = Enrollment("synthetic-client", "synthetic-secret", "example.test", "tag:ci", opener=api)
    assert client.key() == "tskey-auth-synthetic"
    request = api.calls[1]
    assert request.full_url == "https://api.tailscale.com/api/v2/tailnet/example.test/keys"
    assert json.loads(request.data)["capabilities"]["devices"]["create"] == {
        "reusable": False, "ephemeral": True, "preauthorized": True, "tags": ["tag:ci"]}
    client.revoke()
    assert api.calls[-1].method == "DELETE"
    assert api.calls[-1].full_url.endswith("/keys/key-one")
    assert client.owned_keys == []


def test_enrollment_redirect_refuses_without_forwarding_credentials():
    with pytest.raises(EnrollmentError):
        NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.test/steal")


def test_private_api_error_body_never_reaches_diagnostics():
    class Broken:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, "private-error-marker", {}, None)
    with pytest.raises(EnrollmentError) as error:
        Enrollment("test", "test", "example.test", "tag:ci", opener=Broken()).key()
    assert "private-error-marker" not in str(error.value)


def test_real_failed_child_output_is_private_and_not_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("UPCLOUD_TOKEN", "synthetic-provider-token")
    runtime = MODULE.Runtime(tmp_path)
    with pytest.raises(MODULE.DeploymentError) as error:
        runtime.run([sys.executable, "-c", "import sys; print('private-child-marker'); sys.exit(4)"])
    assert "private-child-marker" not in str(error.value)
    assert capsys.readouterr() == ("", "")
    log = tmp_path / "command-1.log"
    assert b"private-child-marker" in log.read_bytes()
    assert log.stat().st_mode & 0o777 == 0o600


def test_real_subprocess_timeout_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("UPCLOUD_TOKEN", "synthetic-provider-token")
    with pytest.raises(MODULE.DeploymentError, match="timeout"):
        MODULE.Runtime(tmp_path).run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)


@pytest.mark.parametrize("fail_goal", [None, "deploy", "staging-destroy", "daemon-start", "logout", "deploy-with-signal"])
def test_orchestration_requires_deploy_and_verified_cleanup(tmp_path, monkeypatch, fail_goal):
    """Provider commands are injected here; this is ordering, not live proof."""
    root, work, artifact = tmp_path / "repo", tmp_path / "private", tmp_path / "artifact"
    for path in (root, work, artifact):
        path.mkdir(mode=0o700)
    (root / "terraform/providers/upcloud/environments").mkdir(parents=True)
    monkeypatch.setattr(MODULE, "ROOT", root)
    for name in ("CI_TAILSCALE_OAUTH_CLIENT_ID", "CI_TAILSCALE_OAUTH_CLIENT_SECRET"):
        monkeypatch.setenv(name, "synthetic-value")
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"8.8.8.8"))
    monkeypatch.setattr(MODULE, "issue_secrets", lambda *a: None)
    monkeypatch.setattr(MODULE, "bootstrap", lambda *a: None)
    calls = []

    class BoundaryRuntime:
        def __init__(self, private_root):
            self.work = private_root
            self.environment = {}

        def run(self, command, **kwargs):
            command = [str(item) for item in command]
            calls.append(command)
            if command[:2] == ["git", "status"]:
                return b""
            if command[0].endswith("deploy-source-identity.sh"):
                return ("a" * 40 + " " + "b" * 64).encode()
            if command[0] == "ssh-keygen":
                MODULE.private(work / "admin.pub", "ssh-ed25519 synthetic-public-key")
            if "systemd-run" in command:
                (work / "tailscale.sock").touch()
                if fail_goal == "daemon-start":
                    raise MODULE.DeploymentError("injected-post-activation-failure")
            if "logout" in command and fail_goal == "logout":
                raise MODULE.DeploymentError("injected-logout-failure")
            if "status" in command:
                return b'{"Self":{"TailscaleIPs":["100.64.0.1"]}}'
            if command[0] == "age" and "-o" in command:
                MODULE.private(Path(command[command.index("-o") + 1]), "encrypted-boundary")
            return b""

        def script(self, name, *arguments, **kwargs):
            calls.append([name, *map(str, arguments)])
            if name == "ci-ssh-seed.py" and arguments[0] == "create":
                return json.dumps({"image_path": str(work / "seed.img"), "manifest_path": str(work / "seed.json"),
                                   "known_hosts_path": str(work / "pins"), "filesystem_uuid": "00000000-0000-4000-8000-000000000001",
                                   "image_sha256": "c" * 64, "host_public_key_sha256": "d" * 64}).encode()
            return b""

        def make(self, goal, **environment):
            calls.append(["make", goal])
            if goal == "apply":
                state = root / "terraform/providers/upcloud/terraform.tfstate.d" / self.environment["ENV"] / "terraform.tfstate"
                state.parent.mkdir(parents=True)
                MODULE.private(state, "{}")
            if goal == "staging-cleanup-manifest":
                MODULE.document(work / "cleanup.json", {"owned": True})
            if goal == "staging-destroy" and fail_goal == "deploy-with-signal":
                os.kill(os.getpid(), signal.SIGTERM)
            if goal == fail_goal or (goal == "deploy" and fail_goal == "deploy-with-signal"):
                raise MODULE.DeploymentError("injected-boundary-failure")
            return b""

        def output(self, _name):
            return "192.0.2.10"

    class Keys:
        def __init__(self, *_args):
            pass
        def key(self):
            return "synthetic-enrollment"
        def revoke(self):
            calls.append(["revoke"])

    args = argparse.Namespace(profile="p0", distro="debian13", zone="fi-hel1", mode="deploy")
    if fail_goal:
        with pytest.raises(MODULE.DeploymentError):
            MODULE.execute(config(), args, work, artifact, runtime_factory=BoundaryRuntime, enrollment_factory=Keys)
    else:
        assert MODULE.execute(config(), args, work, artifact, runtime_factory=BoundaryRuntime, enrollment_factory=Keys)["status"] == "passed"
    result = json.loads((artifact / "result.json").read_bytes())
    assert (result["status"] == "passed") is (fail_goal is None)
    assert (["make", "staging-destroy"] in calls) is (fail_goal != "daemon-start")
    assert any(call[:3] == ["sudo", "systemctl", "stop"] for call in calls)
    assert ["revoke"] in calls
    if fail_goal != "daemon-start":
        assert calls.index(["make", "plan"]) < calls.index(["make", "apply"]) < calls.index(["make", "deploy"])
    variables = list((root / "terraform/providers/upcloud/environments").glob("*.tfvars"))
    assert bool(variables) is (fail_goal in {"staging-destroy", "logout"})
    assert (artifact / "recovery.tar.gz.age").exists() is bool(fail_goal)


def test_invalid_recipient_checksum_is_refused_by_real_age_before_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("UPCLOUD_TOKEN", "synthetic-provider-token")
    runtime = MODULE.Runtime(tmp_path)
    with pytest.raises(MODULE.DeploymentError):
        MODULE.validate_recovery_recipient(runtime, "age1" + "a" * 58)
    assert runtime.counter == 1
    assert len(list(tmp_path.iterdir())) == 1


def test_actual_age_recipient_accepts_recoverable_ciphertext(tmp_path, monkeypatch):
    monkeypatch.setenv("UPCLOUD_TOKEN", "synthetic-provider-token")
    runtime = MODULE.Runtime(tmp_path)
    runtime.run(["age-keygen", "-o", tmp_path / "key"])
    recipient = runtime.run(["age-keygen", "-y", tmp_path / "key"]).decode().strip()
    MODULE.validate_recovery_recipient(runtime, recipient)
    ciphertext = (tmp_path / "command-3.log").read_bytes()
    plain = runtime.run(["age", "--decrypt", "-i", tmp_path / "key"], data=ciphertext)
    assert plain == b"CI recovery recipient validation\n"


@pytest.mark.native_runtime
def test_ci_generator_real_crypto_passes_secret_schema(tmp_path):
    """Exercise the installed pinned Xray, release downloads and real key tools."""
    output = tmp_path / "generated.yaml"
    environment = {**os.environ, "OUT": str(output), "SERVER_NAME": "vpn-ci.example.test",
                   "CLIENT_NAME": "ci-test", "REALITY_TARGET": "example.test:443",
                   "REALITY_SERVER_NAME": "example.test", "WATCHDOG_CANARY_URL": "https://example.test/204",
                   "PROVIDER": "upcloud", "ENV": "ci-staging-generator", "COHORTS": "ci-p0p1p2"}
    generated = subprocess.run([str(ROOT / "scripts/ci-bootstrap-secrets.sh")], cwd=ROOT,
                               env=environment, capture_output=True, timeout=300)
    # Do not put private subprocess diagnostics or generated values in assertions.
    assert generated.returncode == 0, "real CI credential generation failed"
    assert output.stat().st_mode & 0o777 == 0o600
    checked = subprocess.run([sys.executable, str(ROOT / "scripts/validate-secrets.py"), str(output)],
                             cwd=ROOT, env=environment, capture_output=True, timeout=30)
    assert checked.returncode == 0, "generated CI credentials violate schema"
    value = yaml.safe_load(output.read_bytes())
    assert value["hysteria"]["masquerade_url"] == environment["WATCHDOG_CANARY_URL"]
    registry = value["client_registry"]["ci-test"]
    assert registry["hosts"] == ["upcloud:ci-staging-generator"]
    assert registry["cohorts"] == ["ci-p0p1p2"]
    public = subprocess.run(["wg", "pubkey"], input=registry["awg_private_key"].encode(), capture_output=True, timeout=10)
    assert public.returncode == 0
    assert public.stdout.decode().strip() == value["amneziawg_secrets"]["peers"][0]["public_key"]
