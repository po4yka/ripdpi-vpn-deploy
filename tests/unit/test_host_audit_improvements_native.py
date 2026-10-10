"""Supported native scanner output and memory-only TLS lifetime validation."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_supported_lynis_scan_produces_fresh_completed_machine_receipt(tmp_path):
    assert os.geteuid() == 0 and shutil.which("lynis")
    collector = load(
        "ansible/roles/security_audit/files/lynis_collect.py", "native_lynis_collect"
    )
    report = tmp_path / "scan"
    report.mkdir(mode=0o700)
    result = collector.collect(str(report))
    assert result["collection_success"] is True
    raw = (report / "report.dat").read_text()
    assert result["warnings"] == sum(
        line.startswith("warning[]=") for line in raw.splitlines()
    )
    assert "finish=true" in raw
    assert (report / "command-output.txt").stat().st_mode & 0o777 == 0o600
    # Reusing a prior report directory never manufactures a new clean receipt.
    with pytest.raises(ValueError, match="fresh"):
        collector.collect(str(report))


def test_self_steal_memory_tls_preflight_preserves_seven_day_floor(tmp_path):
    assert os.geteuid() == 0 and shutil.which("openssl")
    helper = load(
        "ansible/roles/subscription-host/files/subscription_tls.py",
        "native_self_steal_tls",
    )
    for days in (1, 30):
        key, cert = tmp_path / f"{days}.key", tmp_path / f"{days}.crt"
        result = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-subj",
                "/CN=edge.example.test",
                "-addext",
                "subjectAltName=DNS:edge.example.test",
                "-days",
                str(days),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0
        request = {
            "certificate": cert.read_text(),
            "private_key": key.read_text(),
            "hostname": "edge.example.test",
        }
        if days == 1:
            with pytest.raises(ValueError):
                helper.validate(request, 604800)
        else:
            helper.validate(request, 604800)
            with pytest.raises(ValueError):
                helper.validate({**request, "hostname": "wrong.example.test"}, 604800)
    assert not Path("/run/reality-self-steal").exists()


def test_real_exporter_private_socket_and_scrape_agree_with_normalized_endpoint():
    import sys

    assert os.geteuid() == 0 and shutil.which("prometheus-node-exporter")
    helper = ROOT / "ansible/roles/monitoring/files/private_endpoint.py"
    script = r"""
import importlib.util,json,os,socket,subprocess,time,urllib.request
spec=importlib.util.spec_from_file_location('endpoint',HELPER)
endpoint=importlib.util.module_from_spec(spec);spec.loader.exec_module(endpoint)
subprocess.run(['ip','link','set','lo','up'],check=True)
subprocess.run(['ip','addr','add','100.64.0.2/32','dev','lo'],check=True)
subprocess.run(['ip','-6','addr','add','fd7a:115c:a1e0::2/128','dev','lo'],check=True)
local=[row['local'] for interface in json.loads(subprocess.check_output(['ip','-j','addr'])) for row in interface['addr_info']]
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for address in ['127.0.0.1','::1','100.64.0.2','fd7a:115c:a1e0::2']:
    family=socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family) as listener:
        listener.bind((address,0)); port=listener.getsockname()[1]
    host='['+address+']' if ':' in address else address
    selected=endpoint.validate({'endpoint':host+':'+str(port),'approved_tailnet_addresses':['100.64.0.2','fd7a:115c:a1e0::2'],'local_addresses':local})
    process=subprocess.Popen(['prometheus-node-exporter','--web.listen-address='+selected['endpoint'],'--collector.disable-defaults'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for attempt in range(100):
            try:
                response=client.open('http://'+selected['endpoint']+'/metrics',timeout=2)
                body=response.read(1048576).decode(); break
            except OSError:
                assert process.poll() is None; time.sleep(0.02)
        else: raise AssertionError('exporter did not serve private metrics')
        assert response.status==200 and 'node_exporter_build_info' in body
        before=process.pid
        for bad in ['0.0.0.0:9100','[::]:9100','192.0.2.1:9100','localhost:9100',host+':'+str(port)+' --web.config.file=/tmp/config']:
            try: endpoint.validate({'endpoint':bad,'approved_tailnet_addresses':[],'local_addresses':local})
            except ValueError: pass
            else: raise AssertionError('unsafe endpoint admitted')
        assert process.pid==before and process.poll() is None
        assert client.open('http://'+selected['endpoint']+'/metrics',timeout=2).status==200
    finally:
        process.terminate(); process.wait(timeout=5)
print('four approved private sockets/scrapes; unsafe input preserves active process')
""".replace("HELPER", repr(str(helper)))
    result = subprocess.run(
        ["unshare", "--net", sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "four approved private sockets/scrapes" in result.stdout


@pytest.mark.parametrize("child", ["sub", "bootstrap", ".vpn-bootstrap-consumed"])
@pytest.mark.parametrize("kind", ["symlink", "mode", "missing"])
def test_actual_subscription_retained_child_preflight_preserves_authority(
    tmp_path, child, kind
):
    import pwd
    import yaml

    assert os.geteuid() == 0
    try:
        account = pwd.getpwnam("vpn-bootstrap")
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                "vpn-bootstrap",
            ],
            check=True,
        )
        account = pwd.getpwnam("vpn-bootstrap")
    root = tmp_path / "payload"
    for path in [root] + [
        root / name for name in ("sub", "bootstrap", ".vpn-bootstrap-consumed")
    ]:
        path.mkdir(parents=True, mode=0o700)
        path.chmod(0o700)
        (os.chown(path, account.pw_uid, account.pw_gid))
    for name, data in (
        (".vpn-bootstrap-state.lock", ""),
        (".vpn-bootstrap-retired-before", '{"schema":1,"retired_before":0}'),
    ):
        path = root / name
        path.write_text(data)
        path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)
    target = tmp_path / "foreign"
    target.mkdir(mode=0o755)
    (target / "public-fixture").write_text("retain target bytes")
    before = (
        target.stat().st_uid,
        target.stat().st_gid,
        target.stat().st_mode,
        (target / "public-fixture").read_bytes(),
    )
    unsafe = root / child
    if kind == "symlink":
        unsafe.rmdir()
        unsafe.symlink_to(target, target_is_directory=True)
    elif kind == "mode":
        unsafe.chmod(0o777)
    else:
        unsafe.rmdir()
    play = tmp_path / "guard.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "subscription": {
                            "subscription_dir": str(root),
                            "cert_pem": "public fixture",
                            "key_pem": "public fixture",
                        }
                    },
                    "roles": [{"role": str(ROOT / "ansible/roles/subscription-host")}],
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "retention authority provisioning refused" in result.stdout
    assert "Ensure subscription dir" not in result.stdout
    assert (
        target.stat().st_uid,
        target.stat().st_gid,
        target.stat().st_mode,
        (target / "public-fixture").read_bytes(),
    ) == before
    if kind == "mode":
        assert unsafe.stat().st_mode & 0o777 == 0o777
    elif kind == "missing":
        assert not unsafe.exists()


@pytest.mark.parametrize("bad_root", ["site", "tls"])
@pytest.mark.parametrize("kind", ["writable", "symlink", "foreign"])
def test_actual_self_steal_root_guard_never_repairs_unsafe_metadata(
    tmp_path, bad_root, kind
):
    import yaml

    assert os.geteuid() == 0
    roots = {name: tmp_path / name for name in ("site", "tls")}
    for path in roots.values():
        path.mkdir(mode=0o750)
    unsafe = roots[bad_root]
    if kind == "writable":
        unsafe.chmod(0o777)
    elif kind == "foreign":
        os.chown(unsafe, 65534, 65534)
    else:
        unsafe.rmdir()
        target = tmp_path / "foreign-target"
        target.mkdir(mode=0o777)
        unsafe.symlink_to(target, target_is_directory=True)
    target = unsafe.resolve()
    (target / "public-fixture").write_text("preserve existing bytes")
    before = (
        target.stat().st_uid,
        target.stat().st_gid,
        target.stat().st_mode,
        (target / "public-fixture").read_bytes(),
    )
    source = yaml.safe_load(
        (ROOT / "ansible/roles/reality-self-steal/tasks/configure.yml").read_text()
    )
    names = {
        "Inspect owned candidate roots without following links",
        "Require existing candidate roots to retain safe owned directory authority",
        "Prepare empty directory scaffold for private candidate binding",
    }
    guards = [task for task in source if task["name"] in names]
    assert len(guards) == 3
    play = tmp_path / "roots.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "reality_self_steal_site_root": str(roots["site"]),
                        "reality_self_steal_tls_dir": str(roots["tls"]),
                    },
                    "tasks": guards,
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Prepare empty directory scaffold" not in result.stdout
    assert (
        target.stat().st_uid,
        target.stat().st_gid,
        target.stat().st_mode,
        (target / "public-fixture").read_bytes(),
    ) == before


def test_actual_retained_runtime_missing_payload_refuses_before_host_mutation(tmp_path):
    import yaml

    assert os.geteuid() == 0
    installed = Path("/usr/local/bin/vpn-bootstrap.py")
    assert (
        not installed.exists()
    ), "fixture must not overwrite unrelated bootstrap runtime"
    # Its retained presence is the authority boundary; it is never executed.
    installed.write_bytes(
        (
            ROOT / "ansible/roles/subscription-host/files/retention_authority.py"
        ).read_bytes()
    )
    installed.chmod(0o755)
    root = tmp_path / "missing-payload"
    play = tmp_path / "missing-retained.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "subscription": {
                            "subscription_dir": str(root),
                            "cert_pem": "public fixture",
                            "key_pem": "public fixture",
                        }
                    },
                    "roles": [{"role": str(ROOT / "ansible/roles/subscription-host")}],
                }
            ]
        )
    )
    try:
        before = installed.read_bytes()
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(play)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert "retention authority provisioning refused" in result.stdout
        assert "Ensure nginx is present" not in result.stdout
        assert installed.read_bytes() == before
        assert not root.exists()
    finally:
        installed.unlink()


def test_real_maintenance_unit_floor_collects_retired_markers_and_bounds_private_audit():
    import json
    import pwd
    import sys
    import time
    import uuid
    from jinja2 import Environment, StrictUndefined

    assert os.geteuid() == 0
    account = pwd.getpwnam("vpn-bootstrap")
    suffix = uuid.uuid4().hex[:12]
    base = Path("/var/lib") / ("vpn-p2-sub-maint-" + suffix)
    base.mkdir(mode=0o755)
    payload, logs = base / "payload", base / "logs"
    for path in [payload, logs] + [
        payload / name for name in ("sub", "bootstrap", ".vpn-bootstrap-consumed")
    ]:
        path.mkdir(mode=0o700)
        os.chown(path, account.pw_uid, account.pw_gid)

    def authority(path, data):
        path.write_text(data)
        path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)

    authority(payload / ".vpn-bootstrap-state.lock", "")
    authority(
        payload / ".vpn-bootstrap-retired-before", '{"schema":1,"retired_before":0}'
    )
    issued = int(time.time()) - 2592000 - 10
    marker = payload / ".vpn-bootstrap-consumed" / ("a" * 64)
    authority(
        marker, json.dumps({"schema": 1, "issued": issued, "expires": issued + 60})
    )
    authority(logs / "reads.log", '{"public":"fixture"}\n' * 1000)
    subscription = {
        "subscription_dir": str(payload),
        "reads_log": str(logs / "reads.log"),
        "bootstrap_max_lifetime_seconds": 60,
        "reads_log_max_bytes": 4096,
        "reads_log_backup_count": 2,
    }
    env = Environment(
        undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True
    )
    env.filters["dirname"] = lambda value: str(Path(value).parent)
    script = base / "bootstrap.py"
    script.write_text(
        env.from_string(
            (
                ROOT / "ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2"
            ).read_text()
        ).render(subscription=subscription)
    )
    script.chmod(0o755)
    name = "vpn-p2-sub-maint-" + suffix + ".service"
    unit = Path("/etc/systemd/system") / name
    source = env.from_string(
        (
            ROOT
            / "ansible/roles/subscription-host/templates/vpn-subscription-maintenance.service.j2"
        ).read_text()
    ).render(subscription=subscription)
    unit.write_text(source.replace("/usr/local/bin/vpn-bootstrap.py", str(script)))
    try:
        subprocess.run(
            ["systemd-analyze", "verify", str(unit)], capture_output=True, check=True
        )
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, check=True)
        result = subprocess.run(
            ["systemctl", "start", name], capture_output=True, text=True, timeout=15
        )
        if result.returncode:
            result.stdout += subprocess.run(
                ["journalctl", "-u", name, "--no-pager", "--output=cat", "--lines=8"],
                capture_output=True,
                text=True,
            ).stdout
        assert result.returncode == 0, result.stdout + result.stderr
        assert not marker.exists()
        assert (
            json.loads((payload / ".vpn-bootstrap-retired-before").read_text())[
                "retired_before"
            ]
            >= issued
        )
        assert (logs / "reads.log").stat().st_size <= 4096
        assert (logs / "reads.log").stat().st_mode & 0o777 == 0o600
        assert (logs / "reads.log").stat().st_uid == account.pw_uid
    finally:
        subprocess.run(["systemctl", "stop", name], capture_output=True)
        unit.unlink()
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
