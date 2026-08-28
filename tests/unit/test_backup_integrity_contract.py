"""Backup script must prove integrity and snapshot freshness."""

from pathlib import Path
import importlib.util
import json
import os
import stat

import pytest


def test_backup_checks_restic_and_remote_contents():
    script = (Path(__file__).resolve().parents[2] / "ansible/roles/backup/templates/vpn-backup.sh.j2").read_text()
    assert 'restic -r "$REPO" check' in script
    assert 'snapshots --tag vpn-stack --latest 1 --json' in script
    assert "dt.timedelta(hours={{ backup_snapshot_max_age_hours | int }})" in script
    assert "rclone check" in script
    assert "rclone size" not in script


@pytest.fixture
def configure(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/backup-configure.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("backup_configure", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "OWNER_UID", os.getuid())
    module.observed_quiescent = module.quiescent
    monkeypatch.setattr(module, "quiescent", lambda: None)
    if hasattr(module, "repository_decryptable"):
        module.observed_repository_decryptable = module.repository_decryptable
        monkeypatch.setattr(module, "repository_decryptable", lambda: None)
    for directory in ("run", "etc/restic", "etc/systemd/system", "usr/bin",
                      "usr/local/sbin", "var/backups/vpn-restic", "var/lib/vpn-backup"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, data, mode in (
        ("etc/restic/password", b"test-password-long-enough", 0o600),
        ("var/backups/vpn-restic/config", b"{}", 0o600),
        ("usr/bin/restic", b"#!/bin/sh\n", 0o755),
        *( (f"etc/systemd/system/{unit}", b"[Unit]\n", 0o644) for unit in module.UNITS),
    ):
        target = tmp_path / name
        target.write_bytes(data)
        target.chmod(mode)
    return module


def staged(configure):
    token = configure.claim()
    stage = configure.path("run/vpn-backup-configure.lock/stage")
    for relative in configure.FILES:
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_text("[offsite]\ntype = local\n" if relative.endswith("rclone.conf")
                          else "#!/bin/bash\nexit 0\n")
        target.chmod(0o600)
    (stage / "password").write_bytes(b"test-password-long-enough")
    (stage / "password").chmod(0o600)
    (stage / "settings.json").write_text(json.dumps({
        "enabled": True, "rclone_remote": "offsite", "rclone_path": "bucket/prod/generation",
        "transfers": 1, "bwlimit": "off", "restic_repo_dir": "/var/backups/vpn-restic",
    }))
    (stage / "settings.json").chmod(0o600)
    return token


def old_files(module):
    old = {}
    for index, relative in enumerate(module.FILES):
        target = module.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(f"old-{index}\n".encode())
        target.chmod(0o600 if index == 0 else 0o700)
        old[relative] = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode))
    return old


def assert_old(module, old):
    for relative, expected in old.items():
        target = module.path(relative)
        assert (target.read_bytes(), stat.S_IMODE(target.stat().st_mode)) == expected


def test_configure_real_files_positive_and_idempotent(configure):
    token = staged(configure)
    configure.validate(token)
    assert configure.publish(token) is True
    assert configure.path("etc/rclone/rclone.conf").stat().st_mode & 0o777 == 0o600
    assert configure.path("usr/local/sbin/vpn-backup.sh").stat().st_mode & 0o777 == 0o750
    assert configure.path("etc/restic/password").read_bytes() == b"test-password-long-enough"
    configure.release(token)
    token = staged(configure)
    assert configure.publish(token) is False
    configure.release(token)
    assert not configure.path("run/vpn-backup-configure.lock").exists()


@pytest.mark.parametrize("failure", [1, 2, 3, "postcheck"])
def test_configure_rolls_back_every_publish_and_postcheck(configure, monkeypatch, failure):
    old = old_files(configure)
    token = staged(configure)
    publish = configure.atomic_write
    count = 0
    def write(target, data, mode):
        nonlocal count
        if target in [configure.path(name) for name in configure.FILES]:
            count += 1
            if count == failure:
                raise OSError("synthetic private failure")
        return publish(target, data, mode)
    monkeypatch.setattr(configure, "atomic_write", write)
    calls = 0
    def guard():
        nonlocal calls
        calls += 1
        if failure == "postcheck" and calls == 2:
            raise configure.ConfigError("not-quiescent")
    monkeypatch.setattr(configure, "quiescent", guard)
    with pytest.raises(configure.ConfigError, match="configuration-rolled-back"):
        configure.publish(token)
    assert_old(configure, old)
    configure.release(token)


def test_configure_rollback_restores_absence(configure, monkeypatch):
    token = staged(configure)
    original = configure.atomic_write
    def write(target, data, mode):
        if target == configure.path(configure.FILES[1]):
            raise OSError("write refused")
        original(target, data, mode)
    monkeypatch.setattr(configure, "atomic_write", write)
    with pytest.raises(configure.ConfigError, match="configuration-rolled-back"):
        configure.publish(token)
    assert all(not configure.path(name).exists() for name in configure.FILES)
    configure.release(token)


def test_configure_failed_rollback_retains_private_recovery_and_lock(configure, monkeypatch):
    old_files(configure)
    token = staged(configure)
    original = configure.atomic_write
    def write(target, data, mode):
        if target == configure.path(configure.FILES[1]):
            raise OSError("persistent filesystem failure")
        original(target, data, mode)
    monkeypatch.setattr(configure, "atomic_write", write)
    with pytest.raises(configure.ConfigError, match="rollback-incomplete-keep-timers-stopped"):
        configure.publish(token)
    with pytest.raises(configure.ConfigError, match="rollback-incomplete-keep-timers-stopped"):
        configure.release(token)
    recovery = configure.path(f"var/lib/vpn-backup/configure-recovery/{token}")
    assert recovery.is_dir() and stat.S_IMODE(recovery.stat().st_mode) == 0o700
    assert configure.path("run/vpn-backup-configure.lock").is_dir()


def test_configure_existing_lock_is_never_removed(configure):
    token = configure.claim()
    with pytest.raises(configure.ConfigError, match="configuration-locked"):
        configure.claim()
    with pytest.raises(configure.ConfigError, match="lock-not-owned"):
        configure.release("0" * 32)
    assert configure.path("run/vpn-backup-configure.lock/token").read_text() == token
    configure.release(token)


@pytest.mark.parametrize("fault", ["password", "script", "symlink", "remote", "path", "permissions"])
def test_configure_validation_rejects_before_live_writes(configure, fault):
    old = old_files(configure)
    token = staged(configure)
    stage = configure.path("run/vpn-backup-configure.lock/stage")
    if fault == "password":
        (stage / "password").write_text("wrong-password")
    elif fault == "script":
        (stage / configure.FILES[1]).write_text("if ; then\n")
    elif fault == "symlink":
        target = configure.path(configure.FILES[0])
        target.unlink()
        target.symlink_to(configure.path("etc/restic/password"))
    elif fault == "permissions":
        configure.path("etc/restic/password").chmod(0o644)
    else:
        settings = json.loads((stage / "settings.json").read_text())
        settings["rclone_remote" if fault == "remote" else "rclone_path"] = '$(touch /bad)'
        (stage / "settings.json").write_text(json.dumps(settings))
    with pytest.raises(configure.ConfigError):
        configure.validate(token)
    if fault not in ("symlink",):
        assert_old(configure, old)
    configure.release(token)


def test_configure_playbook_cannot_import_full_stack_or_service_handlers():
    import yaml
    root = Path(__file__).resolve().parents[2]
    play = yaml.safe_load((root / "ansible/playbooks/backup-configure.yml").read_text())[0]
    text = json.dumps(play)
    for forbidden in ("site.yml", "systemd_service", "notify", "flush_handlers", "baseline", "firewall"):
        assert forbidden not in text
    role = root / "ansible/roles/backup/tasks"
    for filename in ("configure-only.yml", "configuration.yml", "install-rclone.yml"):
        source = (role / filename).read_text()
        for forbidden in ("ansible.builtin.systemd_service", "notify:", "flush_handlers", "tasks_from: main"):
            assert forbidden not in source
    transaction = (role / "configure-only.yml").read_text()
    assert "include_tasks: configuration.yml" in transaction
    assert "include_tasks: install-rclone.yml" in transaction
    assert " always:" in transaction
    make = (root / "Makefile").read_text().split("backup-configure:", 1)[1].split("\n\n", 1)[0]
    assert "require-clean-source" not in make and "require-inventory" not in make
    helper = (root / "scripts/backup-configure.py").read_text()
    assert "fleet_inspection.select_hosts(Path(inventory), [alias])[0]" in helper
    assert "environment.update(clean_source(root, environment))" in helper
    assert "validate-ansible-extra-vars.py" in helper
    assert "backup-configure.py" in make
    assert '"$(ANSIBLE_LIMIT)"' not in make and '"$(SECRETS_FILE)"' not in make
    assert "--tags" not in make and "source-drift" not in make


@pytest.mark.parametrize("fault", [None, "active", "activating", "job", "missing", "failed", "unloaded", "enabled-timer"])
def test_configure_observes_exact_unit_states_without_mutations(configure, monkeypatch, fault):
    import subprocess
    blocks = []
    for index, unit in enumerate(configure.UNITS):
        fields = {"Id": unit, "LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead", "Job": "",
                  "UnitFileState": "disabled" if unit.endswith(".timer") else "static"}
        if index == 2 and fault == "enabled-timer":
            fields["UnitFileState"] = "enabled"
        if index == 0:
            if fault in ("active", "activating", "failed"):
                fields["ActiveState"] = fault
            elif fault == "job":
                fields["Job"] = "12"
            elif fault == "unloaded":
                fields["LoadState"] = "not-found"
            elif fault == "missing":
                continue
        blocks.append("\n".join(f"{key}={value}" for key, value in fields.items()))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "\n\n".join(blocks), "")
    monkeypatch.setattr(configure.subprocess, "run", run)
    if fault:
        with pytest.raises(configure.ConfigError):
            configure.observed_quiescent()
    else:
        configure.observed_quiescent()
    assert len(calls) == 1 and calls[0][:2] == ["systemctl", "show"]
    assert tuple(calls[0][-4:]) == configure.UNITS


def test_active_execution_refuses_before_claiming_or_writing(configure, monkeypatch):
    def active():
        raise configure.ConfigError("backup-not-quiescent")
    monkeypatch.setattr(configure, "quiescent", active)
    with pytest.raises(configure.ConfigError, match="backup-not-quiescent"):
        configure.claim()
    assert not configure.path("run/vpn-backup-configure.lock").exists()


@pytest.mark.parametrize("alias", ["node-one", "vpn-test.example.com", "", "vpn", "all", "node-*", "node-one,node-two", "!node-one", "unknown"])
def test_configuration_requires_one_exact_real_inventory_host(configure, tmp_path, monkeypatch, alias):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    key = tmp_path / "identity"
    key.write_text("synthetic identity")
    key.chmod(0o600)
    inventory = tmp_path / "inventory.ini"
    name = alias if alias in ("node-one", "vpn-test.example.com") else "node-one"
    inventory.write_text(f"[vpn]\n{name} ansible_host=192.0.2.1 ansible_user=admin ansible_port=22 ansible_ssh_private_key_file={key}\n")
    inventory.chmod(0o600)
    if alias in ("node-one", "vpn-test.example.com"):
        configure.select_target(str(inventory), alias)
    else:
        import fleet_inspection
        with pytest.raises((configure.ConfigError, fleet_inspection.InspectionError)):
            configure.select_target(str(inventory), alias)


def test_rclone_package_slice_never_refreshes_or_upgrades():
    import yaml
    root = Path(__file__).resolve().parents[2]
    tasks = yaml.safe_load((root / "ansible/roles/backup/tasks/install-rclone.yml").read_text())
    assert len(tasks) == 1
    assert tasks[0]["ansible.builtin.apt"] == {"name": "rclone", "state": "present", "update_cache": False}
    assert "notify" not in tasks[0]


def test_canonical_temporary_secret_path_is_pinned_before_validators(configure, monkeypatch):
    import tempfile
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    with tempfile.NamedTemporaryFile() as materialized:
        os.fchmod(materialized.fileno(), 0o600)
        materialized.write(b"synthetic canonical materialization")
        materialized.flush()
        assert configure.materialized_bytes(materialized.name) == b"synthetic canonical materialization"


def test_secret_intake_rejects_final_symlink_and_public_file(configure, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    real = tmp_path / "secrets.yaml"
    real.write_bytes(b"synthetic")
    real.chmod(0o600)
    link = tmp_path / "alias.yaml"
    link.symlink_to(real)
    with pytest.raises(configure.ConfigError):
        configure.materialized_bytes(str(link))
    real.chmod(0o644)
    with pytest.raises(configure.ConfigError):
        configure.materialized_bytes(str(real))


@pytest.mark.parametrize("alias", ['node"; touch /tmp/never-backup-test; #', '$(touch /tmp/never-backup-test)', 'node\nother'])
def test_unsafe_controller_alias_never_reaches_subprocess(configure, monkeypatch, alias):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    calls = []
    monkeypatch.setattr(configure.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(configure.ConfigError, match="exact-single-host-required"):
        configure.controller("unused", alias, "unused")
    assert not calls


@pytest.mark.parametrize("payload", ['node"; touch SENTINEL; #', '$(touch SENTINEL)', 'node\nother'])
def test_make_configuration_recipe_never_evaluates_untrusted_arguments(tmp_path, payload):
    import subprocess
    import shutil
    root = Path(__file__).resolve().parents[2]
    recipe = root.joinpath("Makefile").read_text().split("# Capture caller data", 1)[1].split("\n\ndeploy-canary:", 1)[0]
    recipe = ("# Capture caller data" + recipe).replace(
        "backup-configure: require-clean-source", "backup-configure:")
    (tmp_path / "Makefile").write_text(recipe)
    (tmp_path / "scripts").mkdir()
    for name in ("backup-configure.py", "fleet_inspection.py"):
        shutil.copyfile(root / "scripts" / name, tmp_path / "scripts" / name)
    result = subprocess.run(["make", "backup-configure", "ANSIBLE_LIMIT=" + payload,
                             'SECRETS_FILE="; touch SENTINEL; #'], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "exact-single-host-required" in result.stderr
    assert not (tmp_path / "SENTINEL").exists()


@pytest.mark.parametrize("field", ["ANSIBLE_LIMIT", "SECRETS_FILE", "ANSIBLE_EXTRA_VARS_FILE"])
def test_make_data_fields_do_not_execute_make_functions_or_implicit_exports(tmp_path, field):
    import subprocess
    import shutil
    root = Path(__file__).resolve().parents[2]
    recipe = root.joinpath("Makefile").read_text().split("# Capture caller data", 1)[1].split("\n\ndeploy-canary:", 1)[0]
    recipe = ("# Capture caller data" + recipe).replace(
        "backup-configure: require-clean-source", "backup-configure:")
    (tmp_path / "Makefile").write_text(recipe)
    (tmp_path / "scripts").mkdir()
    for name in ("backup-configure.py", "fleet_inspection.py"):
        shutil.copyfile(root / "scripts" / name, tmp_path / "scripts" / name)
    arguments = {"ANSIBLE_LIMIT": "!invalid", "SECRETS_FILE": "missing", "ANSIBLE_EXTRA_VARS_FILE": ""}
    arguments[field] = "$(shell touch SENTINEL)"
    result = subprocess.run(["make", "backup-configure", *(f"{key}={value}" for key, value in arguments.items())],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "exact-single-host-required" in result.stderr
    assert not (tmp_path / "SENTINEL").exists()


def test_make_rejects_debug_before_any_ansible_command(tmp_path):
    import shutil
    import subprocess
    root = Path(__file__).resolve().parents[2]
    source = root.joinpath("Makefile").read_text()
    recipe = "# Capture caller data" + source.split("# Capture caller data", 1)[1].split("\n\ndeploy-canary:", 1)[0]
    inventory_guard = "require-inventory:" + source.split("\nrequire-inventory:", 1)[1].split("\nrequire-clean-source:", 1)[0]
    (tmp_path / "Makefile").write_text("ANSIBLE_DIR := ansible\nrequire-clean-source:\n\n" + recipe + "\n" + inventory_guard)
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(root / "scripts/backup-configure.py", tmp_path / "scripts/backup-configure.py")
    inventory = tmp_path / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\nnode-one ansible_host=192.0.2.1\n")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("ansible-inventory", "ansible-playbook"):
        command = binaries / name
        command.write_text('#!/bin/sh\nprintf "%s\\n" "$0" >> "$ANSIBLE_CALLS"\nprintf \'{"vpn":{"hosts":["node-one"]}}\\n\'\n')
        command.chmod(0o700)
    calls = tmp_path / "calls"
    environment = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
                   "ANSIBLE_DEBUG": "true", "ANSIBLE_CALLS": str(calls)}
    result = subprocess.run(["make", "backup-configure", "ANSIBLE_LIMIT=node-one", "SECRETS_FILE=unused"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "ansible-debug-not-supported" in result.stderr
    assert not calls.exists()


@pytest.mark.parametrize("origin", ["default", "command-line", "environment"])
def test_make_preserves_default_resolution_and_literal_explicit_paths(tmp_path, origin):
    import subprocess
    root = Path(__file__).resolve().parents[2]
    recipe = root.joinpath("Makefile").read_text().split("# Capture caller data", 1)[1].split("\n\ndeploy-canary:", 1)[0]
    recipe = ("# Capture caller data" + recipe).replace(
        "backup-configure: require-clean-source", "backup-configure:")
    (tmp_path / "Makefile").write_text("ENV := test\nRUNTIME_DIR := /private/runtime\nSECRETS_FILE ?= $(RUNTIME_DIR)/vpn-$(ENV).yaml\n" + recipe)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/backup-configure.py").write_text(
        "import json, os\nfrom pathlib import Path\n"
        "Path('captured.json').write_text(json.dumps({k: os.environ.get(k) for k in "
        "('BACKUP_CONFIGURE_HOST', 'BACKUP_CONFIGURE_SECRETS_FILE', 'BACKUP_CONFIGURE_EXTRA_VARS_FILE')}))\n")
    values = {"ANSIBLE_LIMIT": "node-one", "SECRETS_FILE": '/private/a path/$(literal).yaml',
              "ANSIBLE_EXTRA_VARS_FILE": '/private/quoted-"name".yaml'}
    environment = {k: v for k, v in os.environ.items() if k not in values}
    arguments = ["make", "backup-configure", "ANSIBLE_LIMIT=node-one"]
    if origin == "command-line":
        arguments += [f"{key}={value}" for key, value in values.items()]
    elif origin == "environment":
        environment.update(values)
    result = subprocess.run(arguments, cwd=tmp_path, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    actual = json.loads((tmp_path / "captured.json").read_text())
    assert actual["BACKUP_CONFIGURE_HOST"] == "node-one"
    assert actual["BACKUP_CONFIGURE_SECRETS_FILE"] == (
        "/private/runtime/vpn-test.yaml" if origin == "default" else values["SECRETS_FILE"])
    assert actual["BACKUP_CONFIGURE_EXTRA_VARS_FILE"] == (
        "" if origin == "default" else values["ANSIBLE_EXTRA_VARS_FILE"])


def controller_adapter(configure, monkeypatch):
    """Isolate snapshot/output tests; real Git/inventory/SSH have separate cases."""
    monkeypatch.setattr(configure, "clean_source", lambda *_: {
        "DEPLOY_SOURCE_REVISION": "a" * 40, "DEPLOYABLE_SOURCE_DIGEST": "b" * 64})
    def inventory(_source, alias, directory):
        target = directory / "inventory.ini"
        configure.private_file(target, f"[vpn]\n{alias}\n".encode())
        return {}, [], target
    monkeypatch.setattr(configure, "prepare_inventory", inventory)
    monkeypatch.setattr(configure, "transport_variables", lambda *_: {})


@pytest.mark.parametrize("debug", ["false", "no", "0", "off"])
def test_controller_uses_one_private_snapshot_and_cleans_after_ansible(configure, tmp_path, monkeypatch, debug):
    import subprocess
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    controller_adapter(configure, monkeypatch)
    monkeypatch.setenv("ANSIBLE_DEBUG", debug)
    for name in ("SKIP_PRECHECK", "ANSIBLE_TAGS", "ANSIBLE_RUN_TAGS", "ANSIBLE_SKIP_TAGS", "BACKUP_CONFIGURE_EXTRA_VARS_FILE"):
        monkeypatch.delenv(name, raising=False)
    original = tmp_path / "input.yaml"
    original.write_bytes(b"original-private-material")
    original.chmod(0o600)
    commands, snapshots = [], []
    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["env"]["ANSIBLE_DEBUG"] == "false"
        assert Path(kwargs["env"]["ANSIBLE_HOME"]).is_dir()
        snapshot_file = Path(kwargs["env"]["VPN_SECRETS_FILE"])
        snapshots.append(snapshot_file)
        assert snapshot_file.read_bytes() == b"original-private-material"
        assert stat.S_IMODE(snapshot_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(snapshot_file.parent.stat().st_mode) == 0o700
        original.write_bytes(b"replaced-after-first-read")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(configure.subprocess, "run", run)
    configure.controller("inventory.ini", "node-one", str(original))
    assert len(commands) == 4
    assert commands[-1][commands[-1].index("--limit") + 1] == "node-one"
    assert "--strict" in commands[0]
    assert all(not item.exists() for item in snapshots)


@pytest.mark.parametrize("status", ["pending", "rollback-incomplete", "invalid", None])
def test_persistent_incomplete_recovery_blocks_after_runtime_lock_disappears(configure, status):
    recovery = configure.path("var/lib/vpn-backup/configure-recovery") / ("a" * 32)
    recovery.mkdir(parents=True, mode=0o700)
    if status is not None:
        (recovery / "status").write_text(status)
        (recovery / "status").chmod(0o600)
    assert not configure.path("run/vpn-backup-configure.lock").exists()
    with pytest.raises(configure.ConfigError, match="recovery-incomplete-keep-timers-stopped"):
        configure.claim()
    assert not configure.path("run/vpn-backup-configure.lock").exists()
    assert recovery.exists()


@pytest.mark.parametrize("failure", [None, "password", "config"])
def test_real_restic_repository_precondition_is_read_only(configure, monkeypatch, failure):
    import hashlib
    import shutil
    import subprocess
    executable = shutil.which("restic")
    assert executable, "real restic is required for backup repository regression tests"
    binary = configure.path("usr/bin/restic")
    shutil.copyfile(executable, binary)
    binary.chmod(0o755)
    repo = configure.path("var/backups/vpn-restic")
    (repo / "config").unlink()
    password = configure.path("etc/restic/password")
    subprocess.run([str(binary), "--no-cache", "-r", str(repo), "--password-file", str(password), "init"],
                   capture_output=True, check=True, timeout=30)
    if failure == "password":
        password.write_text("wrong-private-password")
    elif failure == "config":
        (repo / "config").chmod(0o600)
        (repo / "config").write_bytes(b"not-an-encrypted-restic-config")
    def repository_files():
        return {str(item.relative_to(repo)): hashlib.sha256(item.read_bytes()).hexdigest()
                for item in repo.rglob("*") if item.is_file()}
    before = repository_files()
    observed = configure.observed_repository_decryptable
    monkeypatch.setattr(configure, "repository_decryptable", observed)
    if failure:
        with pytest.raises(configure.ConfigError, match="local-repository-unreadable"):
            configure.prerequisites()
    else:
        configure.prerequisites()
    assert repository_files() == before
    assert not configure.path("run/vpn-backup-configure.lock").exists()


@pytest.mark.parametrize("value", ["true", "yes", "1", "on", "TRUE"])
def test_debug_is_rejected_before_secret_snapshot_or_subprocess(configure, monkeypatch, value):
    monkeypatch.setenv("ANSIBLE_DEBUG", value)
    calls = []
    monkeypatch.setattr(configure, "materialized_bytes", lambda *_: calls.append("secret-read"))
    monkeypatch.setattr(configure.subprocess, "run", lambda *_args, **_kwargs: calls.append("process"))
    with pytest.raises(configure.ConfigError, match="ansible-debug-not-supported"):
        configure.controller("unused", "node-one", "unused")
    assert calls == []


def test_controller_disables_config_debug_for_real_private_ansible_script(configure, tmp_path, monkeypatch):
    import subprocess
    import uuid
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    for key in list(os.environ):
        if key.startswith("ANSIBLE_") or key in ("SKIP_PRECHECK", "BACKUP_CONFIGURE_EXTRA_VARS_FILE"):
            monkeypatch.delenv(key, raising=False)
    settings = tmp_path / "ansible.cfg"
    settings.write_text("[defaults]\ndebug=True\n")
    monkeypatch.setenv("ANSIBLE_CONFIG", str(settings))
    monkeypatch.setenv("ANSIBLE_BECOME", "false")
    materialized = tmp_path / "secrets.yaml"
    materialized.write_bytes(b"synthetic-private-input")
    materialized.chmod(0o600)
    token = uuid.uuid4().hex
    claim = tmp_path / "claim.py"
    claim.write_text('import json\nprint(json.dumps({"token": ' + repr(token) + '}))\n')
    play = tmp_path / "private.json"
    play.write_text(json.dumps([{"hosts": "localhost", "gather_facts": False, "become": False,
                                "tasks": [{"name": "Private fixture", "no_log": True,
                                           "ansible.builtin.script": {"cmd": str(claim), "executable": "python3"}}]}]))
    controller_adapter(configure, monkeypatch)
    original_run = subprocess.run
    observed = []
    def run(command, **kwargs):
        if command[0] == "ansible-playbook":
            result = original_run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(play)],
                                  env=kwargs["env"], cwd=tmp_path, capture_output=True, text=True, timeout=45)
            observed.append(result)
            return result
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(configure.subprocess, "run", run)
    configure.controller("unused", "node-one", str(materialized))
    assert len(observed) == 1 and observed[0].returncode == 0
    assert token not in observed[0].stdout + observed[0].stderr


def test_controller_environment_drops_execution_and_git_overrides(configure, monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "ANSIBLE_SSH_EXECUTABLE", "ANSIBLE_CALLBACK_PLUGINS",
                 "ANSIBLE_CONFIG", "ANSIBLE_ACTION_PLUGINS", "PYTHONPATH", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "synthetic-untrusted-override")
    root = Path(__file__).resolve().parents[2]
    env = configure.execution_environment(root)
    assert not any(name in env for name in ("GIT_DIR", "GIT_WORK_TREE", "PYTHONPATH", "AWS_SECRET_ACCESS_KEY"))
    assert env["ANSIBLE_CONFIG"] == str(root / "ansible/ansible.cfg")
    assert env["ANSIBLE_VARS_ENABLED"] == ""
    assert env["ANSIBLE_CALLBACK_PLUGINS"] == os.devnull
    assert env["ANSIBLE_ACTION_PLUGINS"] == os.devnull
    assert "synthetic-untrusted-override" not in env.values()


def test_inventory_snapshot_is_selected_once_and_never_reopens_original(configure, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    key = tmp_path / "identity"
    key.write_text("synthetic-private-key")
    key.chmod(0o600)
    inventory = tmp_path / "source.ini"
    inventory.write_text(f"[vpn]\nnode-one ansible_host=192.0.2.1 ansible_user=deploy ansible_port=2222\n"
                         f"other ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22\n"
                         f"[vpn-p0]\nnode-one\n[vpn:vars]\nansible_ssh_private_key_file={key}\n")
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    calls = []
    select = configure.select_target
    def once(path, alias):
        calls.append(Path(path))
        result = select(path, alias)
        inventory.write_text("[vpn]\nchanged\n")
        return result
    monkeypatch.setattr(configure, "select_target", once)
    host, cohorts, selected = configure.prepare_inventory(str(inventory), "node-one", directory)
    assert host["address"] == "192.0.2.1" and host["port"] == 2222
    assert cohorts == ["vpn-p0"]
    assert len(calls) == 1 and calls[0] != inventory
    assert "192.0.2.1" in calls[0].read_text() and "changed" not in selected.read_text()
    assert selected.read_text() == "[vpn]\nnode-one\n[vpn-p0]\nnode-one\n"
    assert stat.S_IMODE(selected.stat().st_mode) == 0o600


def test_transport_overrides_keep_selected_host_key_identity(configure, tmp_path, monkeypatch):
    import shlex
    import subprocess
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    key = tmp_path / "identity"
    key.write_text("synthetic-key")
    key.chmod(0o600)
    known = tmp_path / "known_hosts"
    known.write_text("synthetic-pin")
    host = {"name": "node-one", "address": "192.0.2.1", "transport": "192.0.2.1",
            "alias": "node-one.example.test", "port": 22, "key": str(key), "user": "deploy"}
    values = configure.transport_variables(host, {"ansible_host": "100.64.0.1", "ansible_port": 2222}, known)
    assert (values["ansible_host"], values["ansible_port"], values["ansible_user"]) == ("100.64.0.1", 2222, "deploy")
    result = subprocess.run([values["ansible_ssh_executable"], "-G", *shlex.split(values["ansible_ssh_args"]),
                             values["ansible_host"]], capture_output=True, text=True, check=True)
    parsed = dict(line.split(" ", 1) for line in result.stdout.splitlines())
    assert parsed["hostkeyalias"] == "[node-one.example.test]:2222"
    assert parsed["port"] == "2222" and parsed["user"] == "deploy"
    assert parsed["stricthostkeychecking"] == "true"
    assert parsed["identityagent"] == "none" and parsed["controlmaster"] == "false"
    assert values["ansible_scp_executable"] == "/usr/bin/scp"
    assert values["ansible_sftp_executable"] == "/usr/bin/sftp"


@pytest.mark.parametrize("cohort", ["p0", "p1p2", "fullstack"])
@pytest.mark.parametrize("override", [False, True])
def test_real_ansible_canonical_cohort_rendering_parity(configure, tmp_path, cohort, override):
    import shutil
    import subprocess
    import yaml
    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / "baseline"
    isolated = tmp_path / "isolated"
    for directory in (baseline, isolated):
        directory.mkdir()
    shutil.copytree(root / "ansible/group_vars", baseline / "group_vars")
    secrets = tmp_path / "secrets.yaml"
    document = yaml.safe_load((root / "tests/fixtures/secrets-sample.yml").read_text())
    secrets.write_text(yaml.safe_dump(document))
    secrets.chmod(0o600)
    extra = {"public_site_canonical_url": "https://override.example.test",
             "ansible_host": "100.64.0.1", "ansible_port": 2222} if override else {}
    environment = configure.execution_environment(root)
    inventory = tmp_path / "inventory.ini"
    inventory.write_text(f"[vpn]\nnode-one\n[vpn-{cohort}]\nnode-one\n")
    envs = [{**environment, "ANSIBLE_VARS_ENABLED": "host_group_vars"}, environment]
    for directory, env in zip((baseline, isolated), envs):
        play = [{"hosts": "vpn", "connection": "local", "gather_facts": False, "become": False,
                 "tasks": [
                     {"name": "Capture effective cohort", "ansible.builtin.copy": {
                         "dest": str(directory / "values.json"),
                         "content": "{{ {'vpn': vpn, 'restic_repo_dir': restic_repo_dir, 'ansible_host': ansible_host | default(''), 'ansible_port': ansible_port | default(22), 'public_site_canonical_url': public_site_canonical_url | default('')} | to_json }}"}},
                     {"name": "Render real backup scripts", "ansible.builtin.template": {
                         "src": str(root / "ansible/roles/backup/templates") + "/{{ item }}.j2",
                         "dest": str(directory) + "/{{ item }}"},
                      "loop": ["vpn-backup.sh", "vpn-backup-restore-drill.sh"]}]}]
        if directory == baseline:
            play[0]["vars_files"] = [str(secrets)]
            play[0]["tasks"].insert(0, {"name": "Expose canonical static AWG defaults without execution",
                "ansible.builtin.import_role": {"name": "amneziawg"}, "when": False})
        else:
            production = yaml.safe_load((root / "ansible/playbooks/backup-configure.yml").read_text())[0]
            loader = next(task for task in production["pre_tasks"] if "ansible.builtin.include_vars" in task)
            play[0]["pre_tasks"] = [loader]
            env["BACKUP_CONFIGURATION_VARS_FILES"] = json.dumps(configure.canonical_variables(root, ["vpn-" + cohort]))
        play[0]["vars"] = yaml.safe_load((root / "ansible/roles/backup/defaults/main.yml").read_text())
        play[0]["vars"]["vpn_secrets_file"] = str(secrets)
        # Role defaults must remain below vars_files, just as in the real role.
        play[0]["vars"].pop("backup")
        playbook = directory / "play.json"
        playbook.write_text(json.dumps(play))
        if directory == isolated:
            for base in (isolated, tmp_path):
                sibling = base / "host_vars"
                sibling.mkdir(exist_ok=True)
                (sibling / "node-one.yml").write_text("vpn: {enable_backup: false}\nansible_connection: poisoned\n")
        completed = subprocess.run(["ansible-playbook", "-i", str(inventory), str(playbook),
                                    "--extra-vars", json.dumps(extra)], env=env, capture_output=True, text=True, timeout=45)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    for name in ("values.json", "vpn-backup.sh", "vpn-backup-restore-drill.sh"):
        assert (baseline / name).read_bytes() == (isolated / name).read_bytes()


def test_make_git_routing_cannot_run_identity_before_controller(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[2]
    source = root.joinpath("Makefile").read_text()
    recipe = "# Capture caller data" + source.split("# Capture caller data", 1)[1].split("\n\ndeploy-canary:", 1)[0]
    (tmp_path / "Makefile").write_text(
        "DEPLOY_SOURCE_REVISION ?= $(shell touch EARLY; printf revision)\n"
        "DEPLOYABLE_SOURCE_DIGEST ?= $(shell touch EARLY; printf digest)\n"
        "export DEPLOY_SOURCE_REVISION DEPLOYABLE_SOURCE_DIGEST\nrequire-clean-source:\n\n" + recipe)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/backup-configure.py").write_text(
        "import os\nassert os.environ.get('DEPLOY_SOURCE_REVISION') == ''\n"
        "assert os.environ.get('DEPLOYABLE_SOURCE_DIGEST') == ''\n")
    result = subprocess.run(["make", "backup-configure"], cwd=tmp_path,
                            env={**os.environ, "GIT_DIR": "unrelated-clean-repository"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "EARLY").exists()


def test_clean_source_ignores_other_git_directory(configure, tmp_path, monkeypatch):
    import shutil
    import subprocess
    root = Path(__file__).resolve().parents[2]
    actual, other = tmp_path / "actual", tmp_path / "other"
    for directory in (actual, other):
        directory.mkdir()
        subprocess.run(["git", "init", "-q", str(directory)], check=True)
        subprocess.run(["git", "-C", str(directory), "config", "user.name", "Backup Test"], check=True)
        subprocess.run(["git", "-C", str(directory), "config", "user.email", "backup@example.invalid"], check=True)
        (directory / "scripts").mkdir()
        shutil.copyfile(root / "scripts/deploy-source-identity.sh", directory / "scripts/deploy-source-identity.sh")
        (directory / "scripts/deploy-source-identity.sh").chmod(0o755)
        subprocess.run(["git", "-C", str(directory), "add", "."], check=True)
        subprocess.run(["git", "-C", str(directory), "commit", "-qm", "test: seed backup source"], check=True)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    env = configure.execution_environment(actual)
    identity = configure.clean_source(actual, env)
    assert len(identity["DEPLOY_SOURCE_REVISION"]) == 40 and len(identity["DEPLOYABLE_SOURCE_DIGEST"]) == 64
    (actual / "dirty.txt").write_text("actual checkout is dirty")
    with pytest.raises(configure.ConfigError, match="clean-source-required"):
        configure.clean_source(actual, env)


def test_controller_pins_final_transport_and_uses_private_inventory(configure, tmp_path, monkeypatch):
    import subprocess
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    for name in ("ANSIBLE_DEBUG", "SKIP_PRECHECK", "ANSIBLE_TAGS", "ANSIBLE_RUN_TAGS", "ANSIBLE_SKIP_TAGS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(configure, "clean_source", lambda *_: {
        "DEPLOY_SOURCE_REVISION": "a" * 40, "DEPLOYABLE_SOURCE_DIGEST": "b" * 64})
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/known_hosts").write_text("synthetic-pin")
    monkeypatch.setattr(configure.Path, "home", lambda: home)
    key = home / ".ssh/identity"
    key.write_text("synthetic-private-key")
    key.chmod(0o600)
    inventory = tmp_path / "source.ini"
    inventory.write_text(f"[vpn]\nnode-one ansible_host=192.0.2.1 ansible_user=deploy ansible_port=22\n"
                         f"[vpn-p0]\nnode-one\n[vpn:vars]\nansible_ssh_private_key_file={key}\n")
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("synthetic-private-input")
    secrets.chmod(0o600)
    extra = tmp_path / "extra.yaml"
    extra.write_text("ansible_host: 100.64.0.1\nansible_port: 2222\n")
    extra.chmod(0o600)
    monkeypatch.setenv("BACKUP_CONFIGURE_EXTRA_VARS_FILE", str(extra))
    monkeypatch.setenv("ANSIBLE_SSH_EXECUTABLE", "/untrusted/ssh")
    calls = []
    def run(command, **kwargs):
        if command[0] == "ansible-playbook":
            calls.append(command)
            assert Path(command[command.index("-i") + 1]) != inventory
            assert Path(command[command.index("-i") + 1]).read_text() == "[vpn]\nnode-one\n[vpn-p0]\nnode-one\n"
            final = json.loads(command[-1])
            assert (final["ansible_host"], final["ansible_port"]) == ("100.64.0.1", 2222)
            assert "HostKeyAlias=[192.0.2.1]:2222" in final["ansible_ssh_args"]
            assert final["ansible_ssh_executable"] == "/usr/bin/ssh"
            assert "ANSIBLE_SSH_EXECUTABLE" not in kwargs["env"]
            assert kwargs["env"]["ANSIBLE_VARS_ENABLED"] == ""
            assert Path(kwargs["env"]["ANSIBLE_HOME"]).parent == kwargs["cwd"]
            assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(configure.subprocess, "run", run)
    configure.controller(str(inventory), "node-one", str(secrets))
    assert len(calls) == 1
