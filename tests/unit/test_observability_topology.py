"""Versioned observability topology and inventory publication contract."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "observability-contract.py"
RENDER = ROOT / "scripts" / "render-inventory.sh"


def _trusted_directory() -> Path:
    root = Path(tempfile.mkdtemp(prefix="ripdpi-observability-topology-", dir=Path.home()))
    root.chmod(0o700)
    return root


def _root_owned_sticky_tmp() -> Path:
    for candidate in (Path("/private/tmp"), Path("/tmp")):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if (
            stat.S_ISDIR(metadata.st_mode)
            and metadata.st_uid == 0
            and metadata.st_mode & stat.S_ISVTX
            and metadata.st_mode & stat.S_IWOTH
        ):
            return candidate
    raise AssertionError("a root-owned world-writable sticky temp directory is required")


@pytest.fixture
def trusted_root():
    root = _trusted_directory()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _topology() -> dict:
    return {
        "schema_version": 2,
        "credential_mode": "systemd",
        "source_revision": "a" * 40,
        "observer": {"kind": "uptime-kuma", "host_alias": "observer-a", "failure_domain": "observer-a"},
        "nodes": [
            {
                "node_id": name,
                "provider": provider,
                "environment": "prod",
                "capabilities": capabilities,
                "failure_domain": name,
                "public_listeners": [{"name": "xray", "protocol": "tcp", "port": 443}],
            }
            for name, provider, capabilities in (
                ("edge-prod", "upcloud", ["vpn"]),
                ("control-prod", "hetzner", ["vpn", "collector"]),
                ("third-prod", "vultr", ["vpn"]),
            )
        ],
    }


def _validate(document: dict, root: Path) -> subprocess.CompletedProcess[str]:
    path = root / "topology.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "topology", "--document", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_topology_is_canonical_and_deterministic(trusted_root: Path) -> None:
    document = _topology()
    document["nodes"].reverse()

    result = _validate(document, trusted_root)

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert [node["node_id"] for node in rendered["nodes"]] == [
        "control-prod",
        "edge-prod",
        "third-prod",
    ]
    assert rendered["observer"] == document["observer"]
    assert result.stdout == json.dumps(rendered, sort_keys=True, separators=(",", ":")) + "\n"
    forbidden = ("198.51.100.", "example.com", "PRIVATE", "TOKEN")
    assert not any(value in result.stdout for value in forbidden)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("duplicate-node", "duplicate identity"),
        ("observer-on-node", "observer placement"),
        ("observer-on-domain", "observer placement"),
        ("public-admin", "public listener"),
        ("public-ingest", "public listener"),
        ("no-collector", "control-plane count"),
        ("two-collectors", "control-plane count"),
        ("obsolete", "obsolete dedicated topology"),
    ],
)
def test_topology_rejects_identity_placement_and_public_surface(
    trusted_root: Path, mutation: str, expected: str
) -> None:
    document = _topology()
    if mutation == "duplicate-node":
        document["nodes"][1]["node_id"] = document["nodes"][0]["node_id"]
    elif mutation == "observer-on-node":
        document["observer"]["host_alias"] = "edge-prod"
    elif mutation == "observer-on-domain":
        document["observer"]["failure_domain"] = "edge-prod"
    elif mutation in {"public-admin", "public-ingest"}:
        document["nodes"][1]["public_listeners"] = [
            {"name": "prometheus" if mutation == "public-admin" else "observability-ingest",
             "protocol": "tcp", "port": 9443}
        ]
    elif mutation == "no-collector":
        document["nodes"][1]["capabilities"] = ["vpn"]
    elif mutation == "two-collectors":
        document["nodes"][0]["capabilities"] = ["vpn", "collector"]
    elif mutation == "obsolete":
        document["schema_version"] = 1
    result = _validate(document, trusted_root)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == f"observability-contract: {expected} rejected\n"


@pytest.mark.parametrize("fault", ["no-vpn", "unknown-capability", "unknown-observer", "eleven-nodes"])
def test_topology_rejects_schema_faults(trusted_root: Path, fault: str) -> None:
    document = _topology()
    if fault == "no-vpn":
        document["nodes"][1]["capabilities"] = ["collector"]
    elif fault == "unknown-capability":
        document["nodes"][0]["capabilities"].append("deadman")
    elif fault == "unknown-observer":
        document["observer"]["kind"] = "healthchecks"
    else:
        document["nodes"] *= 4
    result = _validate(document, trusted_root)
    assert result.returncode == 2
    assert result.stdout == ""


def test_topology_accepts_root_owned_sticky_ancestor_with_trusted_child() -> None:
    root = Path(
        tempfile.mkdtemp(
            prefix="ripdpi-observability-sticky-", dir=_root_owned_sticky_tmp()
        )
    )
    root.chmod(0o700)
    try:
        result = _validate(_topology(), root)
    finally:
        shutil.rmtree(root)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("fault", ["writable-ancestor", "symlink-child"])
def test_topology_rejects_unsafe_child_below_sticky_ancestor(fault: str) -> None:
    sticky_tmp = _root_owned_sticky_tmp()
    root = Path(tempfile.mkdtemp(prefix="ripdpi-observability-unsafe-", dir=sticky_tmp))
    root.chmod(0o700)
    cleanup = [root]
    if fault == "writable-ancestor":
        unsafe = root / "unsafe"
        unsafe.mkdir(mode=0o700)
        unsafe.chmod(0o777)
        target = unsafe / "trusted"
        target.mkdir(mode=0o700)
    else:
        target = Path(tempfile.mkdtemp(prefix="ripdpi-observability-target-", dir=sticky_tmp))
        target.chmod(0o700)
        cleanup.append(target)
        (root / "child").symlink_to(target, target_is_directory=True)
        target = root / "child"
    try:
        result = _validate(_topology(), target)
    finally:
        for path in cleanup:
            shutil.rmtree(path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "observability-contract: topology rejected\n"


def _make_stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _inventory_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "contract").mkdir()
    (root / "secrets").mkdir()
    (root / "ansible" / "inventory").mkdir(parents=True)
    (root / "ansible" / "group_vars").mkdir()
    for name in (
        "render-inventory.sh",
        "terraform-env.sh",
        "observability-contract.py",
        "validate-secrets.py",
    ):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
        (root / "scripts" / name).chmod(0o700)
    shutil.copyfile(
        ROOT / "contract" / "observability-topology.schema.json",
        root / "contract" / "observability-topology.schema.json",
    )
    shutil.copyfile(ROOT / "secrets" / "schema.json", root / "secrets" / "schema.json")
    secrets = yaml.safe_load((ROOT / "tests" / "fixtures" / "secrets-sample.yml").read_text())
    secrets["hysteria"].setdefault("masquerade_url", "https://vpn.example.com")
    sender = secrets["observability_secrets"]["senders"][0]
    secrets["observability_secrets"]["senders"] = [
        {**sender, "node_id": f"{provider}-test",
         "certificate_pem": sender["certificate_pem"] + provider,
         "private_key_pem": sender["private_key_pem"] + provider}
        for provider in ("upcloud", "hetzner", "vultr")
    ]
    secrets["observability_kuma_secrets"]["push_monitors"] = [
        {"check_id": f"node-{provider}", "node_id": f"{provider}-test", "kind": "node",
         "token": f"fixture-kuma-node-{provider}-not-real-0000"}
        for provider in ("upcloud", "hetzner", "vultr")
    ] + [
        {"check_id": kind, "node_id": "hetzner-test", "kind": kind,
         "token": f"fixture-kuma-{kind}-not-real-00000000"}
        for kind in ("pipeline", "delivery")
    ]
    secrets_path = root / "secrets" / "runtime.yml"
    secrets_path.write_text(yaml.safe_dump(secrets))
    secrets_path.chmod(0o600)
    for provider in ("upcloud", "hetzner", "vultr"):
        target = root / "terraform" / "providers" / provider / "environments"
        target.mkdir(parents=True)
        (target / "test.tfvars").write_text("")
    (root / "ansible" / "inventory" / "generated.ini").write_text("last-good\n")
    (root / "ansible" / "group_vars" / "vpn-p0-minimal.yml").write_text("---\n")
    (root / "ansible" / "group_vars" / "all.yml").write_text(
        "---\nobservability_contract:\n  enabled_environments: [test]\n  schema_version: 1\n  credential_mode: systemd\n"
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    terraform = r'''
provider=unknown
for arg in "$@"; do
  case "$arg" in
    *terraform/providers/upcloud*) provider=upcloud ;;
    *terraform/providers/hetzner*) provider=hetzner ;;
    *terraform/providers/vultr*) provider=vultr ;;
  esac
done
while [ "${1:-}" != "" ]; do
  case "$1" in -chdir=*) shift;; *) break;; esac
done
if [ "${1:-}" = console ]; then printf '"[\\"203.0.113.0/24\\"]"\n'; exit 0; fi
if [ "${1:-}" != output ]; then exit 0; fi
shift
mode="$1"; key="${2:-}"
case "$key" in
  server_ipv4) printf '198.51.100.10' ;;
  server_ipv6) printf '2001:db8::1' ;;
  admin_user) printf deploy ;;
  ssh_port) printf 22 ;;
  server_hostname) printf '%s-test' "$provider" ;;
  honeypot_ipv4) printf '' ;;
  public_listeners)
    case "$provider" in
      upcloud)
        if [ "${LISTENER_FAULT:-}" = vpn-unknown ]; then
          printf '[{"name":"metrics","protocol":"tcp","port":9443,"port_range":null}]'
        else
          printf '[{"name":"xray","protocol":"tcp","port":443,"port_range":null}]'
        fi ;;
      hetzner)
        if [ "${LISTENER_FAULT:-}" = public-admin ]; then
          printf '[{"name":"prometheus","protocol":"tcp","port":9090,"port_range":null}]'
        else
          printf '[{"name":"xray","protocol":"tcp","port":443,"port_range":null}]'
        fi ;;
      vultr) printf '[{"name":"xray","protocol":"tcp","port":443,"port_range":null}]' ;;
    esac ;;
esac
'''
    _make_stub(bindir / "terraform", terraform)
    _make_stub(bindir / "ssh", "exit 99")
    _make_stub(
        bindir / "git",
        r'''
case " $* " in
  *" status "*)
    if [ "${GIT_FAULT:-}" = dirty ]; then printf ' M scripts/render-inventory.sh\n'; fi
    if find "${GIT_REPO_ROOT}/ansible/inventory" -maxdepth 1 \
      -name '.observability-topology.*' -print -quit | grep -q .; then
      printf '?? ansible/inventory/.observability-topology.candidate\n'
    fi
    ;;
  *" rev-parse HEAD "*)
    count=0
    if [ -f "${GIT_STATE}" ]; then count="$(cat "${GIT_STATE}")"; fi
    count=$((count + 1))
    printf '%s' "$count" > "${GIT_STATE}"
    if [ "${GIT_FAULT:-}" = stale ] && [ "$count" -gt 1 ]; then
      printf '2222222222222222222222222222222222222222\n'
    else
      printf '1111111111111111111111111111111111111111\n'
    fi
    ;;
  *) exit 2 ;;
esac
''',
    )
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "ANSIBLE_SSH_PRIVATE_KEY_FILE": "/private/test-key",
        "HOSTS": "upcloud:test,hetzner:test,vultr:test",
        "COHORTS": "p0-minimal,-,-",
        "AWG_EVIDENCE_MODES": "",
        "VPN_SECRETS_FILE": str(secrets_path),
        "GIT_STATE": str(tmp_path / "git-state"),
        "GIT_REPO_ROOT": str(root),
        "OBSERVABILITY_CAPABILITIES": "vpn,vpn+collector,vpn",
        "OBSERVABILITY_FAILURE_DOMAINS": "edge-a,control-a,deadman-a",
        "OBSERVABILITY_OBSERVER_ALIAS": "observer-a",
        "OBSERVABILITY_OBSERVER_DOMAIN": "observer-a",
    }
    return root, env


def test_render_inventory_publishes_validated_deterministic_topology(tmp_path: Path) -> None:
    root, env = _inventory_repo(tmp_path)

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    inventory = (root / "ansible" / "inventory" / "generated.ini").read_text()
    assert "[vpn-observability-control]" in inventory
    assert "hetzner-test" in inventory
    assert "[vpn-observability-deadman]" not in inventory
    assert "vultr-test" in inventory
    assert "observability_capabilities=" in inventory
    assert "observability_host_class=" not in inventory
    encoded = next(
        line.split("=", 1)[1]
        for line in inventory.splitlines()
        if line.startswith("observability_topology_b64=")
    )
    topology = json.loads(base64.b64decode(encoded))
    assert [node["node_id"] for node in topology["nodes"]] == [
        "hetzner-test",
        "upcloud-test",
        "vultr-test",
    ]
    assert topology["observer"]["kind"] == "uptime-kuma"
    assert topology["source_revision"] == "1" * 40
    assert "198.51.100.10" not in json.dumps(topology)
    parsed = subprocess.run(
        [
            "ansible-inventory",
            "-i",
            str(root / "ansible" / "inventory" / "generated.ini"),
            "--list",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    hostvars = json.loads(parsed.stdout)["_meta"]["hostvars"]
    for host in ("upcloud-test", "hetzner-test", "vultr-test"):
        assert hostvars[host]["ansible_ssh_private_key_file"] == "/private/test-key"
        assert hostvars[host]["ansible_python_interpreter"] == "/usr/bin/python3"
    assert "vpn_service_address" in hostvars["upcloud-test"]
    assert "vpn_service_address" in hostvars["hetzner-test"]
    assert "vpn_service_address" in hostvars["vultr-test"]


def test_render_inventory_from_root_owned_sticky_tmp_is_supported() -> None:
    parent = Path(
        tempfile.mkdtemp(
            prefix="ripdpi-observability-render-", dir=_root_owned_sticky_tmp()
        )
    )
    parent.chmod(0o700)
    try:
        root, env = _inventory_repo(parent)
        result = subprocess.run(
            ["bash", str(root / "scripts" / "render-inventory.sh")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        inventory = (root / "ansible" / "inventory" / "generated.ini").read_text()
    finally:
        shutil.rmtree(parent)

    assert result.returncode == 0, result.stderr
    assert "[vpn-observability-control]" in inventory
    assert "observability_topology_b64=" in inventory


@pytest.mark.parametrize("selection", ["upcloud:test,hetzner:prod,vultr:test", "upcloud:../prod"])
def test_inventory_scope_refuses_before_terraform(tmp_path: Path, selection: str) -> None:
    root, env = _inventory_repo(tmp_path)
    env["HOSTS"] = selection
    marker = tmp_path / "provider-called"
    _make_stub(tmp_path / "bin" / "terraform", f'touch "{marker}"; exit 99')
    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert not marker.exists()
    assert (root / "ansible/inventory/generated.ini").read_text() == "last-good\n"


def test_render_inventory_refuses_env_topology_when_tracked_selector_is_disabled(
    tmp_path: Path,
) -> None:
    root, env = _inventory_repo(tmp_path)
    (root / "ansible" / "group_vars" / "all.yml").write_text(
        "---\nobservability_contract:\n  enabled_environments: []\n  schema_version: 1\n  credential_mode: systemd\n"
    )

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "tracked observability selector is disabled" in result.stderr
    assert (root / "ansible" / "inventory" / "generated.ini").read_text() == "last-good\n"


@pytest.mark.parametrize("missing", ["all", "capabilities", "failure-domains", "observer"])
def test_enabled_observability_requires_complete_topology_inputs_without_replacing_last_good(
    tmp_path: Path, missing: str
) -> None:
    root, env = _inventory_repo(tmp_path)
    keys = {
        "capabilities": "OBSERVABILITY_CAPABILITIES",
        "failure-domains": "OBSERVABILITY_FAILURE_DOMAINS",
        "observer": "OBSERVABILITY_OBSERVER_ALIAS",
    }
    if missing == "all":
        for key in keys.values():
            env.pop(key)
    else:
        env.pop(keys[missing])

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "enabled observability requires capabilities, failure domains, and observer identity" in result.stderr
    assert (root / "ansible" / "inventory" / "generated.ini").read_text() == "last-good\n"


@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_render_inventory_requires_exact_sender_set_without_replacing_last_good(
    tmp_path: Path, fault: str
) -> None:
    root, env = _inventory_repo(tmp_path)
    secrets_path = Path(env["VPN_SECRETS_FILE"])
    secrets = yaml.safe_load(secrets_path.read_text())
    senders = secrets["observability_secrets"]["senders"]
    if fault == "missing":
        senders[0]["node_id"] = "control-test"
    else:
        extra = dict(senders[0])
        extra["node_id"] = "untracked-vpn"
        extra["certificate_pem"] += "-extra"
        extra["private_key_pem"] += "-extra"
        senders.append(extra)
    secrets_path.write_text(yaml.safe_dump(secrets))

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "observability sender node IDs must exactly match topology VPN node IDs" in result.stderr
    assert (root / "ansible" / "inventory" / "generated.ini").read_text() == "last-good\n"


@pytest.mark.parametrize("fault", ["missing-node", "extra-node", "wrong-collector"])
def test_inventory_requires_exact_independent_monitor_bindings(tmp_path, fault):
    root, env = _inventory_repo(tmp_path)
    path = Path(env["VPN_SECRETS_FILE"])
    secrets = yaml.safe_load(path.read_text())
    monitors = secrets["observability_kuma_secrets"]["push_monitors"]
    if fault == "missing-node":
        monitors.pop(0)
    elif fault == "extra-node":
        monitors[0]["node_id"] = "foreign-node"
    else:
        monitors[-1]["node_id"] = "upcloud-test"
    path.write_text(yaml.safe_dump(secrets))
    result = subprocess.run(["bash", str(root / "scripts/render-inventory.sh")], cwd=root,
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "monitor bindings must exactly match" in result.stderr
    assert (root / "ansible/inventory/generated.ini").read_text() == "last-good\n"


@pytest.mark.parametrize("fault", ["dirty", "stale"])
def test_render_inventory_refuses_untrustworthy_source_identity_without_replacing_last_good(
    tmp_path: Path, fault: str
) -> None:
    root, env = _inventory_repo(tmp_path)
    env["GIT_FAULT"] = fault

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "observability topology source is not clean and stable" in result.stderr
    assert (root / "ansible" / "inventory" / "generated.ini").read_text() == "last-good\n"


@pytest.mark.parametrize("fault", ["public-admin", "vpn-unknown", "observer-placement"])
def test_render_inventory_rejects_invalid_topology_without_replacing_last_good(
    tmp_path: Path, fault: str
) -> None:
    root, env = _inventory_repo(tmp_path)
    if fault in {"public-admin", "vpn-unknown"}:
        env["LISTENER_FAULT"] = fault
    else:
        env["OBSERVABILITY_OBSERVER_DOMAIN"] = "edge-a"

    result = subprocess.run(
        ["bash", str(root / "scripts" / "render-inventory.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert (root / "ansible" / "inventory" / "generated.ini").read_text() == "last-good\n"


def test_repository_runtime_mode_is_systemd_credentials_only() -> None:
    variables = yaml.safe_load((ROOT / "ansible" / "group_vars" / "all.yml").read_text())

    assert variables["observability_contract"] == {
        "enabled_environments": ["staging"],
        "schema_version": 1,
        "credential_mode": "systemd",
    }
