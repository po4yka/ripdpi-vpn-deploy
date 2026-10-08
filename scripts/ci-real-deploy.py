#!/usr/bin/env python3
"""Run one owned, authenticated disposable deployment and guarded teardown."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid

import yaml

from ci_deployment import CI_PROFILES
from ci_tailnet_api import Enrollment, EnrollmentError

ROOT = Path(__file__).resolve().parents[1]
PROFILES = tuple(name.removeprefix("ci-") for name in CI_PROFILES)
CONFIG_FIELDS = {"tailnet", "tag", "templates", "reality_target", "reality_server_name",
                 "probe_url", "recovery_age_recipient", "research"}


class DeploymentError(ValueError):
    """Public diagnostics are categorical; private subprocess output stays local."""


def private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data if isinstance(data, bytes) else data.encode())
    return Path(path)


def document(path, value):
    return private(path, json.dumps(value, sort_keys=True).encode())


def validate_config(value, distro, profile):
    if (not isinstance(value, dict) or set(value) != CONFIG_FIELDS
            or distro not in {"debian13", "ubuntu2404"} or profile not in PROFILES):
        raise DeploymentError("ci-configuration-invalid")
    if (not isinstance(value["templates"], dict) or distro not in value["templates"]
            or not re.fullmatch(r"[0-9a-f-]{36}", value["templates"][distro])
            or not isinstance(value["research"], dict)):
        raise DeploymentError("ci-template-configuration-invalid")
    for key in CONFIG_FIELDS - {"templates", "research"}:
        if (not isinstance(value[key], str) or not value[key]
                or any(ord(c) < 32 or c in '\\"' for c in value[key])):
            raise DeploymentError("ci-configuration-invalid")
    if (not re.fullmatch(r"[A-Za-z0-9.-]+:[1-9][0-9]{0,4}", value["reality_target"])
            or not re.fullmatch(r"[A-Za-z0-9.-]+", value["reality_server_name"])
            or not value["probe_url"].startswith("https://")
            or not re.fullmatch(r"age1[0-9a-z]{58}", value["recovery_age_recipient"])):
        raise DeploymentError("ci-endpoint-configuration-invalid")
    if profile == "p0p4":
        entry = value["research"].get("dns_morph_bridge", {})
        if (set(entry) != {"binary_url", "binary_sha256"}
                or not str(entry["binary_url"]).startswith("https://")
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry["binary_sha256"]))):
            raise DeploymentError("ci-bridge-artifact-required")
    if profile == "p0p5":
        entry = value["research"].get("hysteria_realm", {})
        if (set(entry) != {"linux_amd64_sha256", "linux_arm64_sha256"}
                or any(not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in entry.values())):
            raise DeploymentError("ci-realm-artifact-required")
    return value


def listeners(profile):
    selected = [{"name": "xray", "protocol": "tcp", "port": 443},
                {"name": "xray-fallback", "protocol": "tcp", "port": 2053}]
    if profile in {"p0p1", "p0p1p2"}:
        selected.extend([{ "name": "nginx-xhttp", "protocol": "tcp", "port": 8443},
                         {"name": "public-site-http", "protocol": "tcp", "port": 80}])
    if profile == "p0p1p2":
        selected.append({"name": "hysteria", "protocol": "udp", "port": 443})
    if profile == "p0p4":
        selected.append({"name": "dns-morph-bridge", "protocol": "udp", "port": 53})
    if profile == "p0p5":
        selected.append({"name": "hysteria-realm", "protocol": "tcp", "port": 8444})
    return selected


def promotion_intent(work, config, profile, environment, alias, address, digest):
    target = {"inventory_alias": alias, "public_service_address_sha256": hashlib.sha256(address.encode()).hexdigest(),
              "deployable_digest": digest}
    required = CI_PROFILES["ci-" + profile]
    runtime = {"sing_box": "1.13.16"}
    if "p1-xhttp" in required:
        runtime["xray"] = "26.3.27"
    liveness = {"schema_version": 2, "probe_url": config["probe_url"], "expected_status": 204,
                "expected_runtime": runtime,
                "policies": [{"id": "ci-profile", "required_profiles": required, "min_failed_vantages": 1}],
                "sentinels": [{"id": "ci-sentinel", "ssh_target": "ci-liveness", "policy": "ci-profile",
                               "vantage": "external", "target": target}]}
    return {"schema_version": 1, "kind": "disposable-staging-intent", "target_identity": target,
            "host": "upcloud:" + environment, "cohort": "ci-" + profile, "client": "ci-test",
            "liveness": liveness,
            "inputs": {"sops_file": str(work / "secrets.sops.yaml"), "age_key_file": str(work / "age.key"),
                       "cleanup_manifest": str(work / "cleanup.json")},
            "outputs": {name: str(work / ("sentinel-" + name + ".json"))
                        for name in ("liveness_config", "registry", "promotion_config", "authority")}}


class Runtime:
    def __init__(self, work):
        self.work = work
        self.counter = 0
        self.environment = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE") if k in os.environ}
        self.environment.update(MAKEFLAGS="-j1", PYTHONDONTWRITEBYTECODE="1", ANSIBLE_HOST_KEY_CHECKING="true")
        self.environment["UPCLOUD_TOKEN"] = os.environ["UPCLOUD_TOKEN"]

    def run(self, command, *, environment=None, data=None, timeout=1200):
        self.counter += 1
        log = self.work / f"command-{self.counter}.log"
        child = {**self.environment, **(environment or {})}
        process = None
        try:
            process = subprocess.Popen([str(x) for x in command], cwd=ROOT, env=child,
                                       stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            stdout, stderr = process.communicate(input=data, timeout=timeout)
            private(log, stdout + stderr)
            if process.returncode:
                raise DeploymentError("ci-command-failed")
            return stdout
        except (OSError, subprocess.TimeoutExpired):
            raise DeploymentError("ci-command-unavailable-or-timeout") from None
        finally:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    # The owned process group already exited before cancellation.
                    pass
                process.wait(timeout=10)

    def make(self, goal, **environment):
        return self.run(["make", goal], environment=environment)

    def script(self, name, *arguments, **kwargs):
        return self.run([sys.executable, ROOT / "scripts" / name, *arguments], **kwargs)

    def output(self, name):
        return self.run([ROOT / "scripts/terraform-env.sh", "output", "-raw", name]).decode().strip()


def validate_recovery_recipient(runtime, recipient):
    # age checks the recipient's Bech32 checksum before any external mutation.
    runtime.run(["age", "-r", recipient], data=b"CI recovery recipient validation\n", timeout=15)


def trusted_wait(runtime, pin, alias):
    from bootstrap_readiness import wait_for_bootstrap
    import fleet_inspection
    inventory = ROOT / "ansible/inventory/generated.ini"
    host = fleet_inspection.select_hosts(inventory, [alias])[0]
    wait_for_bootstrap(fleet_inspection.ssh_command(host, pin)[:-1], environment=runtime.environment, first_boot=True)


def issue_secrets(runtime, config, profile, environment, alias):
    work = runtime.work
    path = work / "secrets.yaml"
    runtime.run([ROOT / "scripts/ci-bootstrap-secrets.sh"], environment={
        "OUT": str(path), "SERVER_NAME": alias, "CLIENT_NAME": "ci-test",
        "REALITY_TARGET": config["reality_target"], "REALITY_SERVER_NAME": config["reality_server_name"],
        "WATCHDOG_CANARY_URL": config["probe_url"],
    })
    value = yaml.safe_load(path.read_bytes())
    if profile == "p0p4":
        import base64
        value["dns_morph_bridge_secrets"] = {**config["research"]["dns_morph_bridge"],
                                            "signing_key": base64.b64encode(os.urandom(32)).decode()}
    if profile == "p0p5":
        value["hysteria_realm_secrets"] = {**config["research"]["hysteria_realm"],
                                         "auth_token": os.urandom(32).hex()}
    path.write_text(yaml.safe_dump(value, sort_keys=False))
    runtime.script("validate-secrets.py", str(path))
    runtime.run(["age-keygen", "-o", work / "age.key"])
    recipient = runtime.run(["age-keygen", "-y", work / "age.key"]).decode().strip()
    encrypted = runtime.run(["sops", "--encrypt", "--age", recipient, "--input-type", "yaml", "--output-type", "yaml", path])
    private(work / "secrets.sops.yaml", encrypted)
    # Trust only this run's generated certificate on its disposable CI runner.
    cert = private(work / "ci-ca.crt", value["nginx_xhttp"]["cert_pem"])
    runtime.run(["sudo", "install", "-m", "0644", cert, "/usr/local/share/ca-certificates/vpn-ci.crt"])
    runtime.run(["sudo", "update-ca-certificates"])
    runtime.environment.update(SECRETS_FILE=str(path), VPN_SECRETS_FILE=str(path),
                               SOPS_AGE_KEY_FILE=str(work / "age.key"), SOPS_FILE=str(work / "secrets.sops.yaml"))


def bootstrap(runtime, config, enrollment, seed, identity, alias, address, sources, public_source):
    work = runtime.work
    key_fields = Path(seed["known_hosts_path"]).read_text().split()
    pin = private(work / "known_hosts", f"{address} {key_fields[1]} {key_fields[2]}\n")
    runtime.environment.update(INSPECT_KNOWN_HOSTS=str(pin), ANSIBLE_LIMIT=alias)
    runtime.make("inventory")
    trusted_wait(runtime, str(pin), alias)
    runtime.make("install-ssh-recovery", SSH_RECOVERY_EXCLUSIVE_WINDOW="1",
                 SSH_RECOVERY_INVENTORY=str(ROOT / "ansible/inventory/generated.ini"), SSH_RECOVERY_KNOWN_HOSTS=str(pin))
    common = {"schema_version": 2, "environment": runtime.environment["ENV"], "build_environment": runtime.environment["ENV"],
              "provider": "upcloud", "inventory_alias": alias, "public_address": address, "ssh_port": 22,
              "host_key_sha256": seed["host_public_key_sha256"], "public_sources": [public_source],
              "approved_sources": sources, "source_revision": identity[0], "deployable_digest": identity[1],
              "known_hosts": str(pin), "cleanup_manifest": str(work / "cleanup.json"), "policy_approval": None}
    for scenario in ("controller-loss", "reboot"):
        inputs = document(work / f"bootstrap-{scenario}.json", {**common, "output": str(work / f"handoff-{scenario}.json")})
        recovery = document(work / f"recovery-{scenario}.json", {"schema_version": 2, "bootstrap_config": str(inputs),
                            "evidence": str(work / f"recovery-{scenario}-evidence.json"),
                            "diagnostic": str(work / f"recovery-{scenario}-diagnostic.json")})
        runtime.make(f"staging-tailnet-{scenario}-test" if scenario == "controller-loss" else "staging-tailnet-reboot-recovery-test",
                     TAILNET_RECOVERY_CONFIG=str(recovery), TAILSCALE_AUTH_KEY=enrollment.key())
    handoff = work / "handoff.json"
    inputs = document(work / "bootstrap.json", {**common, "output": str(handoff)})
    runtime.make("bootstrap-tailnet", TAILNET_BOOTSTRAP_CONFIG=str(inputs), TAILSCALE_AUTH_KEY=enrollment.key())
    confirmed = json.loads(handoff.read_bytes())
    contexts = document(work / "contexts.json", {alias: confirmed["contexts"]})
    runtime.environment.update(TAILNET_HANDOFFS=str(handoff), DEPLOY_CI_TAILNET_HANDOFF=str(handoff),
                               DEPLOY_SSH_CONTEXTS_FILE=str(contexts))
    runtime.make("inventory")
    ownership = {"schema_version": 1, "inventory_alias": alias,
                 "inventory_path": str(ROOT / "ansible/inventory/generated.ini"), "known_hosts_path": str(pin),
                 "contexts_path": str(contexts), "source_revision": identity[0], "deployable_digest": identity[1]}
    for mode in ("check", "deploy"):
        path = document(work / f"ownership-{mode}.json", {**ownership, "mode": mode})
        runtime.make("migrate-ssh-ownership", SSH_OWNERSHIP_CONFIG=str(path))
    runtime.environment["ANSIBLE_SSH_ARGS"] = shlex.join([
        "-F", "/dev/null", "-o", "StrictHostKeyChecking=yes", "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "UserKnownHostsFile=" + str(pin), "-o", "HostKeyAlias=" + address,
        "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
    ])


def recovery_member(info):
    # Root-owned transient daemon credentials are unnecessary for provider recovery
    # and cannot be read by the CI user.
    if info.name in {"private/tailscale.state", "private/tailscale.sock"}:
        return None
    return info


@contextmanager
def cleanup_signal_window():
    # A second runner soft signal must not interrupt owned-resource teardown.
    # Hard termination remains unavoidably external to this process.
    saved = {number: signal.signal(number, signal.SIG_IGN)
             for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for number, handler in saved.items():
            signal.signal(number, handler)


def execute(config, args, work, artifact, *, runtime_factory=Runtime, enrollment_factory=Enrollment):
    runtime = runtime_factory(work)
    environment = "ci-staging-" + uuid.uuid4().hex[:16]
    alias = "vpn-" + environment + ".ci.test"
    runtime.environment.update(ENV=environment, PROVIDER="upcloud", COHORTS="ci-" + args.profile,
                               SKIP_PRECHECK="1", TAG_ON_SUCCESS="0")
    tfvars = ROOT / "terraform/providers/upcloud/environments" / (environment + ".tfvars")
    state = ROOT / "terraform/providers/upcloud/terraform.tfstate.d" / environment / "terraform.tfstate"
    enrollment = enrollment_factory(os.environ["CI_TAILSCALE_OAUTH_CLIENT_ID"], os.environ["CI_TAILSCALE_OAUTH_CLIENT_SECRET"],
                                    config["tailnet"], config["tag"])
    phases, cleanup_errors = [], []
    seed, apply_started, daemon_started, sentinel_started, deployed = None, False, False, False, False
    unit = "vpn-ci-tailnet-" + uuid.uuid4().hex
    failure = None
    try:
        if runtime.run(["git", "status", "--porcelain"]).strip():
            raise DeploymentError("clean-source-required")
        identity = runtime.run([ROOT / "scripts/deploy-source-identity.sh", "--identity"]).decode().split()
        validate_recovery_recipient(runtime, config["recovery_age_recipient"])
        runtime.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", work / "admin"])
        runtime.environment["ANSIBLE_SSH_PRIVATE_KEY_FILE"] = str(work / "admin")
        seed = json.loads(runtime.script("ci-ssh-seed.py", "create", "--directory", work / "seed", "--host-alias", alias,
                                         "--environment", environment, "--ssh-port", "22"))
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            public_source = str(ipaddress.IPv4Address(response.read(64).decode().strip()))
        if not ipaddress.ip_address(public_source).is_global:
            raise DeploymentError("controller-public-source-invalid")
        key_file = private(work / "controller-auth.key", enrollment.key())
        daemon_started = True
        runtime.run(["sudo", "systemd-run", "--unit", unit, "--property=RuntimeMaxSec=7200",
                     "tailscaled", "--state=" + str(work / "tailscale.state"), "--socket=" + str(work / "tailscale.sock")])
        deadline = time.monotonic() + 30
        while not (work / "tailscale.sock").exists():
            if time.monotonic() >= deadline:
                raise DeploymentError("controller-daemon-not-ready")
            time.sleep(0.2)
        tailscale = ["sudo", "tailscale", "--socket=" + str(work / "tailscale.sock")]
        runtime.run([*tailscale, "up", "--auth-key=file:" + str(key_file), "--hostname=" + environment,
                     "--accept-dns=false", "--accept-routes=false", "--ssh=false", "--timeout=120s"])
        key_file.unlink()
        status = json.loads(runtime.run([*tailscale, "status", "--json"]))
        sources = status["Self"]["TailscaleIPs"]
        from tailnet_management import validate_sources
        sources = validate_sources(sources)
        values = {"server_name": alias, "zone": args.zone, "plan": "1xCPU-2GB", "storage_template": config["templates"][args.distro],
                  "admin_ssh_public_key": (work / "admin.pub").read_text().strip(), "allowed_ssh_cidrs": [public_source + "/32"],
                  "build_env": environment, "enable_backups": False, "additional_public_ip": False,
                  "enable_provider_firewall": False, "public_listeners": listeners(args.profile),
                  "ci_ssh_seed": {"image_path": seed["image_path"], "image_sha256": seed["image_sha256"],
                                  "filesystem_uuid": seed["filesystem_uuid"], "host_public_key_sha256": seed["host_public_key_sha256"]}}
        private(tfvars, "\n".join(key + " = " + json.dumps(value) for key, value in values.items()) + "\n")
        issue_secrets(runtime, config, args.profile, environment, alias)
        runtime.script("ci-ssh-seed.py", "validate", "--manifest", seed["manifest_path"])
        runtime.make("init")
        runtime.make("plan")
        runtime.script("ci-ssh-seed.py", "validate", "--manifest", seed["manifest_path"])
        apply_started = True
        runtime.make("apply")
        state.chmod(0o600)
        runtime.environment.update(STAGING_CLEANUP_MANIFEST=str(work / "cleanup.json"), STAGING_CLEANUP_STATE=str(state),
                                   STAGING_CLEANUP_HOSTNAME=alias, STAGING_POST_DESTROY_EVIDENCE=str(work / "destroy-evidence.json"))
        runtime.make("staging-cleanup-manifest")
        address = str(ipaddress.IPv4Address(runtime.output("server_ipv4")))
        phases.append("provisioned-with-owned-ssh-key")
        bootstrap(runtime, config, enrollment, seed, identity, alias, address, sources, public_source)
        phases.append("recovery-bootstrap-ownership-passed")
        sentinel_root = work / "sentinel"
        sentinel_root.mkdir(mode=0o700)
        sentinel_started = True
        runtime.script("ci-liveness-sentinel.py", "prepare", "--root", sentinel_root)
        intent = promotion_intent(work, config, args.profile, environment, alias, address, identity[1])
        promotions = document(work / "promotions.json", {alias: intent})
        receipts = document(work / "failure-receipts.json", {alias: str(work / "ssh-failure.json")})
        runtime.environment.update(DEPLOY_PROMOTION_CONFIG_FILE=str(promotions), DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE=str(receipts))
        runtime.make("dry-run")
        if args.mode == "matrix":
            runtime.run([ROOT / "scripts/transport-reachability-matrix.sh", "--profile", args.profile,
                         "--secrets", work / "secrets.yaml", "--output-dir", artifact / "matrix"], timeout=1800)
        else:
            for goal in ("deploy", "verify", "smoke-test"):
                runtime.make(goal)
        deployed = True
        phases.append("canonical-deploy-real-protocol-proof-verify-smoke-passed")
    except (Exception, KeyboardInterrupt):
        failure = "deployment-incomplete"
    finally:
        with cleanup_signal_window():
            if apply_started:
                try:
                    if not (work / "cleanup.json").exists() and state.exists():
                        state.chmod(0o600)
                        runtime.environment.update(STAGING_CLEANUP_MANIFEST=str(work / "cleanup.json"),
                                                   STAGING_CLEANUP_STATE=str(state), STAGING_CLEANUP_HOSTNAME=alias,
                                                   STAGING_POST_DESTROY_EVIDENCE=str(work / "destroy-evidence.json"))
                        try:
                            runtime.make("staging-cleanup-manifest")
                        except DeploymentError:
                            # The exact detached-seed path below handles partial state;
                            # it still reports provisioning as unconfirmed.
                            pass
                    if (work / "cleanup.json").exists():
                        runtime.make("staging-destroy")
                    elif state.exists() and seed is not None:
                        state.chmod(0o600)
                        runtime.script("ci-ssh-seed.py", "cleanup-seed", "--manifest", seed["manifest_path"],
                                       "--state", state, "--environment", environment)
                        phases.append("detached-seed-cleanup-confirmed")
                        raise DeploymentError("provisioning-outcome-unconfirmed")
                    else:
                        raise DeploymentError("provisioning-outcome-unknown")
                    phases.append("provider-cleanup-confirmed")
                except (DeploymentError, OSError):
                    cleanup_errors.append("provider-cleanup-incomplete")
            if sentinel_started:
                try:
                    runtime.script("ci-liveness-sentinel.py", "stop", "--root", work / "sentinel")
                except DeploymentError:
                    cleanup_errors.append("sentinel-cleanup-incomplete")
            if daemon_started:
                try:
                    runtime.run(["sudo", "tailscale", "--socket=" + str(work / "tailscale.sock"), "logout"])
                except DeploymentError:
                    cleanup_errors.append("controller-logout-incomplete")
                try:
                    runtime.run(["sudo", "systemctl", "stop", unit])
                except DeploymentError:
                    cleanup_errors.append("controller-stop-incomplete")
            try:
                enrollment.revoke()
            except EnrollmentError:
                cleanup_errors.append("enrollment-cleanup-incomplete")
            if not cleanup_errors:
                try:
                    if seed is not None:
                        runtime.script("ci-ssh-seed.py", "cleanup-local", "--manifest", seed["manifest_path"])
                    tfvars.unlink(missing_ok=True)
                except (DeploymentError, OSError):
                    cleanup_errors.append("local-seed-cleanup-incomplete")
            result = {"schema_version": 1, "profile": args.profile, "distro": args.distro, "source_revision": identity[0] if 'identity' in locals() else None,
                      "status": "passed" if deployed and failure is None and not cleanup_errors else "failed",
                      "phases": phases, "cleanup_errors": cleanup_errors}
            document(artifact / "result.json", result)
            if (failure or cleanup_errors) and (apply_started or daemon_started or sentinel_started):
                # Retain private diagnostics/state only in operator-decryptable ciphertext.
                archive = work.parent / (work.name + ".tar.gz")
                with tarfile.open(archive, "w:gz") as bundle:
                    bundle.add(work, arcname="private", recursive=True, filter=recovery_member)
                    if state.exists():
                        bundle.add(state, arcname="terraform.tfstate")
                    if tfvars.exists():
                        bundle.add(tfvars, arcname="environment.tfvars")
                archive.chmod(0o600)
                runtime.run(["age", "-r", config["recovery_age_recipient"], "-o", artifact / "recovery.tar.gz.age", archive])
                archive.unlink()
            if result["status"] != "passed":
                raise DeploymentError("ci-deployment-or-cleanup-failed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--distro", choices=("debian13", "ubuntu2404"), required=True)
    parser.add_argument("--zone", default="fi-hel1")
    parser.add_argument("--mode", choices=("deploy", "matrix"), required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if (sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true"
                or not re.fullmatch(r"[a-z]{2}-[a-z]{3}[0-9]+", args.zone)):
            raise DeploymentError("isolated-linux-ci-runner-required")
        for name in ("UPCLOUD_TOKEN", "CI_TAILSCALE_OAUTH_CLIENT_ID", "CI_TAILSCALE_OAUTH_CLIENT_SECRET", "CI_DEPLOY_CONFIG"):
            if not os.environ.get(name):
                raise DeploymentError("missing-" + name)
        config = validate_config(json.loads(os.environ["CI_DEPLOY_CONFIG"]), args.distro, args.profile)
        work, artifact = args.work_dir.absolute(), args.artifact_dir.absolute()
        if work == artifact or work in artifact.parents or artifact in work.parents:
            raise DeploymentError("private-and-public-output-overlap")
        work.mkdir(mode=0o700, parents=False)
        artifact.mkdir(mode=0o700, parents=False)
        os.umask(0o077)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        result = execute(config, args, work, artifact)
        print(json.dumps(result))
        return 0
    except (DeploymentError, EnrollmentError, OSError, ValueError, KeyError):
        print("ci-real-deploy: failed; inspect categorical result or encrypted recovery artifact", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
