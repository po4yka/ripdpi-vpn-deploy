"""Execute runtime audit boundaries locally without credentials or remote hosts."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from transport_fixtures import guarded_xray_bytes

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
VALIDATOR = ANSIBLE / "roles/xray/files/xray_validate.py"


def tasks(path: str) -> list[dict]:
    source = ANSIBLE / path
    result = yaml.safe_load(source.read_text())
    if (
        source.name == "main.yml"
        and len(result) == 1
        and "ansible.builtin.include_tasks" in result[0]
        and (source.parent / "enable.yml").exists()
    ):
        result = yaml.safe_load((source.parent / "enable.yml").read_text())
    return result


def named(items: list[dict], name: str) -> dict:
    def flatten(rows):
        for row in rows:
            yield row
            for key in ("block", "rescue", "always"):
                yield from flatten(row.get(key, []))

    return copy.deepcopy(
        next(task for task in flatten(items) if task.get("name") == name)
    )


def run_play(tmp_path: Path, selected: list[dict], variables: dict, *, env=None):
    play = tmp_path / "play.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "vars": {"ansible_python_interpreter": sys.executable, **variables},
                    "tasks": selected,
                }
            ]
        )
    )
    return subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", "-vv", str(play)],
        env={**os.environ, "ANSIBLE_NOCOLOR": "1", **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


def executable(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(0o755)
    return path


def relocate(value, replacements: dict[str, str]):
    if isinstance(value, list):
        return [relocate(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: relocate(item, replacements)
            for key, item in value.items()
            if key not in {"owner", "group"}
        }
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def test_awg_normalization_never_prints_private_material_under_verbose_callback(
    tmp_path,
):
    from test_awg_device_binding import document
    instance = document()["amneziawg_secrets"]["instances"][0]
    private = instance["server_private_key"]
    preshared_material = instance["peers"][0]["preshared_key"]
    result = run_play(tmp_path, tasks("roles/amneziawg/tasks/instances.yml"), {
        "vpn": {"awg_cohort": ""}, "amneziawg_listen_port": 51820,
        "amneziawg": {"listen_port": 51820}, "amneziawg_cohort": {},
        "amneziawg_secrets": {"instances": [instance]},
        "role_path": str(ROOT / "ansible/roles/amneziawg"),
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert private not in result.stdout + result.stderr
    assert preshared_material not in result.stdout + result.stderr
    for path in (
        "roles/amneziawg/tasks/enable.yml",
        "roles/amneziawg/handlers/main.yml",
    ):
        for task in tasks(path):
            if "_awg_instances" in str(task.get("loop", "")):
                assert task.get("no_log") is True
    rotation = tasks("playbooks/rotate-credentials.yml")[0]
    assert not any(task["name"] == "Restart amneziawg" for task in rotation.get("handlers", []))
    activation = named(rotation["tasks"], "Activate rotated AmneziaWG peers and firewall claims together")
    assert activation["ansible.builtin.import_tasks"] == "tasks/awg-rotate.yml"
    lifecycle = tasks("playbooks/tasks/awg-rotate.yml")[0]
    assert lifecycle["block"][1]["ansible.builtin.include_role"] == {"name": "amneziawg"}
    def flatten(rows):
        for row in rows:
            yield row
            for section in ("block", "rescue", "always"):
                yield from flatten(row.get(section, []))
    sensitive = [task for task in flatten(tasks("roles/amneziawg/tasks/configure.yml"))
                 if "loop" in task or "ansible.builtin.template" in task]
    assert sensitive
    assert all(task.get("no_log") is True for task in sensitive)


@pytest.mark.parametrize(
    "enabled,custom,upstream,success",
    [
        (False, False, True, True),
        (True, False, True, True),
        (True, True, True, False),
        (True, False, False, False),
    ],
)
def test_dns_stub_transition_preserves_or_migrates_resolver_before_restart(
    tmp_path,
    enabled,
    custom,
    upstream,
    success,
):
    etc = tmp_path / "etc"
    run = tmp_path / "run"
    etc.mkdir()
    run.mkdir()
    dropin = etc / "systemd/resolved.conf.d"
    dropin.mkdir(parents=True)
    managed = dropin / "no-stub.conf"
    managed.write_text("[Resolve]\nDNSStubListener=no\n")
    stub = run / "stub-resolv.conf"
    stub.write_text("nameserver 127.0.0.53\n")
    upstream_file = run / "resolv.conf"
    upstream_file.write_text(
        "nameserver 192.0.2.53\n" if upstream else "# no upstream\n"
    )
    resolver = etc / "resolv.conf"
    if custom:
        resolver.write_text("nameserver 127.0.0.53\n")
    else:
        resolver.symlink_to(stub)
    resolvectl = tmp_path / "resolvectl"
    resolvectl.write_text("#!/bin/sh\nexit 0\n")
    resolvectl.chmod(0o755)
    selected = relocate(
        tasks("roles/baseline/tasks/resolver.yml"),
        {
            "/etc/": str(etc) + "/",
            "/run/systemd/resolve/": str(run) + "/",
            "resolvectl": str(resolvectl),
        },
    )
    marker = tmp_path / "restart"
    for restart in [row for row in selected if "ansible.builtin.systemd_service" in row] + [
        row for block in selected for section in ("block", "rescue") for row in block.get(section, [])
        if "ansible.builtin.systemd_service" in row
    ]:
        restart.pop("ansible.builtin.systemd_service")
        restart["ansible.builtin.command"] = {
            "argv": [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).touch()",
            ]
        }
        restart["changed_when"] = True
    result = run_play(tmp_path, selected, {"vpn": {"enable_dns_morph_bridge": enabled}})
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    if not success:
        assert managed.exists()
        assert not marker.exists()
        assert resolver.read_text() == "nameserver 127.0.0.53\n"
    elif enabled:
        assert resolver.resolve() == upstream_file
        assert managed.exists()
    else:
        assert resolver.resolve() == stub
        assert not managed.exists()
        assert marker.exists()


@pytest.mark.parametrize(
    "awg,split,expected4,expected6",
    [
        (False, False, 0, 0),
        (True, False, 1, 1),
        (False, True, 1, 0),
        (True, True, 1, 1),
    ],
)
def test_forwarding_contract_applies_after_baseline_and_removes_legacy_override(
    tmp_path,
    awg,
    split,
    expected4,
    expected6,
):
    directory = tmp_path / "sysctl.d"
    directory.mkdir()
    (directory / "90-vpn.conf").write_text(
        (ANSIBLE / "roles/baseline/templates/sysctl-vpn.conf.j2").read_text()
    )
    (directory / "60-split-hop-egress.conf").write_text("net.ipv4.ip_forward = 1\n")
    selected = relocate(
        tasks("roles/baseline/tasks/forwarding.yml"),
        {
            "/etc/sysctl.d/": str(directory) + "/",
        },
    )
    # This forwarding-contract test exercises the actual configuration modules.
    # Ordered helper installation/execution has separate native sysctl coverage.
    selected = [
        task
        for task in selected
        if task.get("name")
        not in {
            "Ensure baseline policy helper directory",
            "Install ordered mandatory sysctl policy helper",
            "Reconcile effective sysctl values on every converge",
        }
    ]
    result = run_play(
        tmp_path,
        selected,
        {
            "vpn": {
                "enable_amneziawg": awg,
                "enable_split_hop_egress": split,
            }
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (directory / "60-split-hop-egress.conf").exists()
    effective = {}
    for path in sorted(directory.glob("*.conf")):
        for line in path.read_text().splitlines():
            if line.startswith("net.") and "=" in line:
                key, value = line.split("=", 1)
                effective[key.strip()] = value.strip()
    assert effective["net.ipv4.ip_forward"] == str(expected4)
    assert effective["net.ipv6.conf.all.forwarding"] == str(expected6)


def test_hysteria_hopping_keeps_daemon_unprivileged_and_redirects_both_families():
    variables = merge_render_vars()
    variables["hysteria_port_range"] = "20000-40000"
    variables["vpn"] = {
        **variables["vpn"],
        "enable_hysteria": True,
        "enable_amneziawg": False,
    }
    firewall = render_template(
        ANSIBLE / "roles/firewall/templates/nftables.conf.j2", variables
    )
    hysteria = yaml.safe_load(
        render_template(ANSIBLE / "roles/hysteria/templates/config.yaml.j2", variables)
    )
    assert hysteria["listen"] == ":443"
    assert "table inet nat" in firewall
    assert "type nat hook prerouting priority dstnat;" in firewall
    assert "udp dport 20000-40000 counter redirect to :443" in firewall
    assert "chain postrouting" not in firewall
    unit = (ANSIBLE / "roles/hysteria/templates/hysteria-server.service.j2").read_text()
    assert "CAP_NET_ADMIN" not in unit
    variables["hysteria_port_range"] = ""
    disabled = render_template(
        ANSIBLE / "roles/firewall/templates/nftables.conf.j2", variables
    )
    assert "destroy table inet nat" in disabled
    assert "table inet nat {" not in disabled


def test_agent_disable_branch_stops_owned_units():
    disable = named(
        tasks("roles/observability_agent/tasks/main.yml"),
        "Disable observability agent when feature is disabled",
    )
    assert "not (" in disable["when"]
    assert any(
        task["name"] == "Stop and disable observability agent owned units"
        for task in disable["block"]
    )


def validator_fixture(tmp_path: Path):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    systemctl = executable(
        binary_dir / "systemctl", '#!/bin/sh\nprintf "%s\\n" "$TEST_UNIT_ENV"\n'
    )
    binary = executable(
        binary_dir / "xray",
        f"""#!{sys.executable}
import json, os, sys
print(json.dumps({{"asset": os.environ["XRAY_LOCATION_ASSET"], "args": sys.argv[1:]}}))
""",
    )
    environment = {
        **os.environ,
        "PATH": str(binary_dir) + os.pathsep + os.environ["PATH"],
    }
    (tmp_path / "config.json").write_text(guarded_xray_bytes())
    return binary, systemctl, environment


@pytest.mark.parametrize(
    "asset", ["/usr/local/share/xray", "/opt/xray/bundled-assets", "/opt/custom assets"]
)
def test_xray_validator_uses_loaded_service_asset_authority(tmp_path, asset):
    binary, _, environment = validator_fixture(tmp_path)
    environment["TEST_UNIT_ENV"] = (
        json.dumps("XRAY_LOCATION_ASSET=" + asset) + " OTHER=private-sentinel"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--binary",
            str(binary),
            "--config",
            str(tmp_path / "config.json"),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["asset"] == asset
    assert payload["args"] == ["run", "-test", "-config", str(tmp_path / "config.json")]
    assert "private-sentinel" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "unit_env",
    [
        "",
        "OTHER=private-sentinel",
        "XRAY_LOCATION_ASSET=relative/private-sentinel",
        "XRAY_LOCATION_ASSET=/one XRAY_LOCATION_ASSET=/two",
    ],
)
def test_xray_validator_refuses_missing_or_ambiguous_asset_authority(
    tmp_path, unit_env
):
    binary, _, environment = validator_fixture(tmp_path)
    environment["TEST_UNIT_ENV"] = unit_env
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--binary",
            str(binary),
            "--config",
            "/etc/xray/config.json",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    assert result.returncode != 0
    assert not result.stdout
    assert "private-sentinel" not in result.stderr


def test_xray_candidate_validation_can_use_explicit_unpublished_assets(tmp_path):
    binary, systemctl, environment = validator_fixture(tmp_path)
    systemctl.write_text("#!/bin/sh\nexit 99\n")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--binary",
            str(binary),
            "--asset-dir",
            "/candidate/assets",
            "--config",
            str(tmp_path / "config.json"),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["asset"] == "/candidate/assets"


@pytest.mark.parametrize(
    "valid,activation_success", [(False, False), (True, False), (True, True)]
)
def test_config_rollback_preserves_original_on_validation_or_activation_failure(
    private_authority_path,
    valid,
    activation_success,
    monkeypatch,
):
    # Portable real journal/inode boundary model; vendor forwarding is exercised
    # independently by the isolated native rollback lane.
    tmp_path = private_authority_path
    import base64
    sys.path.insert(0, str(ANSIBLE/'roles/runtime-release/files'))
    import transport_runtime_transaction as core
    import transport_runtime_accept as accept
    native_node = core.node
    monkeypatch.setattr(core, 'node', lambda path, _uid, **options: native_node(path, os.getuid(), **options))
    tmp_path.chmod(0o755)
    current, previous = tmp_path/'config.json', tmp_path/'config.json.prev'
    current.write_bytes(b'original'); current.chmod(0o640)
    previous.write_bytes(b'candidate' if valid else b'invalid'); previous.chmod(0o640)
    events = []
    class Boundary:
        def retained(self, _receipt): pass
        def validate_units(self, units): assert units == {'running': True}
        def validate(self):
            events.append('validate')
            if not valid: raise RuntimeError('model-validation-refused')
        def inspect(self): return {'running': True}
        def stop(self): events.append('stop')
        def start(self): events.append('start')
        def ensure(self): return False
        def restore(self, units):
            assert units == {'running': True}
            events.append('restore')
        def ready(self):
            events.append(current.read_text())
            if current.read_bytes() == b'candidate' and not activation_success:
                raise RuntimeError('model-readiness-refused')
    def plan(path, data):
        return {'path':str(path),'data':base64.b64encode(data).decode(),'mode':0o640,'gid':os.getgid()}
    owner = Boundary()
    with core.Transaction(tmp_path/'state', uid=os.getuid()) as tx:
        tx.record('accepted.json', {'schema':1,'nodes':{str(path):core.node(path,os.getuid()) for path in (current,previous)},
                                   'previous':None,'units':owner.inspect()})
    before = [(path.read_bytes(), path.stat().st_ino) for path in (current,previous)]
    receipt = (tmp_path/'state/accepted.json').read_bytes()
    candidate = accept.restore_points([plan(current,previous.read_bytes())])
    with core.Transaction(tmp_path/'state',uid=os.getuid()) as tx:
        if valid and activation_success:
            tx.apply(candidate,owner)
        else:
            with pytest.raises(RuntimeError): tx.apply(candidate,owner)
    if valid and activation_success:
        assert current.read_bytes() == b'candidate' and previous.read_bytes() == b'original'
    else:
        assert [(path.read_bytes(),path.stat().st_ino) for path in (current,previous)] == before
        assert (tmp_path/'state/accepted.json').read_bytes() == receipt
    if not valid:
        assert events == ['validate']
    elif not activation_success:
        assert events[-2:] == ['restore','original']
    operator = tasks('playbooks/rollback-config.yml')[0]['tasks'][0]
    assert "transport_runtime_rollback.py', 'config'" in operator['ansible.builtin.command']['argv']
    assert operator['check_mode'] is False and operator['no_log'] is True and operator['diff'] is False


@pytest.mark.parametrize(
    "monitoring,instances,expected",
    [
        (False, ["awg-blue", "awg-green"], ["nftables", "xray"]),
        (True, ["awg0"], ["nftables", "prometheus-node-exporter", "xray"]),
    ],
)
def test_maintenance_selects_effective_services_and_every_awg_instance(
    tmp_path, monitoring, instances, expected
):
    maintenance = tasks("playbooks/os-maintenance.yml")[0]["tasks"]
    service = named(maintenance, "Verify enabled transport services after maintenance")
    awg = named(maintenance, "Verify AmneziaWG after maintenance")
    for task in (service, awg):
        task.pop("ansible.builtin.command")
        task["ansible.builtin.debug"] = {"msg": "{{ item }}"}
    service["register"] = "service_results"
    awg["register"] = "awg_results"
    result = run_play(
        tmp_path,
        [
            service,
            awg,
            {
                "ansible.builtin.assert": {
                    "that": [
                        'service_results.results | map(attribute="item") | list == expected_services',
                        'awg_results.results | map(attribute="item") | list == expected_instances',
                    ]
                }
            },
        ],
        {
            "vpn": {
                "enable_monitoring": monitoring,
                "enable_amneziawg": True,
                "enable_xray_reality": True,
                "enable_nginx_xhttp": False,
                "enable_hysteria": False,
            },
            "_awg_instances": [{"name": name} for name in instances],
            "expected_services": expected,
            "expected_instances": instances,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("runtime_changed", [False, True])
def test_binary_only_collector_updates_restart_the_selected_runtime(
    tmp_path, runtime_changed
):
    collector = named(
        tasks("roles/observability_control_plane/tasks/enable.yml"),
        "Activate complete validated Prometheus generation with rollback",
    )
    receiver = named(
        collector["block"], "Start or restart Prometheus for the published generation"
    )
    state = receiver.pop("ansible.builtin.systemd_service")["state"]
    receiver["ansible.builtin.debug"] = {"msg": state}
    receiver["register"] = "collector_action"
    result = run_play(
        tmp_path,
        [
            receiver,
            {
                "ansible.builtin.assert": {
                    "that": [
                        'collector_action.msg == ("restarted" if binary_changed else "started")',
                    ]
                }
            },
        ],
        {
            "_observability_agent_runtime_changed": runtime_changed,
            "_observability_agent_generation_switch": {"changed": False},
            "_observability_agent_units": {"changed": False},
            "_observability_agent_service_active": {"rc": 0},
            "_observability_prometheus_runtime_changed": runtime_changed,
            "_observability_prometheus_unit": {"changed": False},
            "_observability_prometheus_activation": {"changed": False},
            "binary_changed": runtime_changed,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_collector_failed_upgrade_restores_the_old_binary_link(tmp_path):
    collector = named(
        tasks("roles/observability_control_plane/tasks/enable.yml"),
        "Activate complete validated Prometheus generation with rollback",
    )
    root = tmp_path / "collector"
    (root / "releases/old").mkdir(parents=True)
    (root / "releases/new").mkdir()
    (root / "current").symlink_to(root / "releases/new")
    receiver = named(collector["rescue"], "Restore the previous collector binary after failed activation")
    result = run_play(tmp_path, [receiver], {
        "observability_control_plane": {"install_root": str(root)},
        "_observability_prometheus_runtime_changed": True,
        "_observability_prometheus_previous_release": {"stat": {
            "islnk": True, "lnk_source": str(root / "releases/old")}},
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "current").resolve() == root / "releases/old"


def test_existing_ingress_complete_authority_uses_the_compensating_transaction():
    source = tasks("roles/observability_control_plane/tasks/enable.yml")
    ingress = named(
        source, "Publish complete isolated mTLS ingress candidate with compensation"
    )
    assert ingress["ansible.builtin.include_role"] == {
        "name": "nginx-xhttp",
        "tasks_from": "transaction",
    }
    inputs = ingress["vars"]
    assert inputs["nginx_transaction_unit"] == "observability-ingress.service"
    assert inputs["nginx_transaction_activation"] == "restart"
    assert (
        inputs["nginx_transaction_credential_root"]
        == "{{ observability_control_plane.config_root }}/tls"
    )
    config = named(source, "Build the exact isolated ingress authority write set")[
        "ansible.builtin.set_fact"
    ]["_observability_ingress_files"]
    assert {row["path"] for row in config} == {
        "{{ observability_control_plane.config_root }}/nginx.conf",
        "/etc/systemd/system/observability-ingress.service",
    }
    tls = named(source, "Append exact isolated ingress TLS authority")
    assert {row["name"] for row in tls["loop"]} == {
        "server.crt",
        "server.key",
        "client-ca.crt",
        "client.crl",
    }
    assert (
        "content_b64" in tls["ansible.builtin.set_fact"]["_observability_ingress_files"]
    )
    assert ingress.get("no_log", True)


@pytest.mark.parametrize("component", ["sender", "collector"])
@pytest.mark.parametrize("had_previous", [False, True])
def test_observability_early_validation_failure_reverts_binary_before_retry(
    tmp_path, component, had_previous
):
    root = tmp_path / "runtime"
    (root / "old").mkdir(parents=True)
    (root / "new").mkdir()
    (root / "current").symlink_to(root / "new")
    if component == "sender":
        outer = named(
            tasks("roles/observability_agent/tasks/main.yml"),
            "Configure observability agent when feature is enabled",
        )
        role, prefix = "observability_agent", "_observability_agent"
    else:
        outer = named(
            tasks("roles/observability_control_plane/tasks/main.yml"),
            "Reconcile control-plane lifecycle with runtime rollback",
        )
        role, prefix = "observability_control_plane", "_observability_prometheus"
    # Sender acquisition stages without changing current. Collector acquisition
    # still publishes before this boundary and requires its outer compensation.
    if component == "sender":
        (root / "current").unlink()
        if had_previous:
            (root / "current").symlink_to(root / "old")
        role_source = (ANSIBLE / "roles/observability_agent/tasks/main.yml").read_text()
        assert "runtime_release_stage_only: true" in role_source
    before_inode = (root / "current").lstat().st_ino if (root / "current").is_symlink() else None
    outer["block"] = [
        {"ansible.builtin.fail": {"msg": "synthetic candidate validation failure"}}
    ]
    outer.pop("when", None)
    previous = {"exists": had_previous, "islnk": had_previous}
    if had_previous:
        previous["lnk_source"] = str(root / "old")
    result = run_play(
        tmp_path,
        [outer],
        {
            role: {"install_root": str(root)},
            f"{prefix}_runtime_ready": False,
            f"{prefix}_previous_release": {"stat": previous},
        },
    )
    assert result.returncode != 0
    if had_previous:
        assert (root / "current").resolve() == root / "old"
        if component == "sender":
            assert (root / "current").lstat().st_ino == before_inode
    else:
        assert not (root / "current").is_symlink()


def test_collector_restores_exact_previous_unit_before_restarting(tmp_path):
    activation = named(
        tasks("roles/observability_control_plane/tasks/enable.yml"),
        "Activate complete validated Prometheus generation with rollback",
    )
    names = [task["name"] for task in activation["rescue"]]
    restore_name = "Restore previous Prometheus unit after failed activation"
    assert names.index(restore_name) < names.index(
        "Restore previous ready Prometheus service"
    )
    restore = named(activation["rescue"], restore_name)
    unit = tmp_path / "observability-prometheus.service"
    unit.write_text("candidate")
    restore["ansible.builtin.copy"]["dest"] = str(unit)
    restore["ansible.builtin.copy"].pop("owner")
    restore["ansible.builtin.copy"].pop("group")
    import base64

    original = "[Service]\nExecStart=/previous/prometheus --previous-arguments\n"
    result = run_play(
        tmp_path,
        [restore],
        {
            "_observability_prometheus_previous_unit": {"stat": {"exists": True}},
            "_observability_prometheus_previous_unit_bytes": {
                "content": base64.b64encode(original.encode()).decode(),
            },
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert unit.read_text() == original


@pytest.mark.parametrize(
    "base_enabled,override,share",
    [
        (False, None, False),
        (True, None, True),
        (True, False, False),
        (False, True, True),
    ],
)
def test_realm_role_defaults_preserve_standalone_tls_without_p2(
    tmp_path, base_enabled, override, share
):
    role = ANSIBLE / "roles/hysteria-realm"
    production = tasks("roles/hysteria-realm/tasks/main.yml")
    account = named(production, "Ensure system user")
    spec = account.pop("ansible.builtin.user")
    account["ansible.builtin.debug"] = {"msg": spec}
    account["register"] = "realm_account"
    copy_tls = named(production, "Drop TLS material when not sharing the hysteria cert")
    copy_tls["ansible.builtin.copy"].pop("owner")
    copy_tls["ansible.builtin.copy"].pop("group")
    copy_tls["ansible.builtin.copy"]["dest"] = (
        str(tmp_path) + "/{{ item.dest | basename }}"
    )
    shared_tls = named(production, "Stage shared TLS material from hysteria config dir")
    shared_spec = shared_tls.pop("ansible.builtin.file")
    shared_tls["ansible.builtin.debug"] = {"msg": shared_spec}
    shared_tls["register"] = "realm_shared_tls"
    checks = {
        "ansible.builtin.assert": {
            "that": [
                'hysteria_realm.version == "v1.14.0-alpha.22"',
                'hysteria_realm.install_root == "/opt/hysteria-realm"',
                "hysteria_realm.listen_port | int == 8444",
                "hysteria_realm.share_hysteria_tls | bool == expected_share",
                "realm_account.msg.append == expected_share",
                '(realm_account.msg.groups | default([])) == (["hysteria"] if expected_share else [])',
                "(realm_shared_tls.skipped | default(false)) == (not expected_share)",
            ]
        },
    }
    probe_role = tmp_path / "probe-role"
    (probe_role / "tasks").mkdir(parents=True)
    (probe_role / "defaults").mkdir()
    (probe_role / "defaults/main.yml").write_bytes(
        (role / "defaults/main.yml").read_bytes()
    )
    probe = probe_role / "tasks/main.yml"
    probe.write_text(yaml.safe_dump([account, copy_tls, shared_tls, checks]))
    variables = {
        **yaml.safe_load((ANSIBLE / "group_vars/vpn-ci-p0p5.yml").read_text()),
        "hysteria_realm_listen_port": 8444,
        "hysteria_config_dir": "/nonexistent-p2-config",
        "hysteria": {"cert_pem": "synthetic-cert", "key_pem": "synthetic-key"},
        "expected_share": share,
    }
    variables["vpn"]["enable_hysteria"] = base_enabled
    if override is not None:
        # Explicit complete role overrides retain the existing caller contract.
        variables["hysteria_realm"] = yaml.safe_load(
            (role / "defaults/main.yml").read_text()
        )["hysteria_realm"]
        variables["hysteria_realm"]["share_hysteria_tls"] = override
    result = run_play(
        tmp_path,
        [
            {
                "ansible.builtin.include_role": {"name": str(probe_role)},
            }
        ],
        variables,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for filename, expected in [
        ("server.fullchain.pem", "synthetic-cert"),
        ("server.key", "synthetic-key"),
    ]:
        destination = tmp_path / filename
        assert destination.exists() != share
        if not share:
            assert destination.read_text() == expected


def test_split_hop_molecule_verifies_the_production_forwarding_file(tmp_path):
    directory = tmp_path / "sysctl.d"
    directory.mkdir()
    (directory / "60-split-hop-egress.conf").write_text("legacy forwarding\n")
    produce = [
        task
        for task in tasks("roles/baseline/tasks/forwarding.yml")
        if task.get("name")
        not in {
            "Ensure baseline policy helper directory",
            "Install ordered mandatory sysctl policy helper",
            "Reconcile effective sysctl values on every converge",
        }
    ]
    verify = tasks("roles/split-hop-egress/molecule/default/verify.yml")[0]["tasks"]
    names = {
        "Canonical forwarding drop-in exists",
        "Superseded forwarding drop-in is absent",
        "Read canonical forwarding policy",
        "Assert IPv4-only forwarding policy for the split-hop workload",
    }
    selected = [task for task in verify if task["name"] in names]
    assert len(selected) == len(names)
    result = run_play(
        tmp_path,
        relocate(
            produce + selected,
            {
                "/etc/sysctl.d/": str(directory) + "/",
            },
        ),
        {"vpn": {"enable_split_hop_egress": True, "enable_amneziawg": False}},
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("activation_failure", [True, False])
def test_agent_molecule_distinguishes_activation_from_preflight_through_outer_rescue(
    tmp_path,
    activation_failure,
):
    outer = named(
        tasks("roles/observability_agent/tasks/main.yml"),
        "Configure observability agent when feature is enabled",
    )
    inner_refusal = named(outer["block"], "Refuse failed observability generation activation")
    # Only exercise exception propagation here; native systemd restoration stays
    # in Molecule. Stale readiness facts must never make preflight count as it.
    outer["block"] = [
        (
            inner_refusal
            if activation_failure
            else {
                "name": "Refuse invalid candidate before activation",
                "ansible.builtin.fail": {"msg": "synthetic preflight refusal"},
            }
        )
    ]
    outer.pop("when", None)
    fixture = tasks(
        "roles/observability_agent/molecule/enabled/tasks/failed-activation.yml"
    )
    exercise = named(
        fixture, "Exercise actual activation failure and exact runtime restoration"
    )
    submission = named(
        exercise["block"], "Submit the native-valid but unstartable generation"
    )
    acceptance = named(
        submission["rescue"],
        "Require the actual activation rescue rather than preflight refusal",
    )
    result = run_play(
        tmp_path,
        [{"block": [outer], "rescue": [acceptance]}],
        {
            "observability_agent": {"install_root": str(tmp_path / "runtime")},
            "_observability_agent_runtime_ready": False,
            "_observability_agent_failed_task_name": inner_refusal["name"],
            "_observability_agent_can_restore_runtime": True,
            "_observability_agent_restored_ready": {"rc": 0},
            "_observability_agent_acceptance": {"rc": 2},
        },
    )
    assert (result.returncode == 0) == activation_failure, result.stdout + result.stderr
