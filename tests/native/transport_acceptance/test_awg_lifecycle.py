"""Existing exact-pair lab plus real canonical retirement and restart handlers."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from native_common import ROOT

pytestmark = pytest.mark.native_runtime


def test_exact_pair_wire_warm_adoption_and_canonical_retirement(tmp_path):
    area = ROOT / "tests/integration/awg_source_candidate"
    owned_roots = [
        Path(raw)
        for raw in (
            "/lab",
            "/usr/local/lib/awg-candidate",
            "/var/lib/ripdpi/runtime-build-receipts",
            "/var/lib/ripdpi/runtime-build-staging",
        )
    ]
    assert all(
        not os.path.lexists(path) for path in owned_roots
    ), "isolated-AWG-lab-already-owned"
    sys.path.insert(0, str(ROOT / "ansible/roles/runtime-release/files"))
    Path("/lab").mkdir(mode=0o700)
    sources = []
    try:
        for name in ("sources.json", "acceptance.py"):
            shutil.copyfile(area / name, Path("/lab") / name)
        shutil.copyfile(
            ROOT / "ansible/roles/amneziawg/templates/awg-quick@.service.j2",
            "/lab/awg-quick@.service",
        )
        for pair in ("baseline", "candidate"):
            destination = Path("/opt") / pair
            assert not destination.exists(), "isolated-AWG-source-already-owned"
            destination.symlink_to(ROOT / ".cache/four-transport-sources" / pair)
            sources.append(destination)
        spec = importlib.util.spec_from_file_location(
            "four_awg_lab", area / "acceptance.py"
        )
        lab = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lab)
        # The lab's disconnected-root assertion applies to its own namespaces;
        # this source lane retains external access only to acquire pinned engines.
        # Join only the network namespace: ip-netns exec also isolates mounts,
        # which hides nested namespace handles from the real systemd manager.
        shutil.copyfile(
            ROOT / "ansible/roles/runtime-release/files/runtime_build_receipt.py",
            "/lab/runtime_build_receipt.py",
        )
        script = tmp_path / "acceptance"
        script.write_text(
            'import sys;sys.path.insert(0,sys.argv[1]);import acceptance;acceptance.unittest.main(module=acceptance,argv=["acceptance"],verbosity=2)'
        )
        namespace = "four-awg-root"
        lab.command("ip", "netns", "add", namespace)
        try:
            observed = subprocess.run(
                ["nsenter", "--net=/run/netns/" + namespace, sys.executable, str(script), "/lab"],
                env={
                    **os.environ,
                    "PYTHONPATH": str(ROOT / "ansible/roles/runtime-release/files"),
                },
                capture_output=True,
                text=True,
                timeout=900,
            )
            assert observed.returncode == 0, (
                "exact-AWG-pair-warm-acceptance-failed\n"
                + observed.stdout + observed.stderr
            )
        finally:
            lab.command("ip", "netns", "delete", namespace)
        # Exercise canonical handlers and two-to-one retirement with actual TUNs.
        shape = tuple(
            lab.PINS["wire_shapes"][0][key]
            for key in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4")
        )

        class QuickTunnel(lab.Tunnel):
            def pid(self, side=0):
                main = super().pid(side)
                if main:
                    return main
                group = lab.command(
                    "systemctl",
                    "show",
                    "-p",
                    "ControlGroup",
                    "--value",
                    self.units[side],
                )
                members = (
                    (Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs")
                    .read_text()
                    .split()
                )
                daemons = []
                for member in members:
                    try:
                        if Path(os.readlink(f"/proc/{member}/exe")).name.startswith(
                            "amneziawg-go"
                        ):
                            daemons.append(int(member))
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                assert len(daemons) == 1, "exact-quick-daemon-identity-unconfirmed"
                return daemons[0]

        tunnels = [QuickTunnel(i, "live", "baseline", shape) for i in (60, 61, 62)]
        for tunnel in tunnels:
            tunnel.units = ["awg-quick@" + name + ".service" for name in tunnel.names]
        record = Path("/var/lib/ripdpi/amneziawg/instances.json")
        assert not record.exists()
        prior_parent = record.parent.exists()
        record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        foreign_queue = tmp_path / "foreign-queue"
        foreign_queue.write_bytes(os.urandom(128))
        queue_before = (foreign_queue.stat().st_ino, foreign_queue.read_bytes())
        try:
            for tunnel in tunnels:
                tunnel.start()
                tunnel.probe()
            # Exercise the canonical oneshot/RemainAfterExit lifecycle: observe the
            # real surviving userspace daemon from the unit's cgroup, not MainPID=0.
            binaries = Path("/lab/bin")
            binaries.mkdir(mode=0o700)
            (binaries / "awg").symlink_to(lab.LIVE / "awg")
            for tunnel in tunnels[:2]:
                lab.command("systemctl", "stop", tunnel.units[0])
                config = tunnel.configs[0]
                config.write_text(
                    config.read_text().replace(
                        "[Interface]\n",
                        f"[Interface]\nAddress = 10.{tunnel.index}.0.1/24\n",
                    )
                )
                unit = (
                    ROOT / "ansible/roles/amneziawg/templates/awg-quick@.service.j2"
                ).read_text()
                unit = unit.replace("PartOf=awg-quick.target", "")
                unit = unit.replace(
                    "[Service]",
                    "[Service]\n"
                    + f"NetworkNamespacePath=/run/netns/{tunnel.names[0]}\n"
                    + f"Environment=PATH={binaries}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
                    + f"Environment=WG_QUICK_USERSPACE_IMPLEMENTATION={lab.LIVE / 'amneziawg-go'}",
                )
                unit = unit.replace(
                    "ExecStart=/usr/bin/awg-quick up %i",
                    f"ExecStart=/bin/bash {lab.LIVE / 'awg-quick'} up {config}",
                )
                unit = unit.replace(
                    "ExecStop=/usr/bin/awg-quick down %i",
                    f"ExecStop=/bin/bash {lab.LIVE / 'awg-quick'} down {config}",
                )
                unit = (
                    "\n".join(
                        row
                        for row in unit.splitlines()
                        if not row.startswith("ExecReload=")
                    )
                    + "\n"
                )
                (Path("/etc/systemd/system") / tunnel.units[0]).write_text(unit)
            lab.command("systemctl", "daemon-reload")
            for tunnel in tunnels[:2]:
                lab.command("systemctl", "start", tunnel.units[0])
                tunnel.initiator = 0
                tunnel.probe()
                assert (
                    lab.command(
                        "systemctl", "show", "-p", "MainPID", "--value", tunnel.units[0]
                    )
                    == "0"
                )
                assert tunnel.pid() > 0
            tasks = yaml.safe_load(
                (ROOT / "ansible/roles/amneziawg/tasks/enable.yml").read_text()
            )
            activate = next(
                row
                for row in tasks
                if row["name"]
                == "Apply changed AmneziaWG runtimes to current instances"
            )
            handlers = yaml.safe_load(
                (ROOT / "ansible/roles/amneziawg/handlers/main.yml").read_text()
            )

            def converge(changed, units=None):
                play = [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "_awg_instances": [
                                {"name": t.names[0]} for t in tunnels[:2]
                            ],
                            "amneziawg_role_enabled": True,
                            "runtime_build_results": {
                                "amneziawg-go": {"changed": changed}
                            },
                        },
                        "tasks": (
                            [
                                {
                                    "ansible.builtin.copy": {
                                        "dest": str(
                                            Path("/etc/systemd/system")
                                            / tunnel.units[0]
                                        ),
                                        "content": text,
                                        "mode": "0644",
                                    },
                                    "notify": ["Reload systemd", "Restart amneziawg"],
                                }
                                for tunnel, text in (units or [])
                            ]
                            + [activate, {"ansible.builtin.meta": "flush_handlers"}]
                        ),
                        "handlers": handlers,
                    }
                ]
                path = tmp_path / "activate.yml"
                path.write_text(yaml.safe_dump(play))
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert result.returncode == 0, (
                    "canonical-AWG-runtime-handler-refused\n"
                    + result.stdout + result.stderr
                )

            pids = [t.pid() for t in tunnels]
            published = lab.publisher.converge(lab.RECEIPTS, lab.descriptor("baseline"))
            converge(published["changed"])
            assert all(t.pid() != pid for t, pid in zip(tunnels[:2], pids))
            for tunnel in tunnels[:2]:
                tunnel.initiator = 0
                tunnel.probe()
            assert tunnels[2].pid() == pids[2]
            tunnels[2].probe()
            for pair in ("candidate",):
                published = lab.publisher.converge(lab.RECEIPTS, lab.descriptor(pair))
                converge(published["changed"])
                for tunnel in tunnels[:2]:
                    tunnel.initiator = 0
                    tunnel.probe()
                    assert lab.digest(f"/proc/{tunnel.pid()}/exe") == lab.digest(
                        f"/opt/{pair}/go/amneziawg-go"
                    )
            unit_changes = [
                (
                    tunnel,
                    (Path("/etc/systemd/system") / tunnel.units[0]).read_text()
                    + "\n[Service]\nProtectHostname=yes\n",
                )
                for tunnel in tunnels[:2]
            ]
            converge(False, unit_changes)
            for tunnel in tunnels[:2]:
                tunnel.initiator = 0
                tunnel.probe()
                assert (
                    lab.command(
                        "systemctl",
                        "show",
                        "-p",
                        "ProtectHostname",
                        "--value",
                        tunnel.units[0],
                    )
                    == "yes"
                )
                assert os.readlink(f"/proc/{tunnel.pid()}/ns/uts") != os.readlink(
                    "/proc/1/ns/uts"
                )
            pids = [t.pid() for t in tunnels]
            converge(
                lab.publisher.converge(lab.RECEIPTS, lab.descriptor("candidate"))[
                    "changed"
                ],
                unit_changes,
            )
            assert pids == [t.pid() for t in tunnels]
            retired = tunnels[1]
            for tunnel in tunnels[:2]:
                lab.command("systemctl", "enable", tunnel.units[0])
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "amneziawg_config_dir": "/lab",
                        "_awg_instances": [{"name": tunnels[0].names[0]}],
                        "_awg_previous": {"config_dir": "/lab"},
                        "_awg_obsolete": [retired.names[0]],
                    },
                    "tasks": [
                        {
                            "ansible.builtin.import_tasks": str(
                                ROOT
                                / "ansible/roles/amneziawg/tasks/retire-instances.yml"
                            )
                        }
                    ],
                }
            ]
            path = tmp_path / "retire.yml"
            path.write_text(yaml.safe_dump(play))
            for _ in range(2):
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={
                        **os.environ,
                        "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
                    },
                )
                assert result.returncode == 0, (
                    "canonical-AWG-retirement-refused\n"
                    + result.stdout + result.stderr
                )
                assert (
                    subprocess.run(
                        [
                            "ip",
                            "-n",
                            retired.names[0],
                            "link",
                            "show",
                            retired.names[0],
                        ],
                        capture_output=True,
                    ).returncode
                    != 0
                )
                with pytest.raises(AssertionError):
                    retired.probe()
                tunnels[0].probe()
                tunnels[2].probe()
                assert (
                    foreign_queue.stat().st_ino,
                    foreign_queue.read_bytes(),
                ) == queue_before
        finally:
            for tunnel in tunnels:
                for unit in tunnel.units:
                    subprocess.run(
                        ["systemctl", "disable", unit], capture_output=True, timeout=15
                    )
                tunnel.close()
            lab.command("systemctl", "daemon-reload")
            record.unlink(missing_ok=True)
            if not prior_parent:
                record.parent.rmdir()
    finally:
        for path in sources:
            path.unlink()
        for path in owned_roots:
            if path.exists():
                assert (
                    not path.is_symlink() and path.stat().st_uid == 0
                ), "AWG-cleanup-authority-changed"
                shutil.rmtree(path)
