"""Contract tests for the inert shared runtime release installer role."""

import getpass
import grp
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
import zipfile
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "runtime-release"
DEFAULTS = ROLE / "defaults" / "main.yml"
TASKS = ROLE / "tasks" / "main.yml"
ACTIVATOR = ROLE / "files" / "runtime_release_activate.py"


def _raw_tasks() -> list[dict]:
    return yaml.safe_load(TASKS.read_text())


def _tasks() -> list[dict]:
    flattened: list[dict] = []

    def visit(tasks: list[dict]) -> None:
        for task in tasks:
            flattened.append(task)
            for section in ("block", "rescue", "always"):
                if section in task:
                    visit(task[section])

    visit(_raw_tasks())
    return flattened


def _task(name: str) -> dict:
    matches = [task for task in _tasks() if task.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def test_runtime_release_defaults_are_a_complete_prefixed_api() -> None:
    defaults = yaml.safe_load(DEFAULTS.read_text())
    assert defaults == {
        "runtime_release_version": "",
        "runtime_release_install_root": "",
        "runtime_release_binary_name": "",
        "runtime_release_public_link": "",
        "runtime_release_urls": {"amd64": "", "arm64": ""},
        "runtime_release_sha256": {"amd64": "", "arm64": ""},
        "runtime_release_arch_slugs": {"amd64": "amd64", "arm64": "arm64"},
        "runtime_release_artifact_filename": "artifact",
        "runtime_release_artifact_type": "binary",
        "runtime_release_archive_member": "",
        "runtime_release_archive_strip_components": 0,
        "runtime_release_download_dir": (
            "{{ runtime_release_install_root }}/.runtime-release-staging"
        ),
        "runtime_release_storage_owner": "root",
        "runtime_release_storage_group": "root",
    }


def test_preflight_and_architecture_selection_happen_before_writes() -> None:
    tasks = _tasks()
    names = [task["name"] for task in tasks]
    assert names[:3] == [
        "Derive canonical runtime release architecture",
        "Refuse unsupported runtime release architecture",
        "Validate runtime release contract before writing",
    ]
    assert names.index(
        "Validate runtime release contract before writing"
    ) < names.index("Ensure runtime release directories")

    architecture = tasks[0]["ansible.builtin.set_fact"]
    serialized = yaml.safe_dump(architecture)
    assert "x86_64" in serialized and "amd64" in serialized
    assert "aarch64" in serialized and "arm64" in serialized
    assert "ansible_facts['architecture']" in serialized

    selection = _task("Select pinned runtime release artifact")
    selected = selection["ansible.builtin.set_fact"]
    assert selected["_runtime_release_url"] == (
        "{{ runtime_release_urls[_runtime_release_arch_key] }}"
    )
    assert selected["_runtime_release_checksum"] == (
        "{{ runtime_release_sha256[_runtime_release_arch_key] | lower }}"
    )
    assert selected["runtime_release_arch_slug"] == (
        "{{ runtime_release_arch_slugs[_runtime_release_arch_key] }}"
    )


def test_contract_refuses_unpinned_or_unsafe_paths_and_artifact_shapes() -> None:
    clauses = _task("Validate runtime release contract before writing")[
        "ansible.builtin.assert"
    ]["that"]
    serialized = yaml.safe_dump(clauses)
    for expected in (
        "^[A-Za-z0-9._+-]+$",
        "^/[A-Za-z0-9._/+\\-]+$",
        "^[A-Za-z0-9._+-]+$",
        "^[0-9a-fA-F]{64}$",
        "runtime_release_artifact_type in ['binary', 'archive']",
        "runtime_release_urls[_runtime_release_arch_key]",
        "runtime_release_sha256[_runtime_release_arch_key]",
    ):
        assert expected in serialized
    assert "runtime_release_archive_member.split('/')" in serialized
    assert "[runtime_release_binary_name]" in serialized
    assert "runtime_release_archive_strip_components | int >= 0" in serialized
    assert "runtime_release_archive_strip_components | int <= 4" in serialized
    for unsafe in ("/../", "/./", "//"):
        assert unsafe in serialized
    assert "runtime_release_storage_owner == 'root'" in clauses
    assert "runtime_release_storage_group == 'root'" in clauses
    assert "runtime_release_owner" not in serialized
    assert "runtime_release_group" not in serialized


def test_download_is_checksum_verified_and_guarded_by_candidate_stat() -> None:
    candidate = _task("Inspect pinned runtime release candidate")
    candidate_path = candidate["ansible.builtin.stat"]["path"]
    assert candidate_path == (
        "{{ runtime_release_install_root }}/releases/"
        "{{ runtime_release_version }}/{{ runtime_release_binary_name }}"
    )

    download = _task("Download pinned runtime release artifact")
    module = download["ansible.builtin.get_url"]
    assert module["url"] == "{{ _runtime_release_url }}"
    assert module["checksum"] == "sha256:{{ _runtime_release_checksum }}"
    assert download["when"] == [
        "_runtime_release_needs_artifact",
        "not ansible_check_mode",
    ]

    verify = _task("Verify staged runtime release candidate")
    assertions = verify["ansible.builtin.assert"]["that"]
    assert "_runtime_release_verified_candidate.stat.exists" in assertions
    assert "_runtime_release_verified_candidate.stat.isreg" in assertions
    assert "_runtime_release_verified_candidate.stat.executable" in assertions


def test_release_receipt_binds_existing_candidate_to_pin_and_binary_digest() -> None:
    candidate = _task("Inspect pinned runtime release candidate")
    assert candidate["ansible.builtin.stat"]["checksum_algorithm"] == "sha256"

    receipt = _task("Validate existing runtime release receipt before writing")
    clauses = yaml.safe_dump(receipt["ansible.builtin.assert"]["that"])
    for field in (
        "schema_version",
        "version",
        "arch_key",
        "arch_slug",
        "binary_name",
        "artifact_sha256",
        "binary_sha256",
    ):
        assert field in clauses
    assert "_runtime_release_candidate.stat.checksum" in clauses

    activation = _task("Activate runtime release under host-local lock")
    argv = activation["ansible.builtin.command"]["argv"]
    for argument in (
        "--artifact-sha256",
        "{{ _runtime_release_checksum }}",
        "--candidate-sha256",
        "{{ _runtime_release_verified_candidate.stat.checksum | default('') }}",
        "--staged-candidate",
        "{{ _runtime_release_staged_candidate_path }}",
        "--artifact-type",
        "{{ runtime_release_artifact_type }}",
    ):
        assert argument in argv
    assert "Publish immutable runtime release receipt" not in [
        task["name"] for task in _tasks()
    ]


def test_binary_and_archive_candidates_are_staged_outside_the_live_release_tree() -> (
    None
):
    names = [task["name"] for task in _tasks()]
    assert "Install pinned binary artifact into versioned release" not in names
    assert "Extract pinned archive into versioned release" not in names

    archive = _task("Extract pinned archive into trusted staging")
    archive_module = archive["ansible.builtin.unarchive"]
    assert archive_module["dest"] == "{{ _runtime_release_stage_dir }}"
    assert archive_module["include"] == ["{{ runtime_release_archive_member }}"]
    assert "runtime_release_archive_strip_components" in archive_module["extra_opts"]

    activation = _task("Activate runtime release under host-local lock")
    assert "--staged-candidate" in activation["ansible.builtin.command"]["argv"]
    assert names.index("Activate runtime release under host-local lock") < names.index(
        "Clean trusted runtime release transaction"
    )


def test_staging_is_unique_and_cleanup_runs_for_every_transaction_outcome() -> None:
    reset = _task("Reset runtime release transaction ownership")
    assert reset["ansible.builtin.set_fact"] == {
        "_runtime_release_transaction_dir": "",
        "_runtime_release_artifact_path": "",
        "_runtime_release_stage_dir": "",
        "_runtime_release_staged_candidate_path": "",
        "_runtime_release_staging_preparation": {},
        "_runtime_release_staging_prepared": False,
    }
    prepare = _task("Prepare trusted runtime release transaction")
    assert prepare["register"] == "_runtime_release_staging_preparation"
    assert "--prepare-staging" in prepare["ansible.builtin.command"]["argv"]

    derive = _task("Select trusted runtime release transaction paths")
    derived = derive["ansible.builtin.set_fact"]
    assert "transaction_dir" in derived["_runtime_release_transaction_dir"]
    assert "artifact_path" in derived["_runtime_release_artifact_path"]
    assert "stage_dir" in derived["_runtime_release_stage_dir"]

    cleanup = _task("Clean trusted runtime release transaction")
    assert cleanup["ansible.builtin.command"]["argv"][-1] == "--cleanup-staging"
    assert cleanup["when"] == [
        "_runtime_release_needs_artifact",
        "not ansible_check_mode",
        "_runtime_release_staging_prepared | bool",
        "_runtime_release_transaction_dir | length > 0",
    ]
    transaction = next(
        task for task in _raw_tasks() if "block" in task and "always" in task
    )
    assert cleanup in transaction["always"]


def test_check_mode_predicts_candidate_or_receipt_publication_work() -> None:
    staging = _task("Validate runtime release staging namespace in check mode")
    assert staging["ansible.builtin.command"]["argv"][-1] == "--validate-staging-root"
    assert staging["changed_when"] is False
    assert staging["check_mode"] is False
    assert staging["when"] == [
        "_runtime_release_needs_artifact",
        "ansible_check_mode",
    ]
    activation = _task("Activate runtime release under host-local lock")
    argv = activation["ansible.builtin.command"]["argv"]
    assert "--requires-artifact" in argv
    assert activation["changed_when"] == (
        "(_runtime_release_activation.stdout | from_json).changed"
    )


def test_candidate_permissions_are_published_only_by_the_locked_helper() -> None:
    source = ACTIVATOR.read_text()
    assert "def _atomic_install_candidate(" in source
    assert "src_dir_fd=release.descriptor" in source
    assert "dst_dir_fd=release.descriptor" in source
    assert "os.fchmod(destination, 0o755)" in source
    assert (
        "Normalize installed runtime release candidate permissions"
        not in TASKS.read_text()
    )


def test_activation_uses_one_locked_helper_with_argv_and_categorical_json() -> None:
    preflight = _task("Preflight runtime release activation layout")
    assert preflight["ansible.builtin.command"]["argv"][-1] == "--check"
    assert preflight["changed_when"] is False
    assert preflight["when"] == "not ansible_check_mode"
    assert "--owner" in preflight["ansible.builtin.command"]["argv"]
    assert "--group" in preflight["ansible.builtin.command"]["argv"]

    activation = _task("Activate runtime release under host-local lock")
    command = activation["ansible.builtin.command"]
    assert command["argv"][:2] == ["/usr/bin/python3", "-"]
    assert command["argv"][2:10] == [
        "--install-root",
        "{{ runtime_release_install_root }}",
        "--version",
        "{{ runtime_release_version }}",
        "--binary-name",
        "{{ runtime_release_binary_name }}",
        "--public-link",
        "{{ runtime_release_public_link }}",
    ]
    assert command["argv"][-1] == "{{ '--check' if ansible_check_mode else '--apply' }}"
    assert "runtime_release_activate.py" in command["stdin"]
    assert command["stdin_add_newline"] is False
    assert "from_json" in activation["changed_when"]
    assert activation["check_mode"] is False

    source = TASKS.read_text()
    assert "Point current at pinned runtime release" not in source
    assert "Refuse unmanaged runtime release activation links" not in source


def test_role_exports_only_change_state_and_selected_arch_slug() -> None:
    published = _task("Publish runtime release change state")[
        "ansible.builtin.set_fact"
    ]
    assert set(published) == {"runtime_release_changed", "runtime_release_arch_slug"}
    changed = published["runtime_release_changed"]
    assert "_runtime_release_activation.stdout | from_json" in changed
    assert published["runtime_release_arch_slug"] == "{{ runtime_release_arch_slug }}"


def _activator_module():
    spec = importlib.util.spec_from_file_location("runtime_release_activate", ACTIVATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _activation_layout(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path = tmp_path.resolve()
    root = tmp_path / "install"
    public = tmp_path / "bin" / "runtime-fixture"
    public.parent.mkdir(parents=True)
    for version in ("v0", "v1", "v2"):
        release = root / "releases" / version
        release.mkdir(parents=True)
        binary = release / "runtime-fixture"
        binary.write_text(f"#!/bin/sh\necho {version}\n")
        binary.chmod(0o755)
    (root / "current").symlink_to(root / "releases" / "v0")
    (root / "previous").symlink_to(root / "releases" / "v2")
    public.symlink_to(root / "current" / "runtime-fixture")
    return root, public


def _link_snapshot(root: Path, public: Path) -> dict[str, str | None]:
    paths = {
        "current": root / "current",
        "previous": root / "previous",
        "public": public,
    }
    return {
        name: os.readlink(path) if path.is_symlink() else None
        for name, path in paths.items()
    }


def _trusted_staging_paths(
    root: Path, version: str, artifact: Path
) -> tuple[Path, Path]:
    staging = root / ".runtime-release-staging"
    artifact_node = (
        staging / f"runtime-release-runtime-fixture-{version}-amd64-{artifact.name}"
    )
    stage = staging / f"stage-runtime-fixture-{version}-amd64"
    return artifact_node, stage


def test_locked_helper_check_mode_predicts_old_current_without_mutation(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    before = _link_snapshot(root, public)

    result = helper.activate(root, "v1", "runtime-fixture", public, check=True)

    assert result == {"status": "predicted", "changed": True}
    assert _link_snapshot(root, public) == before


def test_locked_helper_rejects_traversing_current_and_previous_targets(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    for link_name in ("current", "previous"):
        root, public = _activation_layout(tmp_path / link_name)
        link = root / link_name
        link.unlink()
        link.symlink_to(str(root / "releases" / "v0" / ".." / "v1"))
        before = _link_snapshot(root, public)

        with __import__("pytest").raises(helper.UnsafeState):
            helper.activate(root, "v1", "runtime-fixture", public, check=False)
        assert _link_snapshot(root, public) == before


def test_locked_helper_compensates_each_publish_and_postcheck_failure(
    tmp_path: Path, monkeypatch
) -> None:
    helper = _activator_module()
    for failure_at in (1, 2, 3, 4):
        root, public = _activation_layout(tmp_path / str(failure_at))
        public.unlink()
        before = _link_snapshot(root, public)
        publish_calls = 0
        verify_calls = 0
        injected_publish_failure = False
        real_publish = helper._atomic_link
        real_verify = helper._verify_desired

        def fail_publish(directory, name, target, *, pre_replace=None):
            nonlocal injected_publish_failure, publish_calls
            publish_calls += 1
            if failure_at <= 3 and publish_calls == failure_at:
                injected_publish_failure = True
                raise OSError("injected publish failure")
            return real_publish(directory, name, target, pre_replace=pre_replace)

        def fail_verify(*args, **kwargs):
            nonlocal verify_calls
            verify_calls += 1
            if failure_at == 4 and verify_calls == 1:
                raise OSError("injected postcheck failure")
            return real_verify(*args, **kwargs)

        monkeypatch.setattr(helper, "_atomic_link", fail_publish)
        monkeypatch.setattr(helper, "_verify_desired", fail_verify)
        with __import__("pytest").raises(helper.ActivationFailed):
            helper.activate(root, "v1", "runtime-fixture", public, check=False)
        if failure_at <= 3:
            assert (
                injected_publish_failure
            ), f"publish position {failure_at} was not exercised"
        else:
            assert verify_calls == 1
        assert _link_snapshot(root, public) == before
        monkeypatch.setattr(helper, "_atomic_link", real_publish)
        monkeypatch.setattr(helper, "_verify_desired", real_verify)


def test_locked_helper_serializes_concurrent_controller_activation(
    tmp_path: Path,
) -> None:
    root, public = _activation_layout(tmp_path)
    commands = []
    for version in ("v1", "v2"):
        commands.append(
            [
                sys.executable,
                str(ACTIVATOR),
                "--install-root",
                str(root),
                "--version",
                version,
                "--binary-name",
                "runtime-fixture",
                "--public-link",
                str(public),
                "--apply",
            ]
        )
    processes = [
        subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for command in commands
    ]
    results = [
        process.communicate(timeout=10) + (process.returncode,) for process in processes
    ]
    assert all(result[2] == 0 for result in results), results
    assert all(json.loads(result[0])["status"] == "committed" for result in results)

    current = Path(os.readlink(root / "current"))
    previous = Path(os.readlink(root / "previous"))
    assert current in {root / "releases" / "v1", root / "releases" / "v2"}
    assert previous in {root / "releases" / "v1", root / "releases" / "v2"}
    assert previous != current
    assert os.readlink(public) == str(root / "current" / "runtime-fixture")


def test_locked_helper_reports_incomplete_compensation_distinctly(
    tmp_path: Path, monkeypatch
) -> None:
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected publish failure")

    def fail_compensation(*_args, **_kwargs):
        raise OSError("injected compensation failure")

    monkeypatch.setattr(helper, "_atomic_link", fail_publish)
    monkeypatch.setattr(helper, "_restore_snapshot", fail_compensation)
    with __import__("pytest").raises(helper.CompensationIncomplete):
        helper.activate(root, "v1", "runtime-fixture", public, check=False)


def test_locked_helper_uses_binary_name_when_public_link_has_alias(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root, original_public = _activation_layout(tmp_path)
    alias = original_public.with_name("runtime-alias")
    original_public.rename(alias)

    result = helper.activate(root, "v1", "runtime-fixture", alias, check=False)

    assert result == {"status": "committed", "changed": True}
    assert os.readlink(alias) == str(root / "current" / "runtime-fixture")


def test_locked_helper_refuses_tampered_candidate_before_receipt_or_activation(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    candidate = root / "releases" / "v1" / "runtime-fixture"
    expected = hashlib.sha256(candidate.read_bytes()).hexdigest()
    candidate.write_text("#!/bin/sh\necho tampered\n")
    candidate.chmod(0o755)
    before = _link_snapshot(root, public)

    with __import__("pytest").raises(helper.UnsafeState):
        helper.activate(
            root,
            "v1",
            "runtime-fixture",
            public,
            check=False,
            artifact_sha256="a" * 64,
            candidate_sha256=expected,
            arch_key="amd64",
            arch_slug="amd64",
            owner=getpass.getuser(),
            group=grp.getgrgid(os.getgid()).gr_name,
        )

    assert _link_snapshot(root, public) == before
    assert not (root / "releases" / "v1" / ".runtime-release.json").exists()


def _run_role(
    tmp_path: Path,
    version: str,
    artifact: Path,
    *,
    check: bool = False,
    public_link: Path | None = None,
    uppercase_checksum: bool = False,
    artifact_type: str = "binary",
    archive_member: str = "",
    archive_strip_components: int = 0,
    install_root: Path | None = None,
    run_label: str = "",
    storage_owner: str = "root",
    storage_group: str = "root",
) -> subprocess.CompletedProcess:
    tmp_path = tmp_path.resolve()
    artifact = artifact.resolve()
    if install_root is not None:
        install_root = install_root.resolve()
    if public_link is not None:
        public_link = public_link.resolve()
    tmp_path.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("ansible-playbook")
    assert (
        executable
    ), "installed Ansible is required for the runtime-release behavior proof"
    checksum = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
    if uppercase_checksum:
        checksum = checksum.upper()
    root = install_root or (tmp_path / "install")
    variables = {
        "ansible_facts": {"architecture": "x86_64"},
        "ansible_python_interpreter": sys.executable,
        "runtime_release_version": version,
        "runtime_release_install_root": str(root),
        "runtime_release_binary_name": "runtime-fixture",
        "runtime_release_public_link": str(
            public_link or (tmp_path / "bin" / "runtime-fixture")
        ),
        "runtime_release_urls": {
            "amd64": artifact.as_uri(),
            "arm64": artifact.as_uri(),
        },
        "runtime_release_sha256": {"amd64": checksum, "arm64": checksum},
        "runtime_release_artifact_filename": artifact.name,
        "runtime_release_artifact_type": artifact_type,
        "runtime_release_archive_member": archive_member,
        "runtime_release_archive_strip_components": archive_strip_components,
        "runtime_release_download_dir": str(root / ".runtime-release-staging"),
        "runtime_release_storage_owner": storage_owner,
        "runtime_release_storage_group": storage_group,
    }
    playbook = tmp_path / f"install-{version}-{run_label}.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise runtime release contract",
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": variables,
                    "roles": ["runtime-release"],
                }
            ],
            sort_keys=False,
        )
    )
    config = tmp_path / f"ansible-{run_label}.cfg"
    config.write_text("[defaults]\nfact_caching=memory\ninject_facts_as_vars=false\n")
    environment = {
        key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
    }
    environment.update(
        {
            "ANSIBLE_CONFIG": str(config),
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
            "ANSIBLE_ROLES_PATH": str(ROOT / "ansible" / "roles"),
            "ANSIBLE_NOCOLOR": "1",
        }
    )
    command = [executable, "-i", "localhost,", str(playbook)]
    if check:
        command.append("--check")
    return subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_helper_fixture(
    tmp_path: Path,
    version: str,
    artifact: Path,
    *,
    check: bool = False,
    public_link: Path | None = None,
    uppercase_checksum: bool = False,
    artifact_type: str = "binary",
    archive_member: str = "",
    archive_strip_components: int = 0,
    install_root: Path | None = None,
    run_label: str = "",
) -> subprocess.CompletedProcess[str]:
    """Exercise activation with a non-root fixture identity.

    The production role now requires root-owned storage before it downloads or
    extracts anything.  These unit fixtures cannot create that identity, so
    they exercise the helper's parametrized storage contract directly instead
    of pretending an unprivileged Ansible run is a production convergence.
    """
    del archive_strip_components, run_label
    helper = _activator_module()
    tmp_path = tmp_path.resolve()
    artifact = artifact.resolve()
    # Do not resolve the final public component: after the first activation it
    # is deliberately a symlink into install_root.
    root = Path(os.path.abspath(install_root or (tmp_path / "install")))
    public = Path(
        os.path.abspath(public_link or (tmp_path / "bin" / "runtime-fixture"))
    )
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    artifact_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if uppercase_checksum:
        artifact_digest = artifact_digest.upper()

    if check:
        receipt = root / "releases" / version / ".runtime-release.json"
        candidate = root / "releases" / version / "runtime-fixture"
        try:
            result = helper.activate(
                root,
                version,
                "runtime-fixture",
                public,
                check=True,
                requires_artifact=not candidate.exists() or not receipt.exists(),
            )
        except Exception as error:
            return subprocess.CompletedProcess([], 1, "", f"{error}\n")
        return subprocess.CompletedProcess(
            [], 0, f"changed={int(bool(result['changed']))}\n", ""
        )

    root.mkdir(parents=True, exist_ok=True)
    (root / "releases").mkdir(exist_ok=True)
    for directory in (root, root / "releases"):
        directory.chmod(0o755)

    stage_name = (
        f"stage-runtime-fixture-{version}-amd64" if artifact_type == "archive" else None
    )
    artifact_name = f"runtime-release-runtime-fixture-{version}-amd64-{artifact.name}"
    staging_prepared = False
    transaction_dir: Path | None = None
    staged_candidate: Path | None = None
    receipt = root / "releases" / version / ".runtime-release.json"
    installed_candidate = root / "releases" / version / "runtime-fixture"
    needs_artifact = not installed_candidate.exists() or not receipt.exists()
    try:
        if needs_artifact:
            preparation = helper.prepare_staging(
                root,
                root / ".runtime-release-staging",
                artifact_name,
                stage_name,
                "runtime-fixture",
                version,
                artifact_digest.lower(),
                artifact_type,
                owner=owner,
                group=group,
            )
            staging_prepared = True
            transaction_dir = Path(preparation["transaction_dir"])
            if artifact_type == "binary":
                staged_candidate = Path(preparation["artifact_path"])
                shutil.copyfile(artifact, staged_candidate)
            elif artifact_type == "archive":
                if not archive_member:
                    raise helper.UnsafeState("missing-archive-member")
                stage = Path(preparation["stage_dir"])
                staged_candidate = stage / "runtime-fixture"
                with zipfile.ZipFile(artifact) as archive:
                    staged_candidate.write_bytes(archive.read(archive_member))
            else:
                raise helper.UnsafeState("unsafe-artifact-type")
            staged_candidate.chmod(0o700 if artifact_type == "binary" else 0o755)
        else:
            staged_candidate = installed_candidate
        candidate_digest = hashlib.sha256(staged_candidate.read_bytes()).hexdigest()
        result = helper.activate(
            root,
            version,
            "runtime-fixture",
            public,
            check=False,
            artifact_sha256=artifact_digest.lower(),
            candidate_sha256=candidate_digest,
            artifact_type=artifact_type,
            arch_key="amd64",
            arch_slug="amd64",
            owner=owner,
            group=group,
            staged_candidate=staged_candidate,
            staging_dir=(root / ".runtime-release-staging") if needs_artifact else None,
            transaction_dir=transaction_dir,
            artifact_name=artifact_name if needs_artifact else None,
            stage_name=stage_name if needs_artifact else None,
            requires_artifact=needs_artifact,
        )
    except Exception as error:
        outcome = subprocess.CompletedProcess([], 1, "", f"{error}\n")
    else:
        outcome = subprocess.CompletedProcess(
            [], 0, f"changed={int(bool(result['changed']))}\n", ""
        )
    finally:
        if staging_prepared and transaction_dir is not None:
            helper.cleanup_staging(
                root,
                root / ".runtime-release-staging",
                transaction_dir,
                artifact_name,
                stage_name,
                "runtime-fixture",
                version,
                artifact_digest.lower(),
                artifact_type,
                owner=owner,
                group=group,
            )
    return outcome


def test_helper_install_upgrade_and_activation_failure_rollback(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    first = tmp_path / "fixture-v1"
    second = tmp_path / "fixture-v2"
    third = tmp_path / "fixture-v3"
    first.write_text("#!/bin/sh\necho v1\n")
    second.write_text("#!/bin/sh\necho v2\n")
    third.write_text("#!/bin/sh\necho v3\n")

    installed = _run_helper_fixture(tmp_path, "v1", first)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    current = tmp_path / "install" / "current"
    public = tmp_path / "bin" / "runtime-fixture"
    assert current.readlink() == tmp_path / "install" / "releases" / "v1"
    assert public.readlink() == current / "runtime-fixture"
    assert public.resolve().read_text() == first.read_text()
    receipt = tmp_path / "install" / "releases" / "v1" / ".runtime-release.json"
    assert receipt.is_file()

    upgraded = _run_helper_fixture(tmp_path, "v2", second)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    assert current.readlink() == tmp_path / "install" / "releases" / "v2"
    assert (tmp_path / "install" / "previous").readlink() == (
        tmp_path / "install" / "releases" / "v1"
    )
    assert public.resolve().read_text() == second.read_text()

    idempotent = _run_helper_fixture(tmp_path, "v2", second)
    assert idempotent.returncode == 0, idempotent.stdout + idempotent.stderr
    assert "changed=0" in idempotent.stdout

    public.unlink()
    public.parent.rmdir()
    refused = _run_helper_fixture(tmp_path, "v3", third)
    assert refused.returncode != 0
    assert current.readlink() == tmp_path / "install" / "releases" / "v2"
    assert (tmp_path / "install" / "previous").readlink() == (
        tmp_path / "install" / "releases" / "v1"
    )
    assert (tmp_path / "install" / "releases" / "v3" / "runtime-fixture").exists()


def test_helper_refuses_same_version_pin_or_binary_drift(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho original\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    current = tmp_path / "install" / "current"

    artifact.write_text("#!/bin/sh\necho repinned\n")
    repinned = _run_helper_fixture(tmp_path, "v1", artifact)
    assert repinned.returncode != 0
    assert current.readlink() == tmp_path / "install" / "releases" / "v1"

    artifact.write_text("#!/bin/sh\necho original\n")
    binary = current / "runtime-fixture"
    binary.write_text("#!/bin/sh\necho tampered\n")
    tampered = _run_helper_fixture(tmp_path, "v1", artifact)
    assert tampered.returncode != 0
    assert "binary-pin-mismatch" in (tampered.stdout + tampered.stderr)


def test_helper_serializes_same_version_different_pins_without_cross_blessing(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    first = tmp_path / "fixture-first"
    second = tmp_path / "fixture-second"
    first.write_text("#!/bin/sh\necho first\n")
    second.write_text("#!/bin/sh\necho second\n")

    install_root = tmp_path / "install"
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            _run_helper_fixture,
            tmp_path / "first-controller",
            "v1",
            first,
            install_root=install_root,
            public_link=tmp_path / "bin" / "runtime-fixture",
            run_label="first",
        )
        second_future = executor.submit(
            _run_helper_fixture,
            tmp_path / "second-controller",
            "v1",
            second,
            install_root=install_root,
            public_link=tmp_path / "bin" / "runtime-fixture",
            run_label="second",
        )
        first_process = first_future.result(timeout=30)
        second_process = second_future.result(timeout=30)

    successes = [
        process
        for process in (first_process, second_process)
        if process.returncode == 0
    ]
    assert len(successes) == 1, [
        process.stdout + process.stderr for process in (first_process, second_process)
    ]
    receipt = json.loads(
        (tmp_path / "install/releases/v1/.runtime-release.json").read_text()
    )
    expected = {
        hashlib.sha256(first.read_bytes()).hexdigest(),
        hashlib.sha256(second.read_bytes()).hexdigest(),
    }
    assert receipt["artifact_sha256"] in expected
    assert (
        receipt["binary_sha256"]
        == hashlib.sha256(
            (tmp_path / "install/releases/v1/runtime-fixture").read_bytes()
        ).hexdigest()
    )


def test_helper_forced_losing_pin_cannot_replace_committed_candidate(
    tmp_path: Path,
) -> None:
    """A later same-version controller is the deterministic loser at the role seam."""
    (tmp_path / "winner" / "bin").mkdir(parents=True)
    winner = tmp_path / "fixture-winner"
    loser = tmp_path / "fixture-loser"
    winner.write_text("#!/bin/sh\necho winner\n")
    loser.write_text("#!/bin/sh\necho loser\n")

    installed = _run_helper_fixture(tmp_path / "winner", "v1", winner)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    candidate = tmp_path / "winner" / "install/releases/v1/runtime-fixture"
    receipt = candidate.parent / ".runtime-release.json"
    before_bytes = candidate.read_bytes()
    before_candidate = candidate.stat()
    before_receipt = receipt.read_bytes()
    public = tmp_path / "winner" / "bin/runtime-fixture"
    before_links = _link_snapshot(candidate.parents[2], public)

    refused = _run_helper_fixture(
        tmp_path / "loser",
        "v1",
        loser,
        install_root=candidate.parents[2],
        public_link=public,
        run_label="forced-loser",
    )

    assert refused.returncode != 0
    assert candidate.read_bytes() == before_bytes
    assert candidate.stat().st_ino == before_candidate.st_ino
    assert receipt.read_bytes() == before_receipt
    assert _link_snapshot(candidate.parents[2], public) == before_links


def test_helper_refuses_writable_receipt_before_other_writes(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho original\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    receipt = tmp_path / "install/releases/v1/.runtime-release.json"
    receipt.chmod(0o666)

    refused = _run_helper_fixture(tmp_path, "v1", artifact)
    assert refused.returncode != 0
    assert receipt.stat().st_mode & 0o777 == 0o666


def test_helper_adopts_only_byte_identical_legacy_candidate(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho original\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    receipt = tmp_path / "install" / "releases" / "v1" / ".runtime-release.json"
    receipt.unlink()

    adopted = _run_helper_fixture(tmp_path, "v1", artifact)
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    assert receipt.is_file()

    receipt.unlink()
    (tmp_path / "install" / "current" / "runtime-fixture").write_text(
        "#!/bin/sh\necho mismatch\n"
    )
    refused = _run_helper_fixture(tmp_path, "v1", artifact)
    assert refused.returncode != 0
    assert not receipt.exists()


def test_helper_check_mode_predicts_legacy_receipt_adoption_without_writes(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho original\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    receipt = tmp_path / "install/releases/v1/.runtime-release.json"
    receipt.unlink()
    before_links = _link_snapshot(
        tmp_path / "install", tmp_path / "bin/runtime-fixture"
    )

    predicted = _run_helper_fixture(tmp_path, "v1", artifact, check=True)

    assert predicted.returncode == 0, predicted.stdout + predicted.stderr
    assert "changed=1" in predicted.stdout
    assert not receipt.exists()
    assert (
        _link_snapshot(tmp_path / "install", tmp_path / "bin/runtime-fixture")
        == before_links
    )


def test_helper_uses_distinct_owned_transactions_and_cleans_each_one(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    kwargs = {
        "owner": owner,
        "group": group,
    }

    first = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        "stage",
        "runtime-fixture",
        "v1",
        "0" * 64,
        "archive",
        **kwargs,
    )
    second = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        "stage",
        "runtime-fixture",
        "v1",
        "0" * 64,
        "archive",
        **kwargs,
    )

    assert first["transaction_dir"] != second["transaction_dir"]
    for prepared in (first, second):
        transaction = Path(prepared["transaction_dir"])
        assert transaction.is_dir()
        assert (transaction / ".runtime-release-transaction.json").is_file()
        Path(prepared["artifact_path"]).write_text("artifact\n")
        Path(prepared["artifact_path"]).chmod(0o600)
        (Path(prepared["stage_dir"]) / "runtime-fixture").write_text("binary\n")
        helper.cleanup_staging(
            root,
            root / ".runtime-release-staging",
            transaction,
            "artifact",
            "stage",
            "runtime-fixture",
            "v1",
            "0" * 64,
            "archive",
            **kwargs,
        )
        assert not transaction.exists()
    assert list((root / ".runtime-release-staging").iterdir()) == []


def test_failed_download_transaction_cleanup_allows_unchanged_retry(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    kwargs = {"owner": owner, "group": group}

    failed = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        **kwargs,
    )
    helper.cleanup_staging(
        root,
        root / ".runtime-release-staging",
        Path(failed["transaction_dir"]),
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        **kwargs,
    )

    retry = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        **kwargs,
    )

    assert retry["transaction_dir"] != failed["transaction_dir"]
    assert Path(retry["transaction_dir"]).is_dir()
    helper.cleanup_staging(
        root,
        root / ".runtime-release-staging",
        Path(retry["transaction_dir"]),
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        **kwargs,
    )


def test_failed_archive_transaction_cleanup_removes_only_receipt_owned_nodes(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    prepared = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact.tar",
        "stage",
        "runtime-fixture",
        "v1",
        "1" * 64,
        "archive",
        owner=owner,
        group=group,
    )
    artifact = Path(prepared["artifact_path"])
    artifact.write_text("partial archive\n")
    artifact.chmod(0o600)
    candidate = Path(prepared["stage_dir"]) / "runtime-fixture"
    candidate.write_text("partial candidate\n")

    helper.cleanup_staging(
        root,
        root / ".runtime-release-staging",
        Path(prepared["transaction_dir"]),
        "artifact.tar",
        "stage",
        "runtime-fixture",
        "v1",
        "1" * 64,
        "archive",
        owner=owner,
        group=group,
    )

    assert not Path(prepared["transaction_dir"]).exists()


def test_helper_cli_reports_and_cleans_exact_transaction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    common = [
        "--install-root",
        str(root),
        "--staging-dir",
        str(root / ".runtime-release-staging"),
        "--version",
        "v1",
        "--binary-name",
        "runtime-fixture",
        "--artifact-name",
        "artifact",
        "--artifact-sha256",
        "0" * 64,
        "--artifact-type",
        "binary",
        "--stage-name",
        "",
        "--owner",
        owner,
        "--group",
        group,
    ]

    assert helper.main([*common, "--prepare-staging"]) == 0
    prepared = json.loads(capsys.readouterr().out)
    transaction = Path(prepared["transaction_dir"])
    assert transaction.is_dir()

    assert (
        helper.main(
            [
                *common,
                "--transaction-dir",
                str(transaction),
                "--cleanup-staging",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "cleaned"
    assert not transaction.exists()


def test_helper_refuses_writable_install_ancestor_before_staging_write(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.mkdir(mode=0o777)
    unsafe_parent.chmod(0o777)
    root = unsafe_parent / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name

    with pytest.raises(helper.UnsafeState, match="unsafe-storage-ancestor"):
        helper.prepare_staging(
            root,
            root / ".runtime-release-staging",
            "artifact",
            None,
            "runtime-fixture",
            "v1",
            "0" * 64,
            "binary",
            owner=owner,
            group=group,
        )

    assert not (root / ".runtime-release-staging").exists()


def test_helper_refuses_symlinked_install_ancestor_before_staging_write(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    trusted_parent = tmp_path / "trusted-parent"
    trusted_parent.mkdir(mode=0o700)
    real_root = trusted_parent / "install"
    real_root.mkdir(mode=0o755)
    aliased_parent = tmp_path / "aliased-parent"
    aliased_parent.symlink_to(trusted_parent, target_is_directory=True)
    root = aliased_parent / "install"
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name

    with pytest.raises(helper.UnsafeState, match="unsafe-storage-ancestor"):
        helper.prepare_staging(
            root,
            root / ".runtime-release-staging",
            "artifact",
            None,
            "runtime-fixture",
            "v1",
            "0" * 64,
            "binary",
            owner=owner,
            group=group,
        )

    assert not (real_root / ".runtime-release-staging").exists()


def test_check_mode_staging_preflight_refuses_symlink_without_writes(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    external = tmp_path / "external-staging"
    external.mkdir(mode=0o700)
    marker = external / "operator-owned"
    marker.write_text("preserve\n")
    staging = root / ".runtime-release-staging"
    staging.symlink_to(external, target_is_directory=True)
    before = marker.read_bytes()

    with pytest.raises(helper.UnsafeState, match="unsafe-staging-directory"):
        helper.validate_staging_root(
            root,
            staging,
            owner=getpass.getuser(),
            group=grp.getgrgid(os.getgid()).gr_name,
        )

    assert staging.is_symlink()
    assert marker.read_bytes() == before
    assert set(external.iterdir()) == {marker}


@pytest.mark.parametrize("kind", ["regular", "wrong-mode"])
def test_check_mode_staging_preflight_refuses_unsafe_final_node_without_writes(
    tmp_path: Path,
    kind: str,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    staging = root / ".runtime-release-staging"
    if kind == "regular":
        staging.write_text("operator-owned\n")
    else:
        staging.mkdir(mode=0o755)
    before = staging.lstat()

    with pytest.raises(helper.UnsafeState, match="unsafe-staging-directory"):
        helper.validate_staging_root(
            root,
            staging,
            owner=getpass.getuser(),
            group=grp.getgrgid(os.getgid()).gr_name,
        )

    after = staging.lstat()
    assert (after.st_dev, after.st_ino, after.st_mode) == (
        before.st_dev,
        before.st_ino,
        before.st_mode,
    )


def test_check_mode_staging_preflight_accepts_absent_leaf_without_creating_it(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    staging = root / ".runtime-release-staging"

    result = helper.validate_staging_root(
        root,
        staging,
        owner=getpass.getuser(),
        group=grp.getgrgid(os.getgid()).gr_name,
    )

    assert result == {"status": "validated", "changed": False}
    assert not staging.exists()


def test_check_mode_staging_preflight_refuses_writable_ancestor_without_writes(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.mkdir(mode=0o777)
    unsafe_parent.chmod(0o777)
    root = unsafe_parent / "install"
    root.mkdir(mode=0o755)
    staging = root / ".runtime-release-staging"

    with pytest.raises(helper.UnsafeState, match="unsafe-storage-ancestor"):
        helper.validate_staging_root(
            root,
            staging,
            owner=getpass.getuser(),
            group=grp.getgrgid(os.getgid()).gr_name,
        )

    assert not staging.exists()


def test_pre_download_validation_refuses_replaced_ancestor_without_writing(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    trusted_parent = tmp_path / "trusted-parent"
    trusted_parent.mkdir(mode=0o700)
    root = trusted_parent / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    prepared = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        owner=owner,
        group=group,
    )
    displaced = tmp_path / "displaced-parent"
    trusted_parent.rename(displaced)
    attacker = tmp_path / "attacker-parent"
    attacker.mkdir(mode=0o777)
    attacker.chmod(0o777)
    marker = attacker / "operator-owned"
    marker.write_text("preserve\n")
    trusted_parent.symlink_to(attacker, target_is_directory=True)

    with pytest.raises(helper.UnsafeState, match="unsafe-storage-ancestor"):
        helper.validate_staging(
            root,
            root / ".runtime-release-staging",
            Path(prepared["transaction_dir"]),
            "artifact",
            None,
            "runtime-fixture",
            "v1",
            "0" * 64,
            "binary",
            "prepared",
            owner=owner,
            group=group,
        )

    assert marker.read_text() == "preserve\n"
    assert not (attacker / "install/.runtime-release-staging").exists()


def test_real_role_check_mode_refuses_non_root_fixture_without_writes(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho check\n")

    predicted = _run_role(tmp_path, "v-check", artifact, check=True)
    assert predicted.returncode != 0
    assert not (tmp_path / "install").exists()
    assert not (tmp_path / "install" / ".downloads").exists()


def test_helper_check_mode_predicts_existing_release_without_link_writes(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    first = tmp_path / "fixture-v1"
    second = tmp_path / "fixture-v2"
    first.write_text("#!/bin/sh\necho v1\n")
    second.write_text("#!/bin/sh\necho v2\n")
    assert _run_helper_fixture(tmp_path, "v1", first).returncode == 0
    assert _run_helper_fixture(tmp_path, "v2", second).returncode == 0
    root = tmp_path / "install"
    public = tmp_path / "bin/runtime-fixture"
    before = _link_snapshot(root, public)

    predicted = _run_helper_fixture(tmp_path, "v1", first, check=True)

    assert predicted.returncode == 0, predicted.stdout + predicted.stderr
    assert "changed=1" in predicted.stdout
    assert _link_snapshot(root, public) == before


def test_real_role_rejects_public_self_link_before_writing(tmp_path: Path) -> None:
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho self-link\n")
    public = tmp_path / "install" / "releases" / "v1" / "runtime-fixture"

    refused = _run_role(tmp_path, "v1", artifact, public_link=public)
    assert refused.returncode != 0
    assert not (tmp_path / "install").exists()


def test_real_role_rejects_unmanaged_public_file_before_writing(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    public = bin_dir / "runtime-fixture"
    public.write_text("operator-owned\n")
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho refused\n")

    refused = _run_role(tmp_path, "v1", artifact)
    assert refused.returncode != 0
    assert public.read_text() == "operator-owned\n"
    assert not (tmp_path / "install").exists()


def test_real_role_rejects_non_root_storage_override_before_writes(
    tmp_path: Path,
) -> None:
    """Consumer storage overrides cannot reopen a root-write staging path."""
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho refused\n")
    non_root = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name

    refused = _run_role(
        tmp_path,
        "v1",
        artifact,
        storage_owner=non_root,
        storage_group=group,
    )

    assert refused.returncode != 0
    assert "runtime_release_storage_owner == 'root'" in (
        refused.stdout + refused.stderr
    )
    assert not (tmp_path / "install").exists()


def test_helper_refuses_symlinked_trusted_staging_namespace_without_external_write(
    tmp_path: Path,
) -> None:
    """Root must never follow a runtime-controlled staging namespace redirect."""
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    (tmp_path / "bin").mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "operator-owned"
    marker.write_text("preserve\n")
    (root / ".runtime-release-staging").symlink_to(external, target_is_directory=True)
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho staging\n")

    refused = _run_helper_fixture(tmp_path, "v1", artifact, install_root=root)

    assert refused.returncode != 0
    assert marker.read_text() == "preserve\n"
    assert not (external / "runtime-release-runtime-fixture-v1-amd64-fixture").exists()


def test_helper_does_not_reuse_precreated_legacy_staging_artifact(
    tmp_path: Path,
) -> None:
    """A foreign legacy name cannot collide with a unique transaction path."""
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    staging = root / ".runtime-release-staging"
    staging.mkdir(mode=0o700)
    (tmp_path / "bin").mkdir()
    external = tmp_path / "external-artifact"
    external.write_text("operator-owned\n")
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho artifact\n")
    artifact_node, _ = _trusted_staging_paths(root, "v1", artifact)
    artifact_node.symlink_to(external)

    installed = _run_helper_fixture(tmp_path, "v1", artifact, install_root=root)

    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert external.read_text() == "operator-owned\n"
    assert artifact_node.is_symlink()


def test_helper_does_not_reuse_precreated_legacy_archive_stage(
    tmp_path: Path,
) -> None:
    """A foreign legacy stage cannot collide with a unique transaction path."""
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    staging = root / ".runtime-release-staging"
    staging.mkdir(mode=0o700)
    (tmp_path / "bin").mkdir()
    external = tmp_path / "external-stage"
    external.mkdir()
    marker = external / "operator-owned"
    marker.write_text("preserve\n")
    artifact = tmp_path / "fixture.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        entry = zipfile.ZipInfo("runtime-fixture")
        entry.external_attr = 0o755 << 16
        archive.writestr(entry, b"#!/bin/sh\necho archive\n")
    _, stage = _trusted_staging_paths(root, "v1", artifact)
    stage.symlink_to(external, target_is_directory=True)

    installed = _run_helper_fixture(
        tmp_path,
        "v1",
        artifact,
        install_root=root,
        artifact_type="archive",
        archive_member="runtime-fixture",
    )

    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert marker.read_text() == "preserve\n"
    assert stage.is_symlink()


def test_cleanup_retains_replaced_transaction_nodes_for_explicit_recovery(
    tmp_path: Path,
) -> None:
    helper = _activator_module()
    root = tmp_path / "install"
    root.mkdir(mode=0o755)
    owner = getpass.getuser()
    group = grp.getgrgid(os.getgid()).gr_name
    preparation = helper.prepare_staging(
        root,
        root / ".runtime-release-staging",
        "artifact",
        None,
        "runtime-fixture",
        "v1",
        "0" * 64,
        "binary",
        owner=owner,
        group=group,
    )
    transaction = Path(preparation["transaction_dir"])
    external = tmp_path / "operator-owned"
    external.write_text("preserve\n")
    Path(preparation["artifact_path"]).symlink_to(external)

    with pytest.raises(helper.UnsafeState, match="unsafe-staging-artifact"):
        helper.cleanup_staging(
            root,
            root / ".runtime-release-staging",
            transaction,
            "artifact",
            None,
            "runtime-fixture",
            "v1",
            "0" * 64,
            "binary",
            owner=owner,
            group=group,
        )

    assert transaction.is_dir()
    assert Path(preparation["artifact_path"]).is_symlink()
    assert external.read_text() == "preserve\n"


def test_helper_accepts_uppercase_pin_and_stores_canonical_receipt(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho uppercase\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact, uppercase_checksum=True)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    receipt = yaml.safe_load(
        (tmp_path / "install/releases/v1/.runtime-release.json").read_text()
    )
    assert receipt["artifact_sha256"].islower()


def test_helper_extracts_only_declared_archive_member(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        binary = b"#!/bin/sh\necho archive\n"
        binary_info = zipfile.ZipInfo("runtime-fixture")
        binary_info.external_attr = 0o755 << 16
        archive.writestr(binary_info, binary)
        archive.writestr("../escaped", b"must not extract\n")

    installed = _run_helper_fixture(
        tmp_path,
        "v1",
        artifact,
        artifact_type="archive",
        archive_member="runtime-fixture",
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    release = tmp_path / "install" / "releases" / "v1"
    assert (release / "runtime-fixture").read_bytes() == binary
    assert not (tmp_path / "install" / "releases" / "escaped").exists()
    assert not (tmp_path / "install" / "escaped").exists()


def test_real_role_refuses_archive_symlink_member_without_activation(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    outside = tmp_path / "outside"
    outside.write_text("operator-owned\n")
    artifact = tmp_path / "fixture.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        link = zipfile.ZipInfo("runtime-fixture")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, str(outside))

    refused = _run_role(
        tmp_path,
        "v1",
        artifact,
        artifact_type="archive",
        archive_member="runtime-fixture",
    )

    assert refused.returncode != 0
    assert outside.read_text() == "operator-owned\n"
    assert not (tmp_path / "install" / "current").exists()
    assert not (tmp_path / "install/releases/v1/.runtime-release.json").exists()


def test_real_role_refuses_archive_hardlink_member_without_activation(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture.tar"
    with tarfile.open(artifact, "w") as archive:
        payload = tarfile.TarInfo("payload")
        payload.size = len(b"#!/bin/sh\necho hardlink\n")
        archive.addfile(
            payload, __import__("io").BytesIO(b"#!/bin/sh\necho hardlink\n")
        )
        link = tarfile.TarInfo("runtime-fixture")
        link.type = tarfile.LNKTYPE
        link.linkname = "payload"
        link.mode = 0o755
        archive.addfile(link)

    refused = _run_role(
        tmp_path,
        "v1",
        artifact,
        artifact_type="archive",
        archive_member="runtime-fixture",
    )

    assert refused.returncode != 0
    assert not (tmp_path / "install" / "current").exists()
    assert not (tmp_path / "install/releases/v1/.runtime-release.json").exists()


def test_helper_refuses_existing_hardlinked_candidate_before_writing(
    tmp_path: Path,
) -> None:
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho hardlinked\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    release = tmp_path / "install/releases/v1"
    receipt = release / ".runtime-release.json"
    receipt.unlink()
    os.link(release / "runtime-fixture", release / "runtime-fixture-alias")

    refused = _run_helper_fixture(tmp_path, "v1", artifact)

    assert refused.returncode != 0
    assert not receipt.exists()
    assert (release / "runtime-fixture").stat().st_nlink == 2


def test_helper_refuses_group_or_world_writable_existing_candidate(
    tmp_path: Path,
) -> None:
    """An installed binary must not remain mutable after its receipt exists."""
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho immutable\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr

    candidate = tmp_path / "install/releases/v1/runtime-fixture"
    candidate.chmod(0o775)
    before = candidate.read_bytes()

    refused = _run_helper_fixture(tmp_path, "v1", artifact)

    assert refused.returncode != 0
    assert candidate.read_bytes() == before
    assert candidate.stat().st_mode & 0o777 == 0o775


def test_helper_refuses_group_or_world_writable_existing_release_directory(
    tmp_path: Path,
) -> None:
    """A receipt cannot protect a version directory the runtime may replace in."""
    (tmp_path / "bin").mkdir()
    artifact = tmp_path / "fixture"
    artifact.write_text("#!/bin/sh\necho immutable-directory\n")
    installed = _run_helper_fixture(tmp_path, "v1", artifact)
    assert installed.returncode == 0, installed.stdout + installed.stderr

    release = tmp_path / "install/releases/v1"
    release.chmod(0o775)
    receipt = release / ".runtime-release.json"
    before = receipt.read_bytes()

    refused = _run_helper_fixture(tmp_path, "v1", artifact)

    assert refused.returncode != 0
    assert receipt.read_bytes() == before
    assert release.stat().st_mode & 0o777 == 0o775


def test_locked_helper_refuses_existing_candidate_with_foreign_storage_identity(
    tmp_path: Path, monkeypatch
) -> None:
    """A receipt cannot bless a binary owned by a different storage identity."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    candidate = root / "releases/v1/runtime-fixture"
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()

    class ForeignAccount:
        pw_uid = os.getuid() + 1

    monkeypatch.setattr(helper.pwd, "getpwnam", lambda _name: ForeignAccount())
    with __import__("pytest").raises(helper.UnsafeState):
        helper.activate(
            root,
            "v1",
            "runtime-fixture",
            public,
            check=False,
            artifact_sha256=digest,
            candidate_sha256=digest,
            artifact_type="binary",
            arch_key="amd64",
            arch_slug="amd64",
            owner="runtime-storage",
            group=grp.getgrgid(os.getgid()).gr_name,
        )


def test_locked_helper_refuses_public_parent_swap_without_touching_attacker_directory(
    tmp_path: Path, monkeypatch
) -> None:
    """Public-link publication must retain a checked parent directory handle."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    public.unlink()
    trusted_parent = public.parent
    displaced_parent = tmp_path / "displaced-bin"
    attacker_parent = tmp_path / "attacker-bin"
    real_symlink = helper.os.symlink
    trusted_identity = (trusted_parent.stat().st_dev, trusted_parent.stat().st_ino)
    swapped = False

    def swap_before_public_temp_link(target, link_name, *args, **kwargs):
        nonlocal swapped
        descriptor = kwargs.get("dir_fd")
        descriptor_identity = (
            (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
            if descriptor is not None
            else None
        )
        if not swapped and descriptor_identity == trusted_identity:
            swapped = True
            trusted_parent.rename(displaced_parent)
            attacker_parent.mkdir()
        return real_symlink(target, link_name, *args, **kwargs)

    monkeypatch.setattr(helper.os, "symlink", swap_before_public_temp_link)
    with __import__("pytest").raises(
        (helper.ActivationFailed, helper.CompensationIncomplete, helper.UnsafeState)
    ):
        helper.activate(root, "v1", "runtime-fixture", public, check=False)

    assert swapped
    assert not (attacker_parent / public.name).exists()


def test_locked_helper_refuses_parent_swap_during_compensation_without_attacker_write(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed publish cannot compensate through a replacement public parent."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    trusted_parent = public.parent
    displaced_parent = tmp_path / "displaced-bin"
    attacker_parent = tmp_path / "attacker-bin"
    before_attacker = attacker_parent / public.name
    real_verify = helper._verify_desired
    invoked = False

    def fail_after_swap(*args, **kwargs):
        nonlocal invoked
        if not invoked:
            invoked = True
            trusted_parent.rename(displaced_parent)
            attacker_parent.mkdir()
            before_attacker.write_text("attacker-owned\n")
            raise OSError("inject compensation after public parent swap")
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(helper, "_verify_desired", fail_after_swap)
    with __import__("pytest").raises(helper.CompensationIncomplete):
        helper.activate(root, "v1", "runtime-fixture", public, check=False)

    assert before_attacker.read_text() == "attacker-owned\n"


def test_locked_helper_refuses_install_root_replacement_after_lock_without_attacker_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    """The lock fd remains authoritative if the root pathname is replaced."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    displaced = tmp_path / "displaced-install"
    attacker = tmp_path / "attacker-install"
    attacker.mkdir()
    attacker_marker = attacker / "operator-owned"
    attacker_marker.write_text("preserve\n")
    real_flock = helper.fcntl.flock
    swapped = False

    def replace_root_after_lock(descriptor, operation):
        nonlocal swapped
        real_flock(descriptor, operation)
        if not swapped:
            swapped = True
            root.rename(displaced)
            attacker.rename(root)

    monkeypatch.setattr(helper.fcntl, "flock", replace_root_after_lock)
    with __import__("pytest").raises(
        helper.UnsafeState, match="directory-identity-changed"
    ):
        helper.activate(root, "v1", "runtime-fixture", public, check=False)

    assert swapped
    assert (root / "operator-owned").read_text() == "preserve\n"
    assert not (root / "current").exists()
    assert (displaced / "current").is_symlink()


def test_locked_helper_refuses_untrusted_public_parent_before_activation(
    tmp_path: Path,
) -> None:
    """Public names live only in the same immutable storage contract as releases."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    before = _link_snapshot(root, public)
    public.parent.chmod(0o777)

    with __import__("pytest").raises(
        helper.UnsafeState, match="unsafe-public-link-parent-directory"
    ):
        helper.activate(root, "v1", "runtime-fixture", public, check=False)

    assert _link_snapshot(root, public) == before


def test_locked_helper_refuses_same_name_swap_before_public_unlink(
    tmp_path: Path, monkeypatch
) -> None:
    """An attacker replacement is detected before an unlink can remove it."""
    helper = _activator_module()
    root, public = _activation_layout(tmp_path)
    root_guard = helper._open_directory(root)
    public_guard = helper._open_directory(public.parent)
    real_revalidate = helper._revalidate_link_node
    swapped = False

    def replace_public_before_revalidate(path, expected, **kwargs):
        nonlocal swapped
        if path == public and not swapped:
            swapped = True
            public.unlink()
            public.write_text("attacker-owned\n")
        return real_revalidate(path, expected, **kwargs)

    monkeypatch.setattr(
        helper, "_revalidate_link_node", replace_public_before_revalidate
    )
    try:
        with __import__("pytest").raises(helper.UnsafeState, match="link-node-changed"):
            helper._set_link_state(
                public,
                None,
                parent=public_guard,
                root=root,
                binary_name="runtime-fixture",
                public=True,
            )
    finally:
        public_guard.close()
        root_guard.close()

    assert swapped
    assert public.read_text() == "attacker-owned\n"
