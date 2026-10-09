"""Exercise real per-node key/image creation and strict partial-apply cleanup."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

seed = load("ci_ssh_seed", "scripts/ci-ssh-seed.py")
guest = load("bootstrap_ssh_seed", "terraform/shared/bootstrap-ssh-seed.py")
UUID = "11223344-5566-4788-99aa-bbccddeeff00"

@pytest.fixture
def material(tmp_path):
    mke2fs = "/opt/homebrew/opt/e2fsprogs/sbin/mke2fs" if sys.platform == "darwin" else "mke2fs"
    data = seed.create(tmp_path.resolve() / "seed", "ci-staging-unit", "vpn-ci-staging-unit", 22, mke2fs)
    return data, Path(data["image_path"]).parent / "manifest.json"

def test_real_seed_image_and_guest_identity(material, tmp_path):
    data, manifest = material
    debugfs = "/opt/homebrew/opt/e2fsprogs/sbin/debugfs" if sys.platform == "darwin" else "debugfs"
    source = tmp_path / "extract"
    source.mkdir(mode=0o700)
    key = source / "ssh_host_ed25519_key"
    subprocess.run([debugfs, "-R", f"dump /ssh_host_ed25519_key {key}", data["image_path"]], capture_output=True, check=True)
    key.chmod(0o600)
    assert guest.matches(key, data["host_public_key_sha256"])
    destination = tmp_path / "ssh"
    guest.install(source, destination, data["host_public_key_sha256"])
    target = destination / key.name
    assert guest.matches(target, data["host_public_key_sha256"])
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    inode = target.stat().st_ino
    guest.install(source, destination, data["host_public_key_sha256"])
    assert target.stat().st_ino == inode
    before = target.read_bytes()
    with pytest.raises(ValueError, match="mismatch"):
        guest.install(source, destination, "0" * 64)
    assert target.read_bytes() == before
    assert seed.validate(manifest) == data
    assert b"PRIVATE KEY" not in manifest.read_bytes()
    assert b"PRIVATE KEY" not in Path(data["known_hosts_path"]).read_bytes()
    seed.cleanup_local(manifest)
    assert not manifest.parent.exists()

def test_per_node_identity_is_unique(material, tmp_path):
    data, _ = material
    tool = "/opt/homebrew/opt/e2fsprogs/sbin/mke2fs" if sys.platform == "darwin" else "mke2fs"
    other = seed.create(tmp_path.resolve() / "second", "ci-staging-unit", "second", 2222, tool)
    assert data["host_public_key_sha256"] != other["host_public_key_sha256"]
    assert Path(other["known_hosts_path"]).read_text().startswith("[second]:2222 ssh-ed25519 ")

@pytest.mark.parametrize("change", ["image", "known-hosts", "manifest", "foreign"])
def test_refuses_mutated_artifacts(material, change):
    data, manifest = material
    if change == "image":
        with Path(data["image_path"]).open("r+b") as handle: handle.write(b"altered")
    elif change == "known-hosts": Path(data["known_hosts_path"]).write_text("wrong\n")
    elif change == "manifest":
        changed = dict(data, environment="prod")
        manifest.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n")
    else: (manifest.parent / "foreign").touch()
    with pytest.raises(seed.Refusal):
        seed.cleanup_local(manifest) if change == "foreign" else seed.validate(manifest)


def partial_state(data):
    return {"version": 4, "resources": [{"mode": "managed", "type": "upcloud_storage", "name": "ci_ssh_seed", "instances": [{"index_key": 0, "attributes": {
        "id": UUID, "encrypt": True, "title": data["host_alias"] + "-ssh-seed",
        "labels": {"managed_by": "terraform", "env": data["environment"], "seed_id": data["filesystem_uuid"]},
        "import": [{"source": "direct_upload", "source_hash": data["image_sha256"], "source_location": data["image_path"]}]
    }}]}]}

@pytest.mark.parametrize("condition", ["valid", "attached", "foreign", "unknown", "still-present"])
def test_partial_cleanup_exact_provider_binding(material, tmp_path, condition):
    data, manifest = material
    state = tmp_path.resolve() / "state.json"
    state.write_text(json.dumps(partial_state(data)))
    state.chmod(0o600)
    calls = []
    removed = False
    def request(path, *, method="GET"):
        nonlocal removed
        calls.append((path, method))
        if path == "/1.3/account": return 200, {"account": {"username": "unit-account"}}
        assert path == "/1.3/storage/" + UUID
        if method == "DELETE":
            removed = condition != "still-present"
            return 204, {}
        if removed: return 404, {"error": {"error_code": "STORAGE_NOT_FOUND"}}
        if condition == "unknown": return 500, {}
        return 200, {"storage": {"uuid": UUID, "title": data["host_alias"] + "-ssh-seed", "encrypted": "yes", "servers": {"server": ["foreign"] if condition == "attached" else []}, "labels": [
            {"key": "managed_by", "value": "terraform"}, {"key": "env", "value": "prod" if condition == "foreign" else data["environment"]}, {"key": "seed_id", "value": data["filesystem_uuid"]}]}}
    if condition == "valid":
        assert seed.cleanup_seed(manifest, state, data["environment"], request)["status"] == "seed-storage-absent"
    else:
        with pytest.raises(seed.Refusal): seed.cleanup_seed(manifest, state, data["environment"], request)
        if condition != "still-present": assert all(method != "DELETE" for _, method in calls)
    assert manifest.exists()

@pytest.mark.parametrize("foreign", ["upcloud_server", "upcloud_firewall_rules", "unexpected"])
def test_partial_cleanup_refuses_other_resources_before_api(material, tmp_path, foreign):
    data, manifest = material
    value = partial_state(data)
    value["resources"].append({"mode": "managed", "type": foreign, "name": "vpn", "instances": []})
    state = tmp_path.resolve() / "state.json"
    state.write_text(json.dumps(value)); state.chmod(0o600)
    with pytest.raises(seed.Refusal, match="full-manifest"):
        seed.cleanup_seed(manifest, state, data["environment"], lambda _: pytest.fail("API called"))


@pytest.mark.native_runtime
def test_ci_seed_real_guest_mount_digest_binding_and_unmount(material, tmp_path):
    """Real block-device mount in a private namespace; never replace runner keys."""
    import os
    import textwrap
    assert sys.platform == "linux" and os.geteuid() == 0
    data, _ = material
    ssh = tmp_path / "isolated-ssh"
    ssh.mkdir(mode=0o700)
    script = textwrap.dedent(r'''
        import hashlib, json, os
        from pathlib import Path
        import re, subprocess, sys
        image, filesystem_uuid, digest, ssh, helper = sys.argv[1:]
        def command(argv):
            return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        command(["mount", "--bind", ssh, "/etc/ssh"])
        before = Path("/proc/self/mountinfo").read_text()
        original_digest = hashlib.sha256(Path(image).read_bytes()).hexdigest()
        loop = command(["losetup", "--find", "--show", image])
        assert re.fullmatch(r"/dev/loop[0-9]+", loop)
        by_uuid = Path("/dev/disk/by-uuid") / filesystem_uuid
        made_link = False
        try:
            by_uuid.parent.mkdir(parents=True, exist_ok=True)
            try:
                by_uuid.symlink_to(loop)
                made_link = True
            except FileExistsError:
                assert by_uuid.stat().st_rdev == Path(loop).stat().st_rdev
            invocation = [sys.executable, "-I", "-B", helper, "--filesystem-uuid", filesystem_uuid, "--public-key-sha256"]
            refused = subprocess.run([*invocation, "0" * 64], capture_output=True, text=True, timeout=30)
            assert refused.returncode == 1
            assert not Path("/etc/ssh/ssh_host_ed25519_key").exists()
            assert Path("/proc/self/mountinfo").read_text() == before
            command([*invocation, digest])
            key = Path("/etc/ssh/ssh_host_ed25519_key")
            assert key.is_file() and key.stat().st_mode & 0o777 == 0o600
            import base64
            public = command(["ssh-keygen", "-y", "-f", str(key)])
            assert hashlib.sha256(base64.b64decode(public.split()[1])).hexdigest() == digest
            assert hashlib.sha256(Path(image).read_bytes()).hexdigest() == original_digest
            assert Path("/proc/self/mountinfo").read_text() == before
        finally:
            if made_link and by_uuid.is_symlink() and os.readlink(by_uuid) == loop:
                by_uuid.unlink()
            command(["losetup", "--detach", loop])
            command(["umount", "/etc/ssh"])
    ''')
    result = subprocess.run(["unshare", "--mount", "--propagation", "private", sys.executable, "-c", script,
                             data["image_path"], data["filesystem_uuid"], data["host_public_key_sha256"], str(ssh),
                             str(ROOT / "terraform/shared/bootstrap-ssh-seed.py")], capture_output=True, text=True, timeout=100)
    assert result.returncode == 0, result.stdout + result.stderr
    assert guest.matches(ssh / "ssh_host_ed25519_key", data["host_public_key_sha256"])


@pytest.mark.parametrize("seed_status", [0, 1])
def test_actual_cloud_init_chain_cannot_bootstrap_after_seed_refusal(tmp_path, seed_status):
    import re
    import yaml
    main = (ROOT / "terraform/providers/upcloud/main.tf").read_text()
    line = next(line for line in main.splitlines() if line.strip().startswith("runcmd ="))
    template_command = line.split('["sh", "-c", "', 1)[1].rsplit('"]]', 1)[0]
    base = yaml.safe_load((ROOT / "terraform/shared/cloud-init.yaml.tftpl").read_text())["runcmd"][0][2]
    marker = tmp_path / "bootstrap.done"
    activation = tmp_path / "activation"
    base = base.replace("/var/lib/cloud-init-vpn-bootstrap.done", str(marker))
    base = base.replace("install -d -m 0755 /run/sshd", "true")
    base = base.replace("/usr/bin/python3", "true").replace("/usr/sbin/sshd -t", "true")
    base = base.replace("systemctl enable --now ssh", f"touch {activation}")
    base = base.replace("systemctl reload ssh", "true")
    command = template_command.replace("${local.base_cloud_config.runcmd[0][2]}", base)
    command = re.sub(r"/usr/bin/python3 -I -B /usr/local/libexec/vpn-bootstrap-ssh-seed.py --filesystem-uuid [^ ]+ --public-key-sha256 [^ ]+",
                     "true" if seed_status == 0 else "false", command)
    result = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
    assert result.returncode == seed_status, result.stderr
    assert marker.exists() is (seed_status == 0)
    assert activation.exists() is (seed_status == 0)
