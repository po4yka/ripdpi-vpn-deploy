"""Exact-pair traffic and complete canonical executable/unit/configuration lifecycle."""

import importlib.util
from contextlib import ExitStack
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from native_common import ROOT
from test_awg_activation_native import complete_publisher
from template_render import merge_render_vars, render_template

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
    lab = None
    original_source_root = None
    tunnels = []
    ownership = ExitStack()
    try:
        publisher = ownership.enter_context(complete_publisher(Path("/lab")))
        for name in ("sources.json", "acceptance.py", "corrected_build.py"):
            shutil.copyfile(area / name, Path("/lab") / name)
        correction = Path("/lab/awg-source-correction")
        correction.mkdir(mode=0o755)
        for name in ("awg_source_correction.py", "awg-source-correction.json", "awg-udp-checksum-zero.patch.json"):
            shutil.copyfile(ROOT / "ansible/roles/amneziawg/files" / name, correction / name)
        shutil.copyfile(
            ROOT / "ansible/roles/amneziawg/templates/awg-quick@.service.j2",
            "/lab/awg-quick@.service",
        )
        spec = importlib.util.spec_from_file_location(
            "four_awg_lab", area / "acceptance.py"
        )
        lab = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lab)
        original_source_root = lab.SOURCE_ROOT
        lab.SOURCE_ROOT = ROOT / ".cache/four-transport-sources"
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
            'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import acceptance;acceptance.SOURCE_ROOT=Path(sys.argv[2]);acceptance.unittest.main(module=acceptance,argv=["acceptance"],verbosity=2)'
        )
        namespace = "four-awg-root"
        lab.command("ip", "netns", "add", namespace)
        try:
            observed = subprocess.run(
                ["nsenter", "--net=/run/netns/" + namespace, sys.executable, str(script), "/lab", str(lab.SOURCE_ROOT)],
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
        # Publish the actual fixed executables, shared units, private configs and
        # membership through the production consumer while real clients stay up.
        shape = tuple(lab.PINS["wire_shapes"][0][key]
                      for key in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"))

        class QuickTunnel(lab.Tunnel):
            def pid(self, side=0):
                main = super().pid(side)
                if main:
                    return main
                group = lab.command("systemctl", "show", "-p", "ControlGroup", "--value", self.units[side])
                members = (Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs").read_text().split()
                daemons = []
                for member in members:
                    try:
                        if Path(os.readlink(f"/proc/{member}/exe")).name.startswith("amneziawg-go"):
                            daemons.append(int(member))
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                assert len(daemons) == 1, "exact-quick-daemon-identity-unconfirmed"
                return daemons[0]

        tunnels = [QuickTunnel(i, "live", "baseline", shape) for i in (60, 61, 62)]
        for tunnel in tunnels:
            tunnel.units = ["awg-quick@" + name + ".service" for name in tunnel.names]
        foreign_queue = tmp_path / "foreign-queue"
        foreign_queue.write_bytes(os.urandom(128))
        queue_before = (foreign_queue.stat().st_ino, foreign_queue.read_bytes())
        try:
            for tunnel in tunnels:
                tunnel.start()
                tunnel.probe()
            foreign_unit = Path("/etc/systemd/system") / tunnels[2].units[0]
            foreign_before = (foreign_unit.stat().st_ino, foreign_unit.read_bytes())
            foreign_pid = tunnels[2].pid()
            prior_pids = [t.pid() for t in tunnels[:2]]
            configs = {}
            for tunnel in tunnels[:2]:
                lab.command("systemctl", "stop", tunnel.units[0])
                (Path("/etc/systemd/system") / tunnel.units[0]).unlink()
                configs[tunnel.names[0]] = tunnel.configs[0].read_text().replace(
                    "[Interface]\n", f"[Interface]\nAddress = 10.{tunnel.index}.0.1/24\n")
            values = merge_render_vars(); values['amneziawg_config_dir'] = '/lab'
            shared = render_template(ROOT / "ansible/roles/amneziawg/templates/awg-quick@.service.j2", values)
            shared = shared.replace("[Service]", "[Service]\nNetworkNamespacePath=/run/netns/%i\n"
                                    "Environment=WG_QUICK_USERSPACE_IMPLEMENTATION=/usr/local/bin/amneziawg-go")

            def acquire(pair):
                selected = lab.source(pair)
                return publisher.acquire(str(selected / "go/amneziawg-go"), str(selected / "tools/src/wg"),
                                         str(selected / "tools/src/wg-quick/linux.bash"))

            def publish(acquired, selected=configs, unit=shared, absent=(), accepted=True):
                result = publisher.apply(publisher.request(acquired, selected, unit, absent=absent))
                assert (result.returncode == 0) == accepted, "complete-AWG-publication-outcome-refused\n" + result.stdout + result.stderr
                return json.loads(result.stdout) if accepted else None

            def probe_owned():
                for tunnel in tunnels[:2]:
                    tunnel.initiator = 0
                    tunnel.probe()
                assert tunnels[2].pid() == foreign_pid
                tunnels[2].probe()
                assert (foreign_unit.stat().st_ino, foreign_unit.read_bytes()) == foreign_before
                assert (foreign_queue.stat().st_ino, foreign_queue.read_bytes()) == queue_before

            baseline = acquire('baseline')
            # Rehearse legacy adoption with actual build publications and native
            # traffic. Membership alone never fabricates executable authority.
            for project, outputs in (('amneziawg-go', baseline[:1]), ('amneziawg-tools', baseline[1:])):
                descriptor = lab.descriptor('baseline')
                descriptor['name'] = project
                descriptor['steps'], descriptor['outputs'] = [], []
                for output in outputs:
                    name = Path(output['path']).name
                    staged = f'/var/lib/ripdpi/runtime-build-staging/{project}/{name}'
                    descriptor['steps'].append({'argv': ['/usr/bin/install', '-m', '0755', output['source'], staged],
                                                'chdir': '/lab', 'environment': {}, 'timeout_seconds': 30})
                    descriptor['outputs'].append({'name': name, 'staged_path': staged, 'path': output['path']})
                publication = lab.publisher.converge(lab.RECEIPTS, descriptor)
                assert publication['changed'] is True
            legacy = publisher.request(baseline, configs, shared)
            for item in legacy['candidates']:
                if 'data' in item:
                    path = Path(item['path'])
                    path.write_bytes(base64.b64decode(item['data'])); path.chmod(item['mode'])
            lab.command('systemctl', 'daemon-reload')
            for tunnel in tunnels[:2]:
                lab.command('systemctl', 'start', tunnel.units[0])
            probe_owned()
            adoption = subprocess.run([sys.executable, '-Es', str(publisher.helper), 'recover'],
                                      input=json.dumps({'check': False}), env=publisher.environment,
                                      capture_output=True, text=True, timeout=60)
            assert adoption.returncode == 0, 'canonical-legacy-AWG-adoption-refused\n' + adoption.stdout + adoption.stderr
            publish(baseline)
            assert all(t.pid() != old for t, old in zip(tunnels[:2], prior_pids))
            assert all(lab.command("systemctl", "show", "-p", "MainPID", "--value", t.units[0]) == "0" for t in tunnels[:2])
            probe_owned()
            candidate = acquire("candidate")
            publish(candidate)
            for tunnel in tunnels[:2]:
                assert lab.digest(f"/proc/{tunnel.pid()}/exe") == lab.digest(lab.source("candidate") / "go/amneziawg-go")
            probe_owned()
            retained_paths = [Path(item["path"]) for item in candidate] + [Path("/etc/systemd/system/awg-quick@.service"),
                              Path("/etc/systemd/system/awg-quick.target"), publisher.record, *[Path('/lab') / (name+'.conf') for name in configs]]
            before = {str(path): (path.stat().st_ino, path.stat().st_mode, path.read_bytes()) for path in retained_paths}
            rejected = Path('/lab/rejected-amneziawg-go')
            rejected.write_text('#!/bin/sh\nexit 71\n'); rejected.chmod(0o755)
            broken = publisher.acquire(rejected, str(lab.source('candidate') / 'tools/src/wg'),
                                       str(lab.source('candidate') / 'tools/src/wg-quick/linux.bash'))
            publish(broken, accepted=False)
            assert {str(path): (path.stat().st_ino, path.stat().st_mode, path.read_bytes()) for path in retained_paths} == before
            probe_owned()
            publish(candidate, unit=shared+'\n[Service]\nExecStartPre=/bin/false\n', accepted=False)
            assert {str(path): (path.stat().st_ino, path.stat().st_mode, path.read_bytes()) for path in retained_paths} == before
            probe_owned()
            hardened = shared + '\n[Service]\nProtectHostname=yes\n'
            publish(candidate, unit=hardened)
            probe_owned()
            for tunnel in tunnels[:2]:
                assert lab.command('systemctl', 'show', '-p', 'ProtectHostname', '--value', tunnel.units[0]) == 'yes'
                assert os.readlink(f'/proc/{tunnel.pid()}/ns/uts') != os.readlink('/proc/1/ns/uts')
            pids = [t.pid() for t in tunnels]
            result = publish(candidate, unit=hardened)
            assert result['changed'] is False and pids == [t.pid() for t in tunnels]
            retired = tunnels[1]
            kept = {tunnels[0].names[0]: configs[tunnels[0].names[0]]}
            absent = [retired.configs[0]]
            for attempt in range(2):
                result = publish(candidate, selected=kept, unit=hardened, absent=absent if attempt == 0 else ())
                if attempt:
                    assert result['changed'] is False
                assert subprocess.run(['ip', '-n', retired.names[0], 'link', 'show', retired.names[0]], capture_output=True).returncode != 0
                assert not retired.configs[0].exists()
                with pytest.raises(AssertionError):
                    retired.probe()
                tunnels[0].probe()
                assert tunnels[2].pid() == foreign_pid
                tunnels[2].probe()
                assert (foreign_unit.stat().st_ino, foreign_unit.read_bytes()) == foreign_before
                assert (foreign_queue.stat().st_ino, foreign_queue.read_bytes()) == queue_before
        finally:
            for tunnel in tunnels:
                for unit in tunnel.units:
                    subprocess.run(["systemctl", "disable", unit], capture_output=True, timeout=15)
                tunnel.close()
            lab.command("systemctl", "daemon-reload")
    finally:
        if original_source_root is not None:
            lab.SOURCE_ROOT = original_source_root
        ownership.close()
        for tunnel in tunnels:
            for unit in tunnel.units:
                subprocess.run(['systemctl', 'reset-failed', unit], capture_output=True, timeout=15)
        for path in owned_roots:
            if path.exists():
                assert (
                    not path.is_symlink() and path.stat().st_uid == 0
                ), "AWG-cleanup-authority-changed"
                shutil.rmtree(path)
