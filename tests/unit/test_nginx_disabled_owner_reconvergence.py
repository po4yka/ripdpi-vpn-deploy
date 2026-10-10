"""Actual shared-role convergence preserves never-created disabled payload roots."""

from __future__ import annotations

import base64
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def command(argv, *, data=None):
    result = subprocess.run(
        argv, input=data, capture_output=True, text=True, timeout=150
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-1000:]
    return result.stdout


def helper():
    assert sys.platform == "linux" and os.geteuid() == 0
    source = ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py"
    spec = importlib.util.spec_from_file_location("nginx_transaction", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(root, owner):
    return {
        "owner": owner,
        "roots": [str(root)],
        "files": [{"path": str(root / "absent.conf"), "kind": "absent"}],
        "validate_argv": ["/usr/sbin/nginx", "-t"],
        "unit": "nginx.service",
        "activation": "reload",
        "check": False,
        "credential_root": "",
        "runtime_directories": [],
        "activate_inactive": False,
        "desired_enabled": None,
        "prune_releases": None,
    }


@pytest.mark.parametrize("required", ["file", "credential"])
def test_missing_required_root_refuses_without_publication(required):
    tx = helper()
    with tempfile.TemporaryDirectory(
        prefix="vpn-nginx-required-", dir="/var/lib"
    ) as work:
        root = Path(work) / "missing"
        document = request(root, "missing-root-regression")
        if required == "file":
            document["files"] = [
                {
                    "path": str(root / "required.conf"),
                    "kind": "file",
                    "mode": "0644",
                    "uid": 0,
                    "gid": 0,
                    "content_b64": base64.b64encode(b"required bytes\n").decode(),
                }
            ]
        else:
            document["credential_root"] = str(root)
            document["activate_inactive"] = True
        before = tx.service_state("nginx.service")
        with pytest.raises(tx.TransactionError, match="^missing-root$"):
            tx.publish(document)
        assert not root.exists()
        assert tx.service_state("nginx.service") == before
        assert not Path(
            "/var/lib/vpn-nginx-publication/nginx.service/pending.json"
        ).exists()


def test_unsafe_existing_disabled_root_refuses_preserving_bytes_and_metadata():
    tx = helper()
    with tempfile.TemporaryDirectory(
        prefix="vpn-nginx-unsafe-", dir="/var/lib"
    ) as work:
        root = Path(work) / "unsafe"
        root.mkdir(mode=0o777)
        root.chmod(0o777)
        foreign = root / "untouched"
        foreign.write_bytes(b"prior bytes\n")
        before = (root.stat(), foreign.stat(), tx.service_state("nginx.service"))
        with pytest.raises(tx.TransactionError, match="^unsafe-parent$"):
            tx.publish(request(root, "unsafe-root-regression"))
        assert foreign.read_bytes() == b"prior bytes\n"
        assert stat.S_IMODE(root.stat().st_mode) == 0o777
        assert (root.stat().st_uid, root.stat().st_gid) == (
            before[0].st_uid,
            before[0].st_gid,
        )
        assert foreign.stat().st_ino == before[1].st_ino
        assert tx.service_state("nginx.service") == before[2]


@pytest.mark.parametrize(
    "case",
    [
        "equal",
        "older-master",
        "other-boot",
        "stale",
        "future",
        "bool-ticks",
        "unknown",
        "foreign-mode",
    ],
)
def test_inactive_witness_boundaries_adopt_or_preserve_refused_authority(case):
    tx = helper()
    before_service = tx.service_state("nginx.service")
    with tempfile.TemporaryDirectory(
        prefix="vpn-nginx-witness-", dir="/var/lib"
    ) as work:
        document = request(Path(work), "witness-" + uuid.uuid4().hex[:12])
        tx.request(document)
        receipt = Path("/var/lib/vpn-nginx-publication/nginx.service") / (
            document["owner"] + ".activated.json"
        )
        assert not os.path.lexists(receipt)
        try:
            command(["systemctl", "start", "nginx.service"])
            tx.wait_adoption("nginx.service")
            master = tx.nginx_master("nginx.service")
            workers = tx.nginx_workers(master)
            boot, now = tx.boot_clock()
            witness = {
                "schema": 1,
                "fingerprint": tx.fingerprint(document),
                "active": False,
                "boot_id": boot,
                "inactive_after_ticks": int(master[1]),
            }
            if case == "older-master":
                witness["inactive_after_ticks"] = now
            elif case == "other-boot":
                witness["boot_id"] = str(uuid.uuid4())
            elif case == "stale":
                witness["fingerprint"] = "0" * 64
            elif case == "future":
                witness["inactive_after_ticks"] = now + 100000
            elif case == "bool-ticks":
                witness["inactive_after_ticks"] = True
            elif case == "unknown":
                witness["unknown"] = True
            tx.persist(receipt, witness)
            if case == "foreign-mode":
                receipt.chmod(0o644)
            before_bytes, before_metadata = receipt.read_bytes(), receipt.stat()
            if case in {"future", "bool-ticks", "unknown", "foreign-mode"}:
                with pytest.raises(tx.TransactionError):
                    tx.publish(document)
                assert receipt.read_bytes() == before_bytes
                assert receipt.stat().st_mode == before_metadata.st_mode
                assert receipt.stat().st_ino == before_metadata.st_ino
                assert tx.nginx_master("nginx.service") == master
                assert tx.nginx_workers(master) == workers
                assert not (receipt.parent / "pending.json").exists()
            else:
                assert tx.publish(document)["changed"] is True
                assert tx.nginx_master("nginx.service") == master
                assert tx.nginx_workers(master).isdisjoint(workers)
                assert tx.private_json(receipt)["active"] is True
        finally:
            tx.clear(receipt)
            if not before_service["active"]:
                command(["systemctl", "stop", "nginx.service"])


def test_actual_disabled_self_steal_then_enabled_xhttp_converges_twice():
    tx = helper()
    available = Path("/etc/nginx/sites-available/vpn-xhttp.conf")
    enabled = Path("/etc/nginx/sites-enabled/vpn-xhttp.conf")
    assert not os.path.lexists(available) and not os.path.lexists(enabled)
    suffix = uuid.uuid4().hex[:12]
    base = Path("/var/lib") / ("vpn-nginx-shared-" + suffix)
    hostname = "shared-" + suffix + ".example.test"
    cert = Path("/etc/nginx/tls") / (hostname + ".fullchain.pem")
    key = Path("/etc/nginx/tls") / (hostname + ".key")
    assert not os.path.lexists(cert) and not os.path.lexists(key)
    hosts = Path("/etc/hosts")
    hosts_bytes, hosts_metadata = hosts.read_bytes(), hosts.stat()
    site = Path("/var/www/public-site")
    site_existed = os.path.lexists(site)
    if site_existed:
        assert stat.S_ISDIR(
            site.lstat().st_mode
        ), "fixture cannot replace a foreign site root"
        # Root copytree preserves bytes/modes/times, but not foreign uid/gid.
        # Refuse those trees before any service or role mutation.
        for directory, folders, files in os.walk(site, followlinks=False):
            for path in [
                Path(directory),
                *(Path(directory) / name for name in folders + files),
            ]:
                info = path.lstat()
                assert (
                    info.st_uid == os.geteuid() and info.st_gid == os.getegid()
                ), "fixture cannot repair foreign site ownership"
                assert stat.S_ISLNK(info.st_mode) or (
                    (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    and not info.st_mode & 0o022
                ), "fixture cannot replace unsafe site authority"
    base.mkdir(mode=0o700)
    if site_existed:
        shutil.copytree(site, base / "prior-site", symlinks=True)
    before_service = tx.service_state("nginx.service")
    receipt = Path(
        "/var/lib/vpn-nginx-publication/nginx.service/nginx-xhttp.activated.json"
    )
    before_receipt = tx.capture(receipt)
    self_receipt = receipt.with_name("reality-self-steal.activated.json")
    before_self_receipt = tx.capture(self_receipt)
    absent_site, absent_tls = base / "never-enabled-site", base / "never-enabled-tls"
    try:
        command(["systemctl", "stop", "nginx.service"])
        command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(base / "key"),
                "-out",
                str(base / "cert"),
                "-subj",
                "/CN=" + hostname,
                "-addext",
                "subjectAltName=DNS:" + hostname,
                "-days",
                "1",
            ]
        )
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        values = yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text())
        values.update(
            vpn={"enable_xray_reality": False, "enable_snell": False},
            vpn_service_address="127.0.0.1",
            nginx_xhttp_public_port=port,
            public_site_canonical_url="https://" + hostname,
            reality_self_steal_site_root=str(absent_site),
            reality_self_steal_tls_dir=str(absent_tls),
            nginx_xhttp={
                "server_name": hostname,
                "cert_pem": (base / "cert").read_text(),
                "key_pem": (base / "key").read_text(),
            },
            xray={"xhttp_path": "/shared-fixture"},
        )
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": values,
                "roles": [
                    {
                        "role": str(ROOT / "ansible/roles/reality-self-steal"),
                        "reality_self_steal_role_enabled": False,
                    },
                    {"role": str(ROOT / "ansible/roles/nginx-xhttp")},
                ],
            }
        ]
        play_path = base / "converge.yml"
        play_path.write_text(yaml.safe_dump(play))
        play_path.chmod(0o600)
        argv = ["ansible-playbook", "-i", "localhost,", str(play_path)]
        command(argv)
        assert not absent_site.exists() and not absent_tls.exists()
        disk_witness = tx.private_json(self_receipt)
        assert disk_witness["active"] is False
        # The role's first public-site writes notify a deferred reload.
        # Wait for its actual pool before measuring the unchanged rerun.
        tx.wait_adoption("nginx.service")
        master = tx.nginx_master("nginx.service")
        workers = tx.nginx_workers(master)
        assert disk_witness["boot_id"] == tx.boot_clock()[0]
        assert int(master[1]) > disk_witness["inactive_after_ticks"]
        second = command(argv)
        assert "changed=0" in second and "failed=0" in second
        assert tx.nginx_master("nginx.service") == master
        assert tx.nginx_workers(master) == workers
        assert tx.private_json(self_receipt)["active"] is True
        assert not absent_site.exists() and not absent_tls.exists()
        context = ssl.create_default_context(cafile=str(base / "cert"))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with socket.create_connection(("127.0.0.1", port), timeout=3) as plain:
            with context.wrap_socket(plain, server_hostname=hostname) as connection:
                connection.sendall(
                    (
                        "GET / HTTP/1.1\r\nHost: "
                        + hostname
                        + "\r\nConnection: close\r\n\r\n"
                    ).encode()
                )
                assert b"200 OK" in connection.recv(4096)
    finally:
        cleanup = request(Path("/etc/nginx"), "nginx-xhttp")
        cleanup["files"] = [
            {"path": str(path), "kind": "absent"}
            for path in (enabled, available, cert, key)
        ]
        tx.publish(cleanup)
        tx.apply(receipt, before_receipt, [])
        tx.apply(self_receipt, before_self_receipt, [])
        tx.restore_enabled("nginx.service", before_service)
        command(
            [
                "systemctl",
                "start" if before_service["active"] else "stop",
                "nginx.service",
            ]
        )
        hosts.write_bytes(hosts_bytes)
        os.chown(hosts, hosts_metadata.st_uid, hosts_metadata.st_gid)
        hosts.chmod(stat.S_IMODE(hosts_metadata.st_mode))
        if site.exists():
            shutil.rmtree(site)
        if site_existed:
            shutil.copytree(base / "prior-site", site, symlinks=True)
        shutil.rmtree(base)
