"""Real helper/filesystem transition between immutable archive and source modes.

Fixture executable bytes prove publication/receipt isolation; no Xray protocol
or upstream source compilation is claimed by this test.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import shutil
import subprocess
import sys
import tempfile

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[2]


def helper(name):
    path = ROOT / "ansible/roles/runtime-release/files" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_source_archive_preserves_exact_receipt_bytes_and_current():
    directory = Path(tempfile.mkdtemp(prefix=".p2-xray-mode-", dir=Path.home()))
    directory.chmod(0o700)
    try:
        tasks = yaml.safe_load(
            (ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text()
        )
        derive = next(
            t
            for t in tasks
            if t["name"] == "Derive mode-bound immutable Xray release identity"
        )
        identity_expr = derive["ansible.builtin.set_fact"][
            "_xray_runtime_release_identity"
        ]
        environment = jinja2.Environment()
        environment.filters["bool"] = bool
        pin = {"version": "vfixture", "source_commit": "a" * 40}
        archive_name = environment.from_string(identity_expr).render(
            xray=pin, xray_runtime_build_from_source=False
        )
        source_name = environment.from_string(identity_expr).render(
            xray=pin, xray_runtime_build_from_source=True
        )
        assert (
            archive_name == "vfixture-archive"
            and source_name == "vfixture-source-" + "a" * 40
        )
        install = directory / "install"
        archive = install / "releases" / archive_name
        source = install / "releases" / source_name
        public = directory / "bin/xray"
        archive.mkdir(parents=True, mode=0o755)
        source.mkdir(mode=0o755)
        public.parent.mkdir(mode=0o755)
        # Ambient umask must not fabricate an invalid public directory contract.
        public.parent.chmod(0o755)
        archive_binary = archive / "xray"
        source_binary = source / "xray"
        archive_binary.write_bytes(b"#!/bin/sh\nprintf archive\\n\n")
        archive_binary.chmod(0o755)
        for path in (install, install / "releases", archive, source):
            path.chmod(0o755)
        digest = hashlib.sha256(archive_binary.read_bytes()).hexdigest()
        activate = helper("runtime_release_activate")
        arguments = {
            "artifact_sha256": digest,
            "candidate_sha256": digest,
            "artifact_type": "archive",
            "arch_key": "arm64",
            "arch_slug": "arm64-v8a",
            "owner": pwd.getpwuid(os.getuid()).pw_name,
            "group": grp.getgrgid(os.getgid()).gr_name,
        }
        activate.activate(
            install, archive_name, "xray", public, check=False, **arguments
        )
        receipt = archive / ".runtime-release.json"
        before = (
            receipt.read_bytes(),
            archive_binary.read_bytes(),
            archive_binary.stat().st_ino,
        )
        build = helper("runtime_build_receipt")
        seed = directory / "source-input"
        seed.write_bytes(b"#!/bin/sh\nprintf source\\n\n")
        seed.chmod(0o755)
        source_digest = hashlib.sha256(seed.read_bytes()).hexdigest()
        receipt_root = directory / "receipts"
        receipt_root.mkdir(mode=0o755)
        stage = directory / "runtime-build-staging/xray-core/xray"
        descriptor = {
            "schema_version": 1,
            "name": "xray-core",
            "source": {
                "repository": "fixture://xray-mode",
                "version": pin["version"],
                "commit": pin["source_commit"],
            },
            "steps": [
                {
                    "argv": ["/bin/cp", str(seed), str(stage)],
                    "chdir": str(directory),
                    "environment": {},
                    "timeout_seconds": 10,
                }
            ],
            "outputs": [
                {
                    "name": "installed",
                    "staged_path": str(stage),
                    "path": str(source_binary),
                    "expected_sha256": source_digest,
                }
            ],
        }
        assert build.converge(receipt_root, descriptor)["changed"]
        assert not build.converge(receipt_root, descriptor)["changed"]
        publish = [
            task
            for task in tasks
            if task["name"] == "Point current Xray runtime at pinned release"
        ]
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "xray_install_dir": str(install),
                    "_xray_runtime_release_identity": source_name,
                    "xray_runtime_build_from_source": True,
                },
                "tasks": publish,
            }
        ]
        path = directory / "publish.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert public.resolve() == source_binary
        assert public.read_bytes() == seed.read_bytes()
        assert (
            receipt.read_bytes(),
            archive_binary.read_bytes(),
            archive_binary.stat().st_ino,
        ) == before
        assert activate.activate(
            install, archive_name, "xray", public, check=False, **arguments
        )["changed"]
        assert public.resolve() == archive_binary and public.read_bytes() == before[1]
        assert (
            receipt.read_bytes(),
            archive_binary.read_bytes(),
            archive_binary.stat().st_ino,
        ) == before
        assert not activate.activate(
            install, archive_name, "xray", public, check=False, **arguments
        )["changed"]
    finally:
        shutil.rmtree(directory)
